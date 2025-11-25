import json
from typing import Any, Dict
from dagster import asset, AssetExecutionContext
from src.ingestion.assets import CourseArtifactConfig
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource
from src.ingestion.assets import BUCKET_NAME
from src.semantic.extraction import LLMExtractor

@asset
def build_knowledge_graph(
    context: AssetExecutionContext,
    process_course_artifact: Dict[str, Any],
    minio: MinioResource,
    neo4j: Neo4jResource,
    weaviate: WeaviateResource
):
    """
    Takes the manifest from ingestion, runs semantic extraction, and populates the graph.
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
    # Simple concatenation of text elements
    full_text = "\n".join([el.get("text", "") for el in text_elements if el.get("text")])
    
    # 4. Extract Outline & Create Course/Section Nodes
    context.log.info("Extracting Outline...")
    try:
        outline = llm.extract_outline(full_text)
        
        # Create Course Node
        neo4j_client.execute_query(
            "MERGE (c:Course {id: $id}) SET c.title = $title",
            {"id": course_id, "title": manifest["filename"]}
        )
        
        # Create Sections recursively
        def create_section_nodes(sections, parent_id):
            for i, sec in enumerate(sections):
                sec_id = f"{parent_id}_s{i}"
                neo4j_client.execute_query(
                    """
                    MERGE (s:Section {id: $id}) 
                    SET s.title = $title, s.level = $level
                    WITH s
                    MATCH (p {id: $parent_id})
                    MERGE (p)-[:HAS_SECTION]->(s)
                    """,
                    {"id": sec_id, "title": sec.title, "level": sec.level, "parent_id": parent_id}
                )
                create_section_nodes(sec.subsections, sec_id)
                
        create_section_nodes(outline.sections, course_id)
        context.log.info("Outline Graph Created.")
        
    except Exception as e:
        context.log.error(f"Outline extraction failed: {e}")

    # 5. Process Slides/Pages (Concept Extraction & Vector Indexing)
    # Group elements by page number (if available) or just chunk?
    # Unstructured usually provides "page_number" in metadata.
    
    from collections import defaultdict
    pages = defaultdict(list)
    for el in text_elements:
        page_num = el.get("metadata", {}).get("page_number", 1)
        pages[page_num].append(el.get("text", ""))
        
    # Ensure Weaviate Class exists
    weaviate_client.ensure_class({
        "class": "SlideText",
        "properties": [
            {"name": "text", "dataType": ["text"]},
            {"name": "course_id", "dataType": ["string"]},
            {"name": "slide_id", "dataType": ["string"]},
        ]
    })

    for page_num, texts in pages.items():
        slide_text = "\n".join(texts)
        if not slide_text.strip():
            continue
            
        slide_id = f"{course_id}_p{page_num}"
        context.log.info(f"Processing Slide {page_num} (ID: {slide_id})")
        
        # Create Slide Node
        neo4j_client.execute_query(
            """
            MATCH (c:Course {id: $course_id})
            MERGE (sl:Slide {id: $id})
            SET sl.number = $page_num, sl.text = $text
            MERGE (c)-[:HAS_SLIDE]->(sl)
            """,
            {"course_id": course_id, "id": slide_id, "page_num": page_num, "text": slide_text[:500]}
        )
        
        # Extract Concepts
        try:
            content = llm.extract_concepts(slide_text)
            
            # Create Concept Nodes & Links
            for concept in content.concepts:
                neo4j_client.execute_query(
                    """
                    MERGE (con:Concept {name: $name})
                    SET con.description = $desc
                    WITH con
                    MATCH (sl:Slide {id: $slide_id})
                    MERGE (sl)-[:TEACHES]->(con)
                    """,
                    {"name": concept.name, "desc": concept.description, "slide_id": slide_id}
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

    neo4j_client.close()
    return {"course_id": course_id, "status": "processed"}
