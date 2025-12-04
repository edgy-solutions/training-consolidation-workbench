from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import os
import json
from datetime import timedelta
from dagster_graphql import DagsterGraphQLClient, DagsterGraphQLClientError

from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.storage.minio import MinioClient
from src.workbench.models import (
    ConceptNode, SourceSlide, TargetDraftNode, SynthesisRequest, SearchRequest,
    GenerateSkeletonRequest, GenerateSkeletonResponse, SkeletonRequest, ProjectTreeResponse,
    RenderRequest
)
from src.ingestion.assets import BUCKET_NAME

from dotenv import load_dotenv

app = FastAPI(title="Training Consolidation Workbench API")

# Load env vars
load_dotenv()

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Clients
# In a real app, use dependency injection or lifespan events
neo4j_client = Neo4jClient()
weaviate_client = WeaviateClient()
minio_client = MinioClient()
# Dagster client - assuming default port or env var
DAGSTER_HOST = os.getenv("DAGSTER_HOST", "localhost")
DAGSTER_PORT = int(os.getenv("DAGSTER_PORT", 3000))
dagster_client = DagsterGraphQLClient(DAGSTER_HOST, port_number=DAGSTER_PORT)

# --- A. The Explorer Module ---

@app.get("/source/tree", response_model=List[Dict[str, Any]])
def get_source_tree(engineering_discipline: Optional[str] = None):
    """
    Returns the hierarchy of Business Units -> Courses.
    Optional: Filter by engineering discipline.
    """
    discipline = engineering_discipline
    if discipline:
        # Convert discipline to title case to match DB values (e.g. "software" -> "Software")
        # Or handle via backend logic if DB is strict.
        # Assuming DB uses Capitalized "Software", "Mechanical" etc.
        query = """
        MATCH (c:Course)
        WHERE toLower(c.discipline) CONTAINS toLower($discipline)
        RETURN c.business_unit as bu, c.id as id, c.title as title, c.discipline as engineering_discipline
        ORDER BY bu, title
        """
        # Use simple parameter for CONTAINS check
        params = {"discipline": discipline}
    else:
        query = """
        MATCH (c:Course)
        RETURN c.business_unit as bu, c.id as id, c.title as title, c.discipline as engineering_discipline
        ORDER BY bu, title
        """
        params = {}
        
    results = neo4j_client.execute_query(query, params)
    
    # Group by Business Unit
    tree = {}
    for row in results:
        bu = row.get("bu", "Uncategorized")
        if bu not in tree:
            tree[bu] = {"name": bu, "type": "BusinessUnit", "children": []}
        
        tree[bu]["children"].append({
            "id": row["id"],
            "name": row["title"],
            "type": "Course",
            "engineering_discipline": row.get("engineering_discipline"),
            # We could fetch slides here or fetch on demand
            "has_children": True 
        })
        
    return list(tree.values())

@app.get("/source/course/{course_id}/slides", response_model=List[Dict[str, Any]])
def get_course_slides(course_id: str):
    """
    Returns slides for a specific course.
    """
    query = """
    MATCH (c:Course {id: $course_id})-[:HAS_SLIDE]->(s:Slide)
    RETURN s.id as id, s.number as number, s.text as text
    ORDER BY s.number
    """
    results = neo4j_client.execute_query(query, {"course_id": course_id})
    return results

@app.get("/source/course/{course_id}/sections", response_model=List[Dict[str, Any]])
def get_course_sections(course_id: str):
    """
    Returns ALL sections (including nested subsections) for a specific course.
    Uses pre-computed concept summaries or COVERS relationships.
    """
    query = """
    MATCH (c:Course {id: $course_id})-[:HAS_SECTION*]->(s:Section)
    
    // Try to get concepts from:
    // 1. Pre-computed summary property
    // 2. Direct COVERS relationship (rolled up)
    // 3. Linked slides (HAS_SLIDE)
    
    OPTIONAL MATCH (s)-[:COVERS]->(con:Concept)
    WITH s, collect(con.name) as covered_concepts
    
    OPTIONAL MATCH (s)-[:HAS_SLIDE]->(sl:Slide)-[t:TEACHES]->(slide_con:Concept)
    WHERE coalesce(t.salience, 0) >= 0.5
    WITH s, covered_concepts, collect(distinct slide_con.name) as slide_concepts
    
    RETURN s.id as id, 
           s.title as title, 
           s.level as level,
           // Priority: Property > COVERS > HAS_SLIDE > Empty
           coalesce(s.concept_summary, covered_concepts[0..10], slide_concepts[0..10], []) as concepts
    ORDER BY s.id
    """
    sections = neo4j_client.execute_query(query, {"course_id": course_id})
    
    # Get course-level concepts as a last resort fallback for the UI
    # But only if a section truly has NO concepts
    course_concepts_query = """
    MATCH (c:Course {id: $course_id})-[:HAS_SLIDE]->(sl:Slide)-[t:TEACHES]->(con:Concept)
    WHERE coalesce(t.salience, 0) >= 0.5
    RETURN collect(distinct con.name)[0..10] as course_concepts
    """
    course_result = neo4j_client.execute_query(course_concepts_query, {"course_id": course_id})
    course_concepts = course_result[0]["course_concepts"] if course_result else []
    
    formatted_results = []
    for row in sections:
        concepts = row["concepts"]
        if not concepts:
            concepts = course_concepts
            
        formatted_results.append({
            "id": row["id"],
            "title": row["title"],
            "level": row.get("level", 0),
            "concepts": concepts
        })
        
    return formatted_results

@app.get("/source/slide/{slide_id}", response_model=SourceSlide)
def get_slide_details(slide_id: str):
    """
    Returns metadata + S3 Presigned URL for the slide image.
    """
    # 1. Fetch Metadata and Concepts from Neo4j
    query = """
    MATCH (s:Slide {id: $id})
    OPTIONAL MATCH (s)-[t:TEACHES]->(c:Concept)
    RETURN s.id as id, s.number as number, s.text as text, collect({name: c.name, salience: t.salience}) as concepts
    """
    results = neo4j_client.execute_query(query, {"id": slide_id})
    
    if not results:
        raise HTTPException(status_code=404, detail="Slide not found")
        
    row = results[0]
    
    # 2. Construct S3 URL
    # Assuming slide_id format is {course_id}_p{page_num}
    # And image stored at images/{course_id}/page_{page_num}.png
    # We need to parse course_id and page_num from slide_id or store them in graph
    
    parts = slide_id.rsplit("_p", 1)
    if len(parts) != 2:
         # Fallback or error
         course_id = "unknown"
         page_num = "1"
    else:
        course_id = parts[0]
        page_num = parts[1]
        
    # object_name = f"images/{course_id}/page_{page_num}.png"
    # Using generated/pages structure to match MinIO
    object_name = f"{course_id}/generated/pages/page_{page_num}.png"
    s3_url = minio_client.get_presigned_url(BUCKET_NAME, object_name)
    
    # 3. Format Concepts
    concepts = []
    for c in row.get("concepts", []):
        if c and c.get("name"): # check if not null and has name
            concepts.append(ConceptNode(
                name=c.get("name"), 
                domain="General",
                salience=c.get("salience")
            ))
            
    return SourceSlide(
        id=row["id"],
        s3_url=s3_url,
        text_preview=row["text"] if row["text"] else "",
        concepts=concepts
    )

@app.get("/search/concepts", response_model=List[str])
def search_concepts(q: str):
    """
    Semantic search for specific topics. Returns list of Slide IDs.
    """
    try:
        # Weaviate NearText search
        response = weaviate_client.client.query.get(
            "SlideText", ["slide_id"]
        ).with_near_text({
            "concepts": [q]
        }).with_limit(10).do()
        
        slides = []
        if "data" in response and "Get" in response["data"] and "SlideText" in response["data"]["Get"]:
            for item in response["data"]["Get"]["SlideText"]:
                slides.append(item["slide_id"])
                
        return slides
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/source/graph/concept/{name}", response_model=List[str])
def get_slides_by_concept(name: str):
    """
    Returns all slides linked to this concept.
    """
    query = """
    MATCH (s:Slide)-[:TEACHES]->(c:Concept {name: $name}) 
    RETURN s.id as id
    """
    results = neo4j_client.execute_query(query, {"name": name})
    return [row["id"] for row in results]

@app.get("/source/filters", response_model=Dict[str, List[str]])
def get_source_filters():
    """
    Returns distinct values for faceted filters.
    """
    filters = {
        "origins": [],
        "domains": [],
        "intents": [],
        "types": []
    }
    
    # Origins (Business Units)
    res = neo4j_client.execute_query("MATCH (c:Course) RETURN distinct c.business_unit as val ORDER BY val")
    filters["origins"] = [r["val"] for r in res if r["val"]]
    
    # Domains (Mapped to Engineering Discipline)
    res = neo4j_client.execute_query("MATCH (c:Course) RETURN distinct c.discipline as val ORDER BY val")
    filters["domains"] = [r["val"] for r in res if r["val"]]
    
    # Intents (Pedagogical Intent - currently checking Slide, might be empty if not ingested)
    res = neo4j_client.execute_query("MATCH (s:Slide) RETURN distinct s.pedagogical_intent as val ORDER BY val")
    filters["intents"] = [r["val"] for r in res if r["val"]]
    
    # Asset Types (Checking Slide, might be empty)
    res = neo4j_client.execute_query("MATCH (s:Slide) RETURN distinct s.asset_type as val ORDER BY val")
    filters["types"] = [r["val"] for r in res if r["val"]]
    
    return filters

@app.get("/source/heatmap/{term}")
def get_concept_heatmap(term: str):
    """
    Returns heatmap data for a concept term, using salience scores.
    Output: {
        "items": { 
            "course_id_1": { "score": 1.5, "type": "course" },
            "slide_id_1": { "score": 0.8, "type": "slide" }
        }
    }
    """
    query = """
    WITH toLower($term) as term
    // 1. Find matching concepts (direct & synonyms)
    MATCH (c:Concept) WHERE toLower(c.name) CONTAINS term
    WITH c as direct_hit
    
    // Find synonyms via CanonicalConcept (if any)
    OPTIONAL MATCH (direct_hit)-[:ALIGNS_TO]->(cc:CanonicalConcept)<-[:ALIGNS_TO]-(synonym:Concept)
    
    // Aggregate all related concepts into a single list
    WITH collect(distinct direct_hit) + collect(distinct synonym) as all_concepts
    UNWIND all_concepts as c
    WITH distinct c WHERE c IS NOT NULL
    
    // 2. Find Slides with Salience
    MATCH (s:Slide)-[r:TEACHES]->(c)
    // Default salience to 0.5 if missing
    WITH s, sum(coalesce(r.salience, 0.5)) as total_score
    
    // 3. Aggregate to Course
    MATCH (course:Course)-[:HAS_SLIDE]->(s)
    
    RETURN course.id as course_id, s.id as slide_id, total_score as slide_score
    """
    
    results = neo4j_client.execute_query(query, {"term": term})
    
    heatmap = {}
    
    # Aggregate results
    for row in results:
        c_id = row["course_id"]
        s_id = row["slide_id"]
        score = row["slide_score"]
        
        # Store Slide Score
        heatmap[s_id] = {"score": score, "type": "slide"}
        
        # Aggregate Course Score
        if c_id not in heatmap:
            heatmap[c_id] = {"score": 0, "type": "course"}
        # Use MAX aggregation so the course color reflects the "hottest" content inside it
        heatmap[c_id]["score"] = max(heatmap[c_id]["score"], score)
        
    return heatmap

@app.post("/source/search", response_model=List[Dict[str, Any]])
def search_source_tree(request: SearchRequest):
    """
    Advanced search with faceted filters.
    Returns a pruned tree structure containing only matching nodes.
    """
    params = {}
    
    # 1. Semantic Search (if query provided)
    candidate_ids = []
    if request.query:
        try:
            # Weaviate NearText search with certainty threshold
            print(f"Searching Weaviate for: {request.query}")
            response = weaviate_client.client.query.get(
                "SlideText", ["slide_id"]
            ).with_near_text({
                "concepts": [request.query],
                "certainty": 0.6  # Lowered to 0.6 to capture relevant matches (e.g. "Assemblies" ~0.68)
            }).with_limit(50).do()
            
            print(f"Weaviate raw response: {response}")
            
            if "data" in response and "Get" in response["data"] and "SlideText" in response["data"]["Get"]:
                candidate_ids = [item["slide_id"] for item in response["data"]["Get"]["SlideText"]]
                print(f"Found {len(candidate_ids)} candidate slide IDs: {candidate_ids}")
            
            if not candidate_ids:
                print(f"No semantic matches found for: {request.query}")
                return [] # No semantic matches
        except Exception as e:
            print(f"Weaviate search failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback or return empty? Let's return empty for now if query was explicit
            return []

    # 2. Build Cypher Query
    # Base pattern: BusinessUnit -> Course -> Slide
    query_parts = [
        "MATCH (c:Course)",
        "MATCH (c)-[:HAS_SLIDE]->(s:Slide)"
    ]
    
    where_clauses = []
    
    # Filter: Origin (Business Unit)
    if request.filters.get("origin"):
        # Assuming origin is the Business Unit name stored on Course
        where_clauses.append("c.business_unit = $origin")
        params["origin"] = request.filters["origin"]
        
    # Filter: Domain (Mapped to Course.discipline)
    if request.filters.get("domain"):
        where_clauses.append("c.discipline = $domain")
        params["domain"] = request.filters["domain"]

    # Filter: Pedagogical Intent
    if request.filters.get("intent"):
        where_clauses.append("s.pedagogical_intent = $intent")
        params["intent"] = request.filters["intent"]

    # Filter: Asset Type
    if request.filters.get("type") and request.filters["type"] != "All Types":
        # Case-insensitive match for asset type
        where_clauses.append("toLower(s.asset_type) = toLower($type)")
        params["type"] = request.filters["type"]

    # Filter: Candidate IDs from Semantic Search
    if request.query:
        where_clauses.append("s.id IN $candidate_ids")
        params["candidate_ids"] = candidate_ids

    if where_clauses:
        query_parts.append("WHERE " + " AND ".join(where_clauses))

    # Return structure
    # We want to reconstruct the tree: BU -> Course -> Slide
    # Need to fetch concepts for each slide first
    query_parts.append("""
    WITH c, s
    OPTIONAL MATCH (s)-[t:TEACHES]->(con:Concept)
    WITH c, s, collect({name: con.name, domain: con.domain, salience: t.salience}) as concepts
    RETURN c.business_unit as bu, 
           c.id as course_id, 
           c.title as course_title, 
           c.discipline as discipline,
           collect(distinct {
               id: s.id, 
               number: s.number, 
               text: s.text,
               s3_url: s.s3_url,
               concepts: [x IN concepts WHERE x.name IS NOT NULL]
           }) as slides
    ORDER BY bu, course_title
    """)
    
    final_query = "\n".join(query_parts)
    
    results = neo4j_client.execute_query(final_query, params)
    
    # 3. Reconstruct Tree
    tree = {}
    for row in results:
        bu = row.get("bu", "Uncategorized")
        if bu not in tree:
            tree[bu] = {"name": bu, "type": "BusinessUnit", "children": []}
            
        # Process slides to generate S3 URLs
        slides = row["slides"]
        for slide in slides:
            # Generate S3 URL dynamically as it's not stored in DB
            try:
                parts = slide["id"].rsplit("_p", 1)
                if len(parts) == 2:
                    c_id = parts[0]
                    page_num = parts[1]
                    object_name = f"{c_id}/generated/pages/page_{page_num}.png"
                    slide["s3_url"] = minio_client.get_presigned_url(BUCKET_NAME, object_name)
            except Exception as e:
                print(f"Failed to generate S3 URL for slide {slide['id']}: {e}")

        # Add Course
        course_entry = {
            "id": row["course_id"],
            "name": row["course_title"],
            "type": "Course",
            "engineering_discipline": row.get("discipline"),
            "slides": slides, # Direct slides list with populated URLs
            "has_children": True
        }
        tree[bu]["children"].append(course_entry)

    return list(tree.values())

# --- B. The Builder Module ---

@app.post("/draft/create", response_model=TargetDraftNode)
def create_draft_project(title: str):
    """
    Initializes a new empty consolidation project.
    """
    import uuid
    project_id = str(uuid.uuid4())
    
    query = """
    CREATE (p:Project:TargetNode {id: $id, title: $title, status: "empty", content_markdown: ""})
    RETURN p.id as id, p.title as title, p.status as status
    """
    results = neo4j_client.execute_query(query, {"id": project_id, "title": title})
    row = results[0]
    
    return TargetDraftNode(
        id=row["id"],
        title=row["title"],
        status=row["status"]
    )

@app.post("/draft/node/add", response_model=TargetDraftNode)
def add_draft_node(parent_id: str, title: str):
    """
    Adds a new Section/Module to the new outline.
    Defaults to 'technical' section type.
    """
    import uuid
    node_id = str(uuid.uuid4())
    
    query = """
    MATCH (parent {id: $parent_id})
    CREATE (child:TargetNode {
        id: $id, 
        title: $title, 
        status: "draft", 
        content_markdown: "",
        section_type: "technical"
    })
    MERGE (parent)-[:HAS_CHILD]->(child)
    RETURN child.id as id, child.title as title, child.status as status, child.section_type as section_type
    """
    # Note: parent could be Project or TargetNode
    results = neo4j_client.execute_query(query, {"parent_id": parent_id, "id": node_id, "title": title})
    
    if not results:
        raise HTTPException(status_code=404, detail="Parent node not found")
        
    row = results[0]
    
    return TargetDraftNode(
        id=row["id"],
        title=row["title"],
        parent_id=parent_id,
        status=row["status"],
        section_type=row.get("section_type", "technical")
    )

@app.put("/draft/node/map")
def map_slides_to_node(node_id: str, slide_ids: List[str]):
    """
    Links "Source Slides" to a "Target Node" (Drag & Drop action).
    Now performs a full sync: removes existing links and adds new ones.
    """
    query = """
    MATCH (t:TargetNode {id: $node_id})
    OPTIONAL MATCH (t)-[r:DERIVED_FROM]->(:Slide)
    DELETE r
    WITH t
    UNWIND $slide_ids as sid
    MATCH (s:Slide {id: sid})
    MERGE (t)-[:DERIVED_FROM]->(s)
    """
    neo4j_client.execute_query(query, {"node_id": node_id, "slide_ids": slide_ids})
    return {"status": "success", "mapped_slides": len(slide_ids)}

@app.put("/draft/node/content")
def update_node_content(node_id: str, request: dict = Body(...)):
    """
    Updates the content_markdown property of a TargetNode.
    Used for auto-saving edited synthesis content from the TipTap editor.
    """
    content_markdown = request.get("content_markdown", "")
    
    query = """
    MATCH (t:TargetNode {id: $node_id})
    SET t.content_markdown = $content
    RETURN t.id as id
    """
    result = neo4j_client.execute_query(query, {"node_id": node_id, "content": content_markdown})
    
    if not result:
        raise HTTPException(status_code=404, detail="Node not found")
    
    return {"status": "success", "node_id": node_id}

@app.put("/draft/node/title")
def update_node_title(node_id: str, request: dict = Body(...)):
    """
    Updates the title of a TargetNode.
    Only allowed for non-mandatory sections (technical).
    """
    title = request.get("title", "")
    
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    
    # Check if this is a mandatory section
    check_query = """
    MATCH (t:TargetNode {id: $node_id})
    RETURN t.section_type as section_type
    """
    check_result = neo4j_client.execute_query(check_query, {"node_id": node_id})
    
    if not check_result:
        raise HTTPException(status_code=404, detail="Node not found")
    
    section_type = check_result[0].get("section_type", "technical")
    
    if section_type in ['introduction', 'mandatory_safety', 'mandatory_assessment']:
        raise HTTPException(status_code=403, detail="Cannot rename mandatory sections")
    
    query = """
    MATCH (t:TargetNode {id: $node_id})
    SET t.title = $title
    RETURN t.id as id
    """
    result = neo4j_client.execute_query(query, {"node_id": node_id, "title": title})
    
    return {"status": "success", "node_id": node_id, "title": title}

@app.get("/draft/structure/{project_id}", response_model=List[TargetDraftNode])
def get_draft_structure(project_id: str):
    """
    Returns the current "New" outline tree.
    """
    # This is a simplified traversal. Recursion might be needed for full tree.
    # For now, let's return flat list with parent_ids
    query = """
    MATCH (p:Project {id: $project_id})
    OPTIONAL MATCH (p)-[:HAS_CHILD*]->(n:TargetNode)
    RETURN n.id as id, n.title as title, n.status as status, n.content_markdown as content
    """ 
    # Accessing parent needs a bit more cypher or separate query.
    # Better query to get nodes and their parents
    query = """
    MATCH (p:Project {id: $project_id})
    WITH p
    MATCH (n:TargetNode) 
    WHERE (p)-[:HAS_CHILD*0..]->(n)
    OPTIONAL MATCH (parent)-[:HAS_CHILD]->(n)
    OPTIONAL MATCH (n)-[:DERIVED_FROM]->(s:Slide)
    OPTIONAL MATCH (n)-[:SUGGESTED_SOURCE]->(ss:Slide)
    RETURN n.id as id, n.title as title, n.status as status, n.content_markdown as content, 
           n.rationale as rationale, n.order as order, coalesce(n.is_unassigned, false) as is_unassigned,
           coalesce(n.is_placeholder, false) as is_placeholder,
           coalesce(n.section_type, 'technical') as section_type,
           parent.id as parent_id, 
           collect(distinct s.id) as source_refs,
           collect(distinct ss.id) as suggested_source_ids
    ORDER BY n.order ASC
    """
    results = neo4j_client.execute_query(query, {"project_id": project_id})
    
    nodes = []
    
    # Explicitly fetch the project node to ensure it's included as the root
    project_query = "MATCH (p:Project {id: $project_id}) RETURN p.id as id, p.title as title, p.status as status"
    project_result = neo4j_client.execute_query(project_query, {"project_id": project_id})
    
    if project_result:
        p_row = project_result[0]
        nodes.append(TargetDraftNode(
            id=p_row["id"],
            title=p_row["title"],
            parent_id=None, # Root has no parent
            status=p_row["status"] or "draft",
            content_markdown=None,
            source_refs=[],
            is_suggestion=False,
            suggested_source_ids=[],
            rationale=None
        ))

    for row in results:
        # Determine if it's a suggestion based on status
        is_suggestion = row["status"] == "suggestion"
        
        nodes.append(TargetDraftNode(
            id=row["id"],
            title=row["title"],
            parent_id=row["parent_id"],
            status=row["status"] or "empty",
            content_markdown=row["content"],
            source_refs=row["source_refs"],
            is_suggestion=is_suggestion,
            suggested_source_ids=row["suggested_source_ids"],
            rationale=row["rationale"],
            order=row.get("order", 0),
            is_unassigned=row.get("is_unassigned") or False,
            is_placeholder=row.get("is_placeholder") or False,
            section_type=row.get("section_type", "technical")
        ))
    return nodes

# --- C. The Synthesis Module ---

from fastapi import BackgroundTasks
from src.services.synthesis_service import SynthesisService

@app.post("/synthesis/trigger")
def trigger_synthesis(request: SynthesisRequest, background_tasks: BackgroundTasks):
    """
    Triggers the DSPy generation logic via background task.
    """
    # 1. Gather Context - Verify node exists
    query = """
    MATCH (t:TargetNode {id: $id})
    RETURN t.id
    """
    results = neo4j_client.execute_query(query, {"id": request.target_node_id})
    if not results:
        raise HTTPException(status_code=404, detail="Target node not found")
    
    # 2. Update status to drafting
    neo4j_client.execute_query("""
        MATCH (n:TargetNode {id: $id}) SET n.status = 'drafting'
    """, {"id": request.target_node_id})
    
    # 3. Trigger Background Task
    service = SynthesisService()
    background_tasks.add_task(service.synthesize_node, request.target_node_id, request.tone_instruction)
    
    return {"status": "queued", "run_id": "background_task"}

@app.get("/synthesis/status/{run_id}")
def get_synthesis_status(run_id: str):
    """
    Polls the status of the generation.
    """
    try:
        status = dagster_client.get_run_status(run_id)
        return {"run_id": run_id, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/synthesis/preview/{node_id}")
def get_synthesis_preview(node_id: str):
    """
    Fetches the generated text (once Dagster is done).
    """
    query = """
    MATCH (n:TargetNode {id: $id})
    RETURN n.content_markdown as content, n.status as status
    """
    results = neo4j_client.execute_query(query, {"id": node_id})
    if not results:
        raise HTTPException(status_code=404, detail="Node not found")
        
    return {"content": results[0]["content"], "status": results[0]["status"]}

# --- F. Curriculum Generator ---

@app.get("/templates/list")
def list_templates():
    """
    List all available curriculum templates from the templates directory.
    
    Returns a list of template names (without .yaml extension).
    """
    import os
    # Use absolute path from project root
    templates_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'templates')
    templates_dir = os.path.abspath(templates_dir)
    
    print(f"[DEBUG] Looking for templates in: {templates_dir}")
    
    try:
        templates = []
        if os.path.exists(templates_dir):
            files = os.listdir(templates_dir)
            print(f"[DEBUG] Found files: {files}")
            
            for filename in files:
                if filename.endswith('.yaml'):
                    template_name = filename[:-5]  # Remove .yaml extension
                    templates.append({
                        "name": template_name,
                        "display_name": template_name.replace('_', ' ').title()
                    })
        else:
            print(f"[WARN] Templates directory does not exist: {templates_dir}")
        
        if not templates:
            # Return default if no templates found
            templates = [{"name": "standard", "display_name": "Standard"}]
        
        print(f"[DEBUG] Returning {len(templates)} templates: {[t['name'] for t in templates]}")
        return {"templates": templates}
    except Exception as e:
        print(f"Error listing templates: {e}")
        import traceback
        traceback.print_exc()
        return {"templates": [{"name": "standard", "display_name": "Standard"}]}

@app.post("/curriculum/generate", response_model=GenerateSkeletonResponse)
def generate_curriculum(request: GenerateSkeletonRequest):
    """
    Generate a consolidated curriculum skeleton from selected source sections.
    
    This endpoint:
    1. Fetches concept summaries from selected sections
    2. Uses DSPy to intelligently merge concepts and eliminate redundancy
    3. Finds best matching slides for each generated section
    4. Creates a Project with TargetNodes in Neo4j
    
    Returns the generated project with suggested source slides.
    """
    from src.services.generator_service import GeneratorService
    
    service = GeneratorService()
    try:
        result = service.generate_skeleton(request.source_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        service.close()


@app.post("/project/generate_skeleton", response_model=ProjectTreeResponse)
def generate_project_skeleton(request: SkeletonRequest):
    """
    Generate a new curriculum project with AI-suggested sections.
    
    This creates a Project with TargetNodes in 'suggestion' status.
    User can review and accept/reject each suggested section.
    """
    from src.services.generator_service import GeneratorService
    
    service = GeneratorService()
    try:
        # Generate skeleton
        result = service.generate_skeleton(
            request.selected_source_ids, 
            title=request.title,
            master_course_id=request.master_course_id,
            template_name=request.template_name or "standard"
        )
        
        # Fetch full project tree
        project_id = result['project_id']
        query = """
        MATCH (p:Project {id: $project_id})
        OPTIONAL MATCH (p)-[:HAS_CHILD]->(t:TargetNode)
        OPTIONAL MATCH (t)-[:SUGGESTED_SOURCE]->(s:Slide)
        WITH p, t, collect(s.id) as suggested_ids
        ORDER BY t.order
        RETURN p.id as project_id, p.title as title, p.status as project_status,
               collect({
                   id: t.id,
                   title: t.title,
                   rationale: t.rationale,
                   status: t.status,
                   order: t.order,
                   is_suggestion: true,
                   is_unassigned: coalesce(t.is_unassigned, false),
                   is_placeholder: coalesce(t.is_placeholder, false),
                   suggested_source_ids: suggested_ids,
                   source_refs: [],
                   parent_id: p.id,
                   content_markdown: null
               }) as nodes
        """
        
        tree_result = neo4j_client.execute_query(query, {"project_id": project_id})
        
        if not tree_result:
            raise HTTPException(status_code=500, detail="Failed to fetch generated project")
        
        return {
            "project_id": project_id,
            "title": tree_result[0]["title"],
            "status": tree_result[0]["project_status"],
            "nodes": tree_result[0]["nodes"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        service.close()


@app.post("/draft/node/accept")
def accept_suggested_node(node_id: str):
    """
    Accept an AI-suggested node, converting it to a permanent draft.
    
    This:
    1. Changes status from 'suggestion' to 'draft'
    2. Converts SUGGESTED_SOURCE relationships to DERIVED_FROM
    3. Makes the suggestion permanent
    """
    query = """
    MATCH (t:TargetNode {id: $node_id})
    WHERE t.status = 'suggestion'
    
    // Update status
    SET t.status = 'draft'
    
    // Convert relationships
    WITH t
    OPTIONAL MATCH (t)-[r:SUGGESTED_SOURCE]->(s:Slide)
    DELETE r
    CREATE (t)-[:DERIVED_FROM]->(s)
    
    RETURN t.id as id, t.status as status, count(s) as sources_accepted
    """
    
    results = neo4j_client.execute_query(query, {"node_id": node_id})
    
    if not results:
        raise HTTPException(status_code=404, detail="Node not found or already accepted")
    
    return {
        "status": "accepted",
        "node_id": results[0]["id"],
        "new_status": results[0]["status"],
        "sources_linked": results[0]["sources_accepted"]
    }

@app.delete("/draft/node/reject")
def reject_suggested_node(node_id: str):
    """
    Reject an AI-suggested node.
    
    For mandatory sections (introduction, mandatory_safety, mandatory_assessment):
    - Clear suggested sources but keep the node
    - Convert to 'draft' status with empty sources
    
    For technical sections:
    - Delete the node entirely
    """
    # First check the section type
    check_query = """
    MATCH (t:TargetNode {id: $node_id})
    WHERE t.status = 'suggestion'
    RETURN t.section_type as section_type
    """
    
    check_results = neo4j_client.execute_query(check_query, {"node_id": node_id})
    
    if not check_results:
        raise HTTPException(status_code=404, detail="Node not found or already processed")
    
    section_type = check_results[0].get("section_type", "technical")
    
    # Mandatory sections: keep node, clear suggestions
    if section_type in ['introduction', 'mandatory_safety', 'mandatory_assessment']:
        query = """
        MATCH (t:TargetNode {id: $node_id})
        WHERE t.status = 'suggestion'
        
        // Delete suggested sources but keep the node
        OPTIONAL MATCH (t)-[r:SUGGESTED_SOURCE]->()
        DELETE r
        
        // Update status to draft
        SET t.status = 'draft'
        
        RETURN t.id as id, t.status as status
        """
        results = neo4j_client.execute_query(query, {"node_id": node_id})
        
        return {
            "status": "cleared",
            "node_id": node_id,
            "action": "suggestions_cleared"
        }
    else:
        # Technical sections: delete entirely
        query = """
        MATCH (t:TargetNode {id: $node_id})
        WHERE t.status = 'suggestion'
        
        DETACH DELETE t
        
        RETURN $node_id as deleted_id
        """
        neo4j_client.execute_query(query, {"node_id": node_id})
        
        return {
            "status": "rejected",
            "node_id": node_id,
            "action": "deleted"
        }

@app.post("/render/trigger")
def trigger_render(request: RenderRequest, background_tasks: BackgroundTasks):
    """
    Triggers the Dagster pipeline to render the project to PPTX/DOCX/PDF.
    """
    # 1. Verify Project
    query = """
    MATCH (p:Project {id: $id})
    RETURN p.id, p.title
    """
    results = neo4j_client.execute_query(query, {"id": request.project_id})
    if not results:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_title = results[0].get("title", "Untitled_Project")
    
    # Generate Filename
    import re
    # Sanitize title
    safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', project_title)
    
    # Default to PPTX for now, as that's the primary desired output
    # In the future, we can add a format parameter to the RenderRequest
    file_extension = request.format.lower()
    if file_extension not in ["pptx", "typ"]:
        file_extension = "pptx"
        
    filename = f"{safe_title}_{request.project_id[:8]}.{file_extension}"
    
    print(f"Triggering render for project {request.project_id} -> {filename}")
    
    # 2. Add Dynamic Partition
    try:
        # Execute GraphQL mutation to add the dynamic partition
        # Must provide repositorySelector and select fields from the Union return type
        mutation = """
        mutation AddPartition($partitionsDefName: String!, $partitionKey: String!, $repoName: String!, $repoLocation: String!) {
          addDynamicPartition(
            partitionsDefName: $partitionsDefName, 
            partitionKey: $partitionKey,
            repositorySelector: {
              repositoryName: $repoName,
              repositoryLocationName: $repoLocation
            }
          ) {
            __typename
            ... on PythonError {
              message
              stack
            }
          }
        }
        """
        variables = {
            "partitionsDefName": "published_files",
            "partitionKey": filename,
            "repoName": "__repository__",
            "repoLocation": "src.pipelines.definitions"
        }
        
        # The client's execute_query takes query and variables
        if hasattr(dagster_client, "execute_query"):
             res = dagster_client.execute_query(mutation, variables)
        else:
             res = dagster_client._execute(mutation, variables)
             
        print(f"Partition added response: {res}")
        
        # Check for GraphQL errors
        if res.get("errors"):
            raise Exception(str(res.get("errors")))
            
        # Check for functional errors (PythonError)
        data = res.get("addDynamicPartition", {})
        if data.get("__typename") == "PythonError":
            raise Exception(f"Dagster error: {data.get('message')}")
        
    except Exception as e:
        print(f"Error adding partition: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register output partition: {str(e)}")

    # 3. Trigger Dagster Job
    # We use tags to specify the partition for the asset job
    dagster_client.submit_job_execution(
        "render_asset_job", 
        run_config={
            "ops": {
                "rendered_course_file": {
                    "config": {"project_id": request.project_id}
                }
            }
        },
        tags={"dagster/partition": filename}
    )
    
    return {"status": "queued", "message": f"Render job submitted for {filename}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
