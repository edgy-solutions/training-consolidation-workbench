#!/bin/bash
# Start all infrastructure (MinIO, Neo4j, Weaviate)
echo "Starting all infrastructure..."
docker-compose up -d

# Re-install dependencies (to pick up weaviate-client downgrade)
echo "Ensuring dependencies are up to date..."
uv pip install -e .

echo "Infrastructure started. You can now run the sensor verification."
