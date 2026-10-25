#!/bin/bash

# Verification Script for Module 3 (Linux/macOS)
set -e

# 1. Infrastructure
if command -v docker &> /dev/null; then
    echo "Checking Docker services..."
    docker-compose up -d
fi

# 2. Install Deps
echo "Updating dependencies..."
if command -v uv &> /dev/null; then
    uv pip install -e .
else
    pip install -e .
fi

# 3. Python Verification
cat <<EOF > verify_harmonization.py
import os
import sys
import time
from src.storage.neo4j import Neo4jClient
from src.semantic.harmonization import Harmonizer

def verify_harmonization():
    client = Neo4jClient()
    
    try:
        print("Seeding conflicting concepts...")
        # Scenario: Safety concepts across BUs
        conflicts = [
            "Emergency Stop", "E-Stop", "Emergency Halt", 
            "Voltage Lockout", "LOTO", "Lock Out Tag Out"
        ]
        
        for term in conflicts:
            client.execute_query(
                "MERGE (c:Concept {name: \$name}) SET c.description = 'Safety procedure.'",
                {"name": term}
            )
            
        print("Seed data created. Running Harmonizer logic directly...")
        
        harmonizer = Harmonizer(client)
        clusters = harmonizer.harmonize()
        
        print(f"Found {len(clusters)} clusters.")
        for c in clusters:
            print(f"  - {c.canonical_name}: {c.source_concepts}")
            
        if len(clusters) > 0:
            harmonizer.apply_clusters(clusters)
            
            # Verify Graph
            results = client.execute_query(
                "MATCH (cc:CanonicalConcept)-[:ALIGNS_TO]->(c:Concept) RETURN c.name, cc.name"
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
EOF

# 4. Run
echo "Running Verification..."
VENV_PYTHON=".venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON verify_harmonization.py
else
    python verify_harmonization.py
fi
