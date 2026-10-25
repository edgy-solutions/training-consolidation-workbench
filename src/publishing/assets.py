import os
import json
import tempfile
from pathlib import Path
from dagster import asset, Config, DynamicPartitionsDefinition, AssetExecutionContext
from src.storage.dagster_resources import MinioResource, Neo4jResource

# Define the dynamic partition
published_files_partition = DynamicPartitionsDefinition(name="published_files")

class RenderConfig(Config):
    project_id: str
    template_name: str = "standin"

from src.publishing.typst_generator import generate_typst_document
from src.publishing.course import GraphLookup, MinioImageResolver, build_course
from src.publishing.deck_export import DEFAULT_MAPPING, export_deck, load_mapping

TEMPLATE_BUCKET = "cib-sources"

COURSE_NODES_QUERY = """
MATCH (p:Project {id: $project_id})-[:HAS_CHILD*]->(n:TargetNode)
MATCH (parent)-[:HAS_CHILD]->(n)
OPTIONAL MATCH (n)-[:DERIVED_FROM]->(s:Slide)
RETURN n.id AS id, parent.id AS parent_id, n.title AS title, n.order AS order,
       n.content_markdown AS content_markdown, n.key_concepts AS key_concepts,
       coalesce(n.is_unassigned, false) AS is_unassigned,
       collect(DISTINCT s.id) AS source_refs
"""


def fetch_course_nodes(neo4j_client, project_id):
    return [dict(row) for row in neo4j_client.execute_query(COURSE_NODES_QUERY, {"project_id": project_id})]


def _download(minio_client, key, dest):
    obj = minio_client.get_object(TEMPLATE_BUCKET, key)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(obj.read())
    finally:
        obj.close()
        obj.release_conn()


def load_template_mapping(minio_client, name, temp_dir):
    """The mapping file for a template name: the stand-in from the repo, any other from cib-sources."""
    if name == "standin":
        return DEFAULT_MAPPING
    base = f"templates/{name}/"
    local = Path(temp_dir) / "template" / name
    _download(minio_client, base + "deck-template.yaml", local / "deck-template.yaml")
    mapping = load_mapping(local / "deck-template.yaml")
    if mapping.template:
        _download(minio_client, base + mapping.template, local / mapping.template)
    return local / "deck-template.yaml"

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
    nodes_query = """
    MATCH (p:Project {id: $project_id})
    OPTIONAL MATCH (p)-[:HAS_CHILD*]->(n:TargetNode)
    RETURN n.title as title, n.content_markdown as content_markdown, n.target_layout as target_layout, n.order as order
    ORDER BY n.order
    """
    nodes_results = neo4j_client.execute_query(nodes_query, {"project_id": project_id})
    
    nodes = [
        {
            "title": row["title"],
            "content_markdown": row["content_markdown"],
            "target_layout": row.get("target_layout"),
            "order": row["order"]
        }
        for row in nodes_results if row["title"]
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
            mapping_path = load_template_mapping(minio_client, config.template_name, temp_dir)
            course = build_course(
                {"id": project_id, "title": project_title},
                fetch_course_nodes(neo4j_client, project_id),
                GraphLookup(neo4j_client),
            )
            resolver = MinioImageResolver(minio_client, os.getenv("BUCKET_NAME", "processing-artifacts"))
            export_deck(course, mapping_path, local_path, resolver)

        else:
            # Default/Fallback
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(f"Project: {project_title}\n\n")
                for node in nodes:
                    f.write(f"--- {node['title']} ---\n")
                    f.write(f"{node.get('content_markdown', '')}\n\n")

        # 4. Upload to MinIO
        bucket_name = "published"
        minio_client.ensure_bucket(bucket_name)
        minio_client.upload_file(bucket_name, filename, local_path)
        
    context.log.info(f"Successfully published {filename} to bucket {bucket_name}")
    
    return {
        "filename": filename,
        "project_id": project_id,
        "url": f"http://{minio.endpoint}/{bucket_name}/{filename}",
        "node_count": len(nodes)
    }
