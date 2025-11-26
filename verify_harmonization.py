import os
import sys
import time
from src.storage.neo4j import Neo4jClient

def verify_harmonization():
    client = Neo4jClient()
    
    try:
        print("Seeding conflicting concepts...")
        # Create conflicting terms directly in Neo4j
        # Scenario: Safety concepts across BUs
        conflicts = [
            "Emergency Stop", "E-Stop", "Emergency Halt", 
            "Voltage Lockout", "LOTO", "Lock Out Tag Out"
        ]
        
        for term in conflicts:
            client.execute_query(
                "MERGE (c:Concept {name: $name}) SET c.description = 'Safety procedure.'",
                {"name": term}
            )
            
        print("Seed data created. Please run the 'harmonize_concepts_job' in Dagster now.")
        print("Waiting 10 seconds for you to trigger it via UI (or manually via CLI if we could)...")
        
        # In a real script we might trigger via graphql, but for now we verify the result *after* user action
        # or we can try to run the harmonization logic directly here for verification?
        # Let's run the Harmonizer class directly to verify the LOGIC, independent of Dagster.
        
        from src.semantic.harmonization import Harmonizer
        harmonizer = Harmonizer(client)
        
        print("Running Harmonizer logic directly...")
        clusters = harmonizer.harmonize()
        
        print(f"Found {len(clusters)} clusters.")
        for c in clusters:
            print(f"  - {c.canonical_name}: {c.source_concepts}")
            
        if len(clusters) > 0:
            harmonizer.apply_clusters(clusters)
            
            # Verify Graph
            results = client.execute_query(
                "MATCH (c:Concept)-[:ALIGNS_TO]->(cc:CanonicalConcept) RETURN c.name, cc.name"
            )
            if len(results) > 0:
                print(f"SUCCESS: Found {len(results)} alignment relationships.")
                sys.exit(0)
            else:
                print("FAILURE: No ALIGNS_TO relationships found.")
                sys.exit(1)
        else:
            print("WARNING: No clusters found. DSPy might need tuning or model is not responding.")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    verify_harmonization()
