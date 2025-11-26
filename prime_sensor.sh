#!/bin/bash
set -e

# --- Configuration ---
BUCKET_NAME="training-content"
SOURCE_DIR="source_docs"

# MinIO Config (defaults, override with env vars)
MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_SECURE="${MINIO_SECURE:-False}"

# Check dependencies
if command -v uv &> /dev/null; then
    # We'll use uv run
    PYTHON_CMD="uv run python"
else
    PYTHON_CMD="python3"
fi

echo "Priming Sensor with documents from '$SOURCE_DIR'..."
$PYTHON_CMD prime_sensor.py

