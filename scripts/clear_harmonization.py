"""
Script to clear old harmonization data from Neo4j.
Run this before re-running harmonize_concepts_job with the updated prompt.
"""
from src.storage.neo4j import Neo4jClient

def clear_harmonization_data():
    client = Neo4jClient()
    
    try:
        # 1. Delete all ALIGNS_TO relationships
        print("Deleting ALIGNS_TO relationships...")
        result = client.execute_query(
            "MATCH ()-[r:ALIGNS_TO]->() DELETE r RETURN count(r) as deleted"
        )
        deleted_rels = result[0]["deleted"] if result else 0
        print(f"  Deleted {deleted_rels} relationships")
        
        # 2. Delete all CanonicalConcept nodes
        print("Deleting CanonicalConcept nodes...")
        result = client.execute_query(
            "MATCH (cc:CanonicalConcept) DETACH DELETE cc RETURN count(cc) as deleted"
        )
        deleted_nodes = result[0]["deleted"] if result else 0
        print(f"  Deleted {deleted_nodes} nodes")
        
        print("\n✅ Harmonization data cleared!")
        print("You can now re-run harmonize_concepts_job in Dagster.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    clear_harmonization_data()
