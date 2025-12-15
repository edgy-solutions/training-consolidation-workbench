import os
import json
import yaml
import tempfile
from dagster import asset, Config, DynamicPartitionsDefinition, AssetExecutionContext
from src.storage.dagster_resources import MinioResource, Neo4jResource

# Define the dynamic partition
published_files_partition = DynamicPartitionsDefinition(name="published_files")

class RenderConfig(Config):
    project_id: str
    template_name: str = "master_engineering" # Default to a valid yaml config name

from src.publishing.typst_generator import generate_typst_document
from src.publishing.pptx_generator import PptxGenerator

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
        
        # Determine Template Logic
        selected_template = config.template_name
        
        # Load YAML Configuration from MinIO
        yaml_config = {}
        template_pptx_path = None
        
        # Define bucket for templates
        SOURCE_BUCKET = "cib-sources"
        
        try:
            # 1. Download YAML Config
            # e.g. templates/master_engineering.yaml
            yaml_key = f"templates/{selected_template}.yaml"
            
            # Check if exists (or just try to get it)
            try:
                obj = minio_client.get_object(SOURCE_BUCKET, yaml_key)
                yaml_content = obj.read()
                yaml_config = yaml.safe_load(yaml_content) or {}
                context.log.info(f"Loaded configuration from {yaml_key}")
            except Exception as e:
                # If .yaml not found, check if it was .yml
                yaml_key = f"templates/{selected_template}.yml"
                try:
                    obj = minio_client.get_object(SOURCE_BUCKET, yaml_key)
                    yaml_content = obj.read()
                    yaml_config = yaml.safe_load(yaml_content) or {}
                    context.log.info(f"Loaded configuration from {yaml_key}")
                except:
                    context.log.warning(f"Configuration {selected_template}.yaml not found. Using defaults.")
            
            # 2. Download Referenced PPTX Template
            # Config should have 'template_path': "templates/Training Template.pptx"
            pptx_key = yaml_config.get("template_path")
            
            if pptx_key:
                try:
                    pptx_obj = minio_client.get_object(SOURCE_BUCKET, pptx_key)
                    template_pptx_path = os.path.join(temp_dir, "base_template.pptx")
                    with open(template_pptx_path, "wb") as f:
                        for chunk in pptx_obj.stream(32*1024):
                            f.write(chunk)
                    context.log.info(f"Downloaded base template from {pptx_key}")
                except Exception as e:
                     context.log.error(f"Failed to download referenced template {pptx_key}: {e}")
            
        except Exception as outer_e:
            context.log.error(f"Template loading process failed: {outer_e}")


        if filename.lower().endswith(".typ"):
             # Generate Typst source
            typst_content = generate_typst_document(project_title, nodes)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(typst_content)
                
        elif filename.lower().endswith(".pptx"):
            # Generate PPTX using Class
            generator = PptxGenerator(config=yaml_config, template_file_path=template_pptx_path)
            generator.generate(project_title, nodes, local_path)
            
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
