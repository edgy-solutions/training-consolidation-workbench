import os
from dotenv import load_dotenv
from dagster import Definitions, load_assets_from_modules, define_asset_job

# Load env vars from .env file if present
load_dotenv()

from src.ingestion import assets as ingestion_assets
from src.semantic import assets as semantic_assets
from src.ingestion.sensors import course_upload_sensor
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource

all_assets = load_assets_from_modules([ingestion_assets, semantic_assets])

# Define the job that the sensor triggers
process_course_job = define_asset_job(
    name="process_course_job",
    selection=["process_course_artifact", "build_knowledge_graph"]
)

defs = Definitions(
    assets=all_assets,
    jobs=[process_course_job],
    sensors=[course_upload_sensor],
    resources={
        "minio": MinioResource(),
        "neo4j": Neo4jResource(),
        "weaviate": WeaviateResource(),
    },
)
