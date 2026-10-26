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

from src.publishing.render import FORMATS, render_project

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
    
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in FORMATS:
        raise ValueError(f"Unsupported render format for {filename}")

    with tempfile.TemporaryDirectory() as temp_dir:
        local_path = os.path.join(temp_dir, filename)
        render_project(project_id, ext, config.template_name, local_path,
                       neo4j_client=neo4j_client, minio_client=minio_client, reader=None)

        # 4. Upload to MinIO
        bucket_name = "published"
        minio_client.ensure_bucket(bucket_name)
        minio_client.upload_file(bucket_name, filename, local_path)
        
    context.log.info(f"Successfully published {filename} to bucket {bucket_name}")
    
    return {
        "filename": filename,
        "project_id": project_id,
        "url": f"http://{minio.endpoint}/{bucket_name}/{filename}",
    }
