#!/bin/bash

# Verification Script for Module 1 (Linux/macOS)
set -e

# 1. Infrastructure Check (Skip Docker if running in K8s/External MinIO)
if [ -z "$USE_EXTERNAL_MINIO" ]; then
    echo "Running in Local Mode (Docker)..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo "Docker is not found. Please install Docker."
        exit 1
    fi

    # Start MinIO
    echo "Starting MinIO..."
    docker-compose up -d minio
    
    # Default local env vars
    export MINIO_ENDPOINT="localhost:9000"
    export MINIO_ACCESS_KEY="minioadmin"
    export MINIO_SECRET_KEY="minioadmin"
    
    echo "Local MinIO started at $MINIO_ENDPOINT"
else
    echo "Running in External MinIO Mode..."
    
    if [ -z "$MINIO_ENDPOINT" ]; then
        echo "Error: MINIO_ENDPOINT must be set when USE_EXTERNAL_MINIO is true."
        exit 1
    fi
    
    echo "Using External MinIO at $MINIO_ENDPOINT"
fi

# 3. Install Python Dependencies
echo "Installing Python dependencies..."
pip install -e .

# 4. Create Test Data
echo "Creating test data in data/raw..."
mkdir -p data/raw
echo "Hello, this is a test document for the training consolidation workbench." > data/raw/test_doc.txt

# 5. Run Dagster Materialization
echo "Running Dagster asset 'raw_documents'..."

dagster asset materialize -m src.pipelines.definitions --select raw_documents

echo "Success! Assets materialized."
echo "You can view the MinIO console at http://localhost:9001 to verify the 'images', 'text', and 'manifests' buckets."
