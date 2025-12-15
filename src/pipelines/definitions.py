import os
from dotenv import load_dotenv
from dagster import Definitions, load_assets_from_modules, define_asset_job, DynamicPartitionsDefinition

# Load env vars from .env file if present
load_dotenv()

from src.ingestion.assets import course_files_partition
from src.ingestion import assets as ingestion_assets
from src.semantic import assets as semantic_assets
from src.publishing import assets as publishing_assets
from src.ingestion.sensors import course_upload_sensor
from src.semantic.sensors import unharmonized_concepts_sensor
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource

all_assets = load_assets_from_modules([ingestion_assets, semantic_assets, publishing_assets])

# Define the job that the sensor triggers
process_course_job = define_asset_job(
    name="process_course_job",
    selection=["process_course_artifact", "build_knowledge_graph"]
)

# Define the job for rendering published files
render_asset_job = define_asset_job(
    name="render_asset_job",
    selection=["rendered_course_file"]
)

# Define the harmonization job (manual trigger or scheduled)
harmonize_concepts_job = define_asset_job(
    name="harmonize_concepts_job",
    selection="harmonize_concepts"
)

from src.workbench.operations import synthesize_node
from dagster import job

@job(name="synthesize_node_job")
def synthesize_node_job():
    synthesize_node()

defs = Definitions(
    assets=all_assets,
    jobs=[process_course_job, harmonize_concepts_job, synthesize_node_job, render_asset_job],
    sensors=[course_upload_sensor, unharmonized_concepts_sensor],
    resources={
        "minio": MinioResource(),
        "neo4j": Neo4jResource(),
        "weaviate": WeaviateResource(),
    },
)
