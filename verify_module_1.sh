#!/bin/bash

# Verification Script for Module 1 (Linux/macOS)
set -e

# 1. Check Docker
echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "Docker is not found. Please install Docker."
    exit 1
fi

# 2. Start MinIO
echo "Starting MinIO..."
docker-compose up -d minio

# 3. Install Python Dependencies
echo "Installing Python dependencies..."
pip install -e .

# 4. Create Test Data
echo "Creating test data in data/raw..."
mkdir -p data/raw
echo "Hello, this is a test document for the training consolidation workbench." > data/raw/test_doc.txt

# 5. Run Dagster Materialization
echo "Running Dagster asset 'raw_documents'..."
# Set default env vars for local dev if not set
export MINIO_ENDPOINT="localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"

dagster asset materialize -m src.pipelines.definitions --select raw_documents

echo "Success! Assets materialized."
echo "You can view the MinIO console at http://localhost:9001 to verify the 'images', 'text', and 'manifests' buckets."
