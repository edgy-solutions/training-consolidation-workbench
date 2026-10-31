import os
from dotenv import load_dotenv
from dagster import Definitions, load_assets_from_modules, define_asset_job, DynamicPartitionsDefinition

# Load env vars from .env file if present
load_dotenv()

from src.publishing import assets as publishing_assets
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource

all_assets = load_assets_from_modules([publishing_assets])

# Define the job for rendering published files
render_asset_job = define_asset_job(
    name="render_asset_job",
    selection=["rendered_course_file"]
)

# Concept alignment (CanonicalConcept, ALIGNS_TO) is doc-tools' concepts.normalise pass (contract §4.7); the workbench only reviews proposals.

from src.workbench.operations import synthesize_node
from dagster import job

@job(name="synthesize_node_job")
def synthesize_node_job():
    synthesize_node()

defs = Definitions(
    assets=all_assets,
    jobs=[synthesize_node_job, render_asset_job],
    resources={
        "minio": MinioResource(),
        "neo4j": Neo4jResource(),
        "weaviate": WeaviateResource(),
    },
)
