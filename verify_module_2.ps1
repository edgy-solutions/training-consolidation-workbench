# Verification Script for Module 2 (PowerShell)

# 1. Check Infrastructure
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "Checking Docker services..."
    docker-compose up -d
}

# 2. Install Deps (Module 2 added new ones)
Write-Host "Updating dependencies..."
uv pip install -e .

# 3. Python Script to Verify Neo4j Data
$VerifyScript = @"
import os
import sys
from src.storage.neo4j import Neo4jClient

def verify_graph():
    try:
        client = Neo4jClient()
        # Check for any Course nodes
        courses = client.execute_query("MATCH (n:Course) RETURN n LIMIT 5")
        print(f"Found {len(courses)} Course nodes.")
        
        # Check for Concepts
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
"@

$VerifyScript | Out-File -Encoding UTF8 verify_graph.py

# 4. Run Verification
Write-Host "Querying Neo4j..."
$VENV_PYTHON = if ($IsWindows) { ".venv\Scripts\python.exe" } else { ".venv/bin/python" }
& $VENV_PYTHON verify_graph.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Module 2 Verification Passed."
} else {
    Write-Host "Module 2 Verification Failed (or data missing)."
}
