import json
import os
from typing import Any, Dict
from dagster import asset, AssetExecutionContext
from src.ingestion.assets import CourseArtifactConfig, course_files_partition
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource
from src.ingestion.assets import BUCKET_NAME
from src.semantic.extraction import LLMExtractor

from src.semantic.harmonization import Harmonizer

@asset
def harmonize_concepts(context: AssetExecutionContext, neo4j: Neo4jResource):
    """
    Analyzes all Concepts in the graph and creates CanonicalConcepts to group synonyms.
    """
    context.log.info("Starting Concept Harmonization...")
    
    neo4j_client = neo4j.get_client()
    harmonizer = Harmonizer(neo4j_client)
    
    try:
        clusters = harmonizer.harmonize()
        context.log.info(f"Identified {len(clusters)} clusters.")
        
        harmonizer.apply_clusters(clusters)
        context.log.info("Harmonization applied to Graph.")
        
    except Exception as e:
        context.log.error(f"Harmonization failed: {e}")
        raise
    finally:
        neo4j_client.close()

@asset(partitions_def=course_files_partition)
def build_knowledge_graph(
    context: AssetExecutionContext,
    process_course_artifact: Dict[str, Any],
    minio: MinioResource,
    neo4j: Neo4jResource,
    weaviate: WeaviateResource
):
    """
    Ingests documents into Neo4j using a Two-Pass strategy:
    1. Create Nodes: Extract Structure (Sections) and Content (Slides) independently.
    2. Link & Roll-up: Connect Sections to Slides via page numbers, then roll up Concepts.
    """
    manifest = process_course_artifact
    course_id = manifest["course_id"]
    text_location = manifest["text_location"]
    
    context.log.info(f"Building Knowledge Graph for course: {course_id}")
    
    # 1. Initialize Clients
    minio_client = minio.get_client()
    neo4j_client = neo4j.get_client()
    weaviate_client = weaviate.get_client()
    llm = LLMExtractor() # Assuming Env vars are set for Ollama
    
    # 2. Load Text Data
    import tempfile
    with tempfile.NamedTemporaryFile() as tmp:
        minio_client.download_file(BUCKET_NAME, text_location, tmp.name)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            text_elements = json.load(f)
            
    # 3. Reconstruct Full Text for Outline
    # 3. Reconstruct Full Text for Outline with Page Markers
    full_text_parts = []
    current_page = -1
    
    for el in text_elements:
        text = el.get("text", "")
        if not text:
            continue
            
        page_num = el.get("metadata", {}).get("page_number")
        
        # If we encounter a new page number, add a marker
        if page_num is not None and page_num != current_page:
            full_text_parts.append(f"\n--- Page {page_num} ---\n")
            current_page = page_num
            
        # Format with Type for better Outline Extraction
        type_ = el.get("type", "Text")
        full_text_parts.append(f"[{type_}] {text}")
        
    full_text = "\n".join(full_text_parts)
    
    # --- PASS 1: CREATE NODES ---

    # 4. Extract Outline & Create Course/Section Nodes
    context.log.info("Extracting Outline (Structure)...")
    try:
        outline = llm.extract_outline(full_text)
        
        # Create Course Node
        metadata = manifest.get("metadata", {})
        neo4j_client.execute_query(
            """
            MERGE (c:Course {id: $id}) 
            SET c.title = $title,
                c.business_unit = $business_unit,
                c.version = $version,
                c.delivery_method = $delivery,
                c.duration_hours = $duration,
                c.audience = $audience,
                c.level = $level,
                c.discipline = $discipline
            """,
            {
                "id": course_id, 
                "title": manifest["filename"], # Or metadata.get('course_title') if preferred
                "business_unit": metadata.get("business_unit"),
                "version": metadata.get("version"),
                "delivery": metadata.get("current_delivery_method"),
                "duration": metadata.get("duration_hours"),
                "audience": metadata.get("audience"),
                "level": metadata.get("level_of_material"),
                "discipline": metadata.get("engineering_discipline")
            }
        )
        
        # Create Sections recursively with PAGE RANGES
        def create_section_nodes(sections, parent_id):
            for i, sec in enumerate(sections):
                sec_id = f"{parent_id}_s{i}"
                neo4j_client.execute_query(
                    """
                    MERGE (s:Section {id: $id}) 
                    SET s.title = $title, 
                        s.level = $level,
                        s.start_page = $start_page,
                        s.end_page = $end_page
                    WITH s
                    MATCH (p {id: $parent_id})
                    MERGE (p)-[:HAS_SECTION]->(s)
                    """,
                    {
                        "id": sec_id, 
                        "title": sec.title, 
                        "level": sec.level, 
                        "parent_id": parent_id,
                        # Fallback to 0 if BAML misses start_page, usually handled in prompt
                        "start_page": getattr(sec, 'start_page', 0),
                        "end_page": getattr(sec, 'end_page', None) 
                    }
                )
                create_section_nodes(sec.subsections, sec_id)
                
        create_section_nodes(outline.sections, course_id)
        context.log.info("Outline Structure Created.")
        
    except Exception as e:
        context.log.error(f"Outline extraction failed: {e}")

    # 5. Process Slides/Pages (Content Extraction)
    from collections import defaultdict
    from src.ingestion.layout_detector import detect_layout
    
    pages = defaultdict(list)
    page_elements = defaultdict(list)
    
    current_chunk_page = 1
    current_chunk_size = 0
    CHUNK_LIMIT = 1500
    
    # Organize text by page number
    for el in text_elements:
        metadata = el.get("metadata", {})
        text = el.get("text", "")
        
        
        # Format text with Type for better Concept Extraction
        type_ = el.get("type", "Text")
        formatted_text = f"[{type_}] {text}"
        
        if "page_number" in metadata:
            # Use explicit page number from extractor
            page_num = metadata["page_number"]
            pages[page_num].append(formatted_text)
            page_elements[page_num].append(el)
        else:
            # Fallback: Assign to synthetic page chunks
            pages[current_chunk_page].append(formatted_text)
            page_elements[current_chunk_page].append(el)
            
            current_chunk_size += len(text)
            if current_chunk_size > CHUNK_LIMIT:
                current_chunk_page += 1
                current_chunk_size = 0
        
    # Ensure Weaviate Class exists with text vectorizer enabled
    weaviate_client.ensure_class({
        "class": "SlideText",
        "vectorizer": "text2vec-transformers",  # Enable semantic search
        "moduleConfig": {
            "text2vec-transformers": {
                "vectorizeClassName": False  # Don't vectorize the class name, just the properties
            }
        },
        "properties": [
            {"name": "text", "dataType": ["text"], "moduleConfig": {"text2vec-transformers": {"skip": False, "vectorizePropertyName": False}}},
            {"name": "course_id", "dataType": ["string"], "moduleConfig": {"text2vec-transformers": {"skip": True}}},
            {"name": "slide_id", "dataType": ["string"], "moduleConfig": {"text2vec-transformers": {"skip": True}}},
        ]
    })

    # Process each page/slide
    for page_num, texts in pages.items():
        slide_text = "\n".join(texts)
        if not slide_text.strip():
            continue
            
        slide_id = f"{course_id}_p{page_num}"
        context.log.info(f"Processing Slide {page_num} (ID: {slide_id})")
        
        # Detect Layout
        elements = page_elements.get(page_num, [])
        layout_style = detect_layout(elements)
        
        # Derive asset type
        filename = manifest["filename"]
        file_ext = os.path.splitext(filename)[1].upper().replace('.', '')
        asset_type = file_ext if file_ext in ["PDF", "PPTX", "DOCX", "PPT", "DOC"] else "Unknown"
        
        # Create Slide Node (Atomic Unit)
        neo4j_client.execute_query(
            """
            MATCH (c:Course {id: $course_id})
            MERGE (sl:Slide {id: $id})
            SET sl.number = $page_num, 
                sl.text = $text,
                sl.asset_type = $asset_type,
                sl.layout_style = $layout_style,
                sl.elements = $elements_json
            MERGE (c)-[:HAS_SLIDE]->(sl)
            """,
            {"course_id": course_id, "id": slide_id, "page_num": page_num, "text": slide_text[:500], "asset_type": asset_type, "layout_style": layout_style, "elements_json": json.dumps(elements)}
        )
        
        # Extract Concepts (BAML)
        try:
            content = llm.extract_concepts(slide_text)
            
            for concept in content.concepts:
                salience = getattr(concept, 'salience', 0.5)
                
                neo4j_client.execute_query(
                    """
                    MERGE (con:Concept {name: $name})
                    SET con.description = $desc
                    WITH con
                    MATCH (sl:Slide {id: $slide_id})
                    MERGE (sl)-[t:TEACHES]->(con)
                    SET t.salience = $salience
                    """,
                    {
                        "name": concept.name, 
                        "desc": concept.description, 
                        "slide_id": slide_id,
                        "salience": salience
                    }
                )
        except Exception as e:
            context.log.error(f"Concept extraction failed for slide {slide_id}: {e}")

        # Vector Indexing
        try:
            weaviate_client.add_object(
                data_object={
                    "text": slide_text,
                    "course_id": course_id,
                    "slide_id": slide_id
                },
                class_name="SlideText"
            )
        except Exception as e:
            context.log.error(f"Vector indexing failed for slide {slide_id}: {e}")

    # --- PASS 2: LINK & ROLL-UP (The Fix) ---
    context.log.info("Pass 2: Linking Structure to Content...")
    
    try:
        # 1. Link Slides to Sections based on Page Numbers
        # This is the critical query that connects the "Outline" to the "Content"
        link_query = """
        MATCH (c:Course {id: $course_id})-[:HAS_SECTION*]->(sec:Section)
        MATCH (c)-[:HAS_SLIDE]->(s:Slide)
        WHERE s.number >= sec.start_page 
          AND (sec.end_page IS NULL OR s.number <= sec.end_page)
        MERGE (sec)-[:HAS_SLIDE]->(s)
        """
        neo4j_client.execute_query(link_query, {"course_id": course_id})
        context.log.info("Linked Slides to Sections.")

        # 2. Roll-up Concepts to Sections (COVERS Relationship)
        # Allows API to query "What does Section 1.1 cover?" without reading slides
        rollup_query = """
        MATCH (c:Course {id: $course_id})-[:HAS_SECTION*]->(sec:Section)
        MATCH (sec)-[:HAS_SLIDE]->(s:Slide)-[t:TEACHES]->(con:Concept)
        WITH sec, con, avg(t.salience) as avg_score, count(s) as frequency
        MERGE (sec)-[r:COVERS]->(con)
        SET r.score = avg_score, r.frequency = frequency
        """
        neo4j_client.execute_query(rollup_query, {"course_id": course_id})
        context.log.info("Rolled up Concepts to Sections.")

        # 3. Create Lightweight Summaries (Property for Fast API access)
        summary_query = """
        MATCH (c:Course {id: $course_id})-[:HAS_SECTION*]->(sec:Section)
        OPTIONAL MATCH (sec)-[r:COVERS]->(con:Concept)
        WITH sec, con, r.score as score
        ORDER BY score DESC
        WITH sec, collect(con.name) as concepts
        SET sec.concept_summary = concepts[0..10]
        """
        neo4j_client.execute_query(summary_query, {"course_id": course_id})
        context.log.info("Created Concept Summaries.")

    except Exception as e:
        context.log.error(f"Pass 2 Linking failed: {e}")

    neo4j_client.close()
    return {"course_id": course_id, "status": "processed"}
