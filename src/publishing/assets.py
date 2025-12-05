import os
import json
import tempfile
from dagster import asset, Config, DynamicPartitionsDefinition, AssetExecutionContext
from src.storage.dagster_resources import MinioResource, Neo4jResource

# Define the dynamic partition
published_files_partition = DynamicPartitionsDefinition(name="published_files")

class RenderConfig(Config):
    project_id: str

from src.publishing.typst_generator import generate_typst_document
from src.publishing.pptx_generator import generate_pptx_document

@asset(partitions_def=published_files_partition)
def rendered_course_file(context: AssetExecutionContext, config: RenderConfig, minio: MinioResource, neo4j: Neo4jResource):
    """
    Renders the course project to a file (PDF/PPTX/Typst) and publishes it to MinIO.
    The partition key is the filename (e.g., "My_Course_v1.pptx").
    """
    filename = context.partition_key
    project_id = config.project_id
    
    context.log.info(f"Rendering project {project_id} to {filename}")
    
    neo4j_client = neo4j.get_client()
    minio_client = minio.get_client()
    
    # 1. Fetch Project Metadata
    query = "MATCH (p:Project {id: $id}) RETURN p.title as title"
    results = neo4j_client.execute_query(query, {"id": project_id})
    
    if not results:
        raise Exception(f"Project {project_id} not found")
        
    project_title = results[0]["title"]
    context.log.info(f"Found project: {project_title}")
    
    # 2. Fetch Project Nodes (Content)
    # simplified query to get flat list of nodes
    nodes_query = """
    MATCH (p:Project {id: $project_id})
    OPTIONAL MATCH (p)-[:HAS_CHILD*]->(n:TargetNode)
    RETURN n.title as title, n.content_markdown as content_markdown, n.order as order
    ORDER BY n.order
    """
    nodes_results = neo4j_client.execute_query(nodes_query, {"project_id": project_id})
    
    # Convert to list of dicts
    nodes = [
        {
            "title": row["title"],
            "content_markdown": row["content_markdown"],
            "order": row["order"]
        }
        for row in nodes_results if row["title"] # Filter out empty/orphan nodes if any
    ]
    context.log.info(f"Fetched {len(nodes)} nodes for rendering.")

    # 3. Render
    with tempfile.TemporaryDirectory() as temp_dir:
        local_path = os.path.join(temp_dir, filename)
        
        if filename.lower().endswith(".typ"):
            # Generate Typst source
            typst_content = generate_typst_document(project_title, nodes)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(typst_content)
                
        elif filename.lower().endswith(".pptx"):
            # Generate PPTX
            generate_pptx_document(project_title, nodes, local_path)
            
        else:
            # Default/Fallback (Text file for unknown extensions)
            context.log.warning(f"Unknown extension for {filename}. Creating text dump.")
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(f"Project: {project_title}\n\n")
                for node in nodes:
                    f.write(f"--- {node['title']} ---\n")
                    f.write(f"{node.get('content_markdown', '')}\n\n")

        # 4. Upload to MinIO
        bucket_name = "published"
        
        # Ensure bucket exists
        # Ensure bucket exists
        minio_client.ensure_bucket(bucket_name)
            
        # Upload
        minio_client.upload_file(bucket_name, filename, local_path)
        
    context.log.info(f"Successfully published {filename} to bucket {bucket_name}")
    
    return {
        "filename": filename,
        "project_id": project_id,
        "url": f"http://{minio.endpoint}/{bucket_name}/{filename}",
        "node_count": len(nodes)
    }
