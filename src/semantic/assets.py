import json
import os
from typing import Any, Dict
from dagster import asset, AssetExecutionContext
from src.storage.dagster_resources import MinioResource, Neo4jResource, WeaviateResource
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
