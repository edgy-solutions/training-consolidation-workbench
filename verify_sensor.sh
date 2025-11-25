#!/bin/bash

# Verification Script for Sensor (Linux/macOS)
set -e

# 0. Load .env if present
if [ -f ".env" ]; then
    echo "Loading .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# 1. Check Docker & MinIO
if [ -z "$USE_EXTERNAL_MINIO" ]; then
    echo "Checking Docker..."
    if command -v docker &> /dev/null; then
        echo "Starting MinIO..."
        docker-compose up -d minio
    else
        echo "Skipping Docker start (Docker not found, assuming external or already running)..."
    fi
else
    echo "Running in External MinIO Mode..."
fi

# 2. Setup Python Environment with uv
echo "Setting up Python environment with uv..."

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Please install it first (see WARP.md)."
    exit 1
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating .venv..."
    uv venv
fi

# Install dependencies
echo "Installing dependencies..."
uv pip install -e .

# 3. Run Upload Script
echo "Running upload script (test suite)..."
# Use python from venv
VENV_PYTHON=".venv/bin/python"
$VENV_PYTHON upload_test_suite.py

# 4. Hint to run Dagster
echo ""
echo "To run the Dagster UI:"
echo "source .venv/bin/activate; dagster dev -m src.pipelines.definitions"
