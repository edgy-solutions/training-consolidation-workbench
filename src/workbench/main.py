from fastapi import FastAPI, HTTPException, Query
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
    ConceptNode, SourceSlide, TargetDraftNode, SynthesisRequest
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

@app.get("/source/slide/{slide_id}", response_model=SourceSlide)
def get_slide_details(slide_id: str):
    """
    Returns metadata + S3 Presigned URL for the slide image.
    """
    # 1. Fetch Metadata and Concepts from Neo4j
    query = """
    MATCH (s:Slide {id: $id})
    OPTIONAL MATCH (s)-[:TEACHES]->(c:Concept)
    RETURN s.id as id, s.number as number, s.text as text, collect(c) as concepts
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
        if c: # check if not null
            concepts.append(ConceptNode(name=c.get("name", ""), domain="General")) # Domain not in graph yet?
            
    return SourceSlide(
        id=row["id"],
        s3_url=s3_url,
        text_preview=row["text"][:200] if row["text"] else "",
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
    """
    import uuid
    node_id = str(uuid.uuid4())
    
    query = """
    MATCH (parent {id: $parent_id})
    CREATE (child:TargetNode {id: $id, title: $title, status: "empty", content_markdown: ""})
    MERGE (parent)-[:HAS_CHILD]->(child)
    RETURN child.id as id, child.title as title, child.status as status
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
        status=row["status"]
    )

@app.put("/draft/node/map")
def map_slides_to_node(node_id: str, slide_ids: List[str]):
    """
    Links "Source Slides" to a "Target Node" (Drag & Drop action).
    """
    query = """
    MATCH (t:TargetNode {id: $node_id})
    MATCH (s:Slide) WHERE s.id IN $slide_ids
    MERGE (t)-[:DERIVED_FROM]->(s)
    """
    neo4j_client.execute_query(query, {"node_id": node_id, "slide_ids": slide_ids})
    return {"status": "success", "mapped_slides": len(slide_ids)}

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
    RETURN n.id as id, n.title as title, n.status as status, n.content_markdown as content, 
           parent.id as parent_id, collect(s.id) as source_refs
    """
    results = neo4j_client.execute_query(query, {"project_id": project_id})
    
    nodes = []
    for row in results:
        # Project node itself might be returned if matched by *0.. 
        # but if it's :Project and not :TargetNode it might depend on labels.
        # In create_draft_project we added :TargetNode label to Project too? Yes.
        nodes.append(TargetDraftNode(
            id=row["id"],
            title=row["title"],
            parent_id=row["parent_id"],
            status=row["status"] or "empty",
            content_markdown=row["content"],
            source_refs=row["source_refs"]
        ))
    return nodes

# --- C. The Synthesis Module ---

@app.post("/synthesis/trigger")
def trigger_synthesis(request: SynthesisRequest):
    """
    Triggers the DSPy generation logic via Dagster.
    """
    # 1. Gather Context - Verify node exists
    query = """
    MATCH (t:TargetNode {id: $id})
    RETURN t.id
    """
    results = neo4j_client.execute_query(query, {"id": request.target_node_id})
    if not results:
        raise HTTPException(status_code=404, detail="Target node not found")
    
    # 2. Fire and Forget - Trigger Dagster Job
    try:
        run_config = {
            "ops": {
                "synthesize_node": {  # Assuming op name
                    "config": {
                        "target_node_id": request.target_node_id,
                        "tone": request.tone_instruction
                    }
                }
            }
        }
        
        # Submit job
        # Note: Job name must match what is defined in Dagster
        job_name = "synthesize_node_job" 
        run_id = dagster_client.submit_job_execution(
            job_name=job_name,
            run_config=run_config
        )
        
        # Update status to drafting
        neo4j_client.execute_query("""
            MATCH (n:TargetNode {id: $id}) SET n.status = 'drafting'
        """, {"id": request.target_node_id})
        
        return {"status": "queued", "run_id": run_id}
        
    except DagsterGraphQLClientError as e:
         raise HTTPException(status_code=500, detail=f"Dagster Error: {str(e)}")
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
