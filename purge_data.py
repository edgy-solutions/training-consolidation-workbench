import sys
import os

# Add src to path so we can import from it
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient

def purge_neo4j():
    print("Purging Neo4j data...")
    try:
        neo4j = Neo4jClient()
        # Detach delete all nodes
        neo4j.execute_query("MATCH (n) DETACH DELETE n")
        print(" - All nodes and relationships deleted.")
        neo4j.close()
    except Exception as e:
        print(f" - Error purging Neo4j: {e}")

def purge_weaviate():
    print("Purging Weaviate data...")
    try:
        weaviate = WeaviateClient()
        # Delete all classes/schema
        weaviate.client.schema.delete_all()
        print(" - All Weaviate classes deleted.")
    except Exception as e:
        print(f" - Error purging Weaviate: {e}")

if __name__ == "__main__":
    print("WARNING: This will delete ALL data in Neo4j and Weaviate.")
    confirm = input("Are you sure? (type 'yes' to confirm): ")
    
    if confirm.lower() == 'yes':
        purge_neo4j()
        purge_weaviate()
        print("Purge complete.")
    else:
        print("Purge cancelled.")
