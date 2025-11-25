#!/bin/bash

# Verification Script for Module 2 (Linux/macOS)
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
cat <<EOF > verify_graph.py
import os
import sys
from src.storage.neo4j import Neo4jClient

def verify_graph():
    try:
        client = Neo4jClient()
        courses = client.execute_query("MATCH (n:Course) RETURN n LIMIT 5")
        print(f"Found {len(courses)} Course nodes.")
        
        concepts = client.execute_query("MATCH (n:Concept) RETURN n LIMIT 5")
        print(f"Found {len(concepts)} Concept nodes.")
        
        if len(courses) > 0 and len(concepts) > 0:
            print("SUCCESS: Graph populated.")
            sys.exit(0)
        else:
            print("WARNING: Graph empty. Did you run the pipeline?")
            sys.exit(1)
    except Exception as e:
        print(f"Error connecting to Neo4j: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_graph()
EOF

# 4. Run
echo "Querying Neo4j..."
VENV_PYTHON=".venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON verify_graph.py
else
    python verify_graph.py
fi
