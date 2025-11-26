#!/bin/bash
set -e

# --- Configuration ---
BUCKET_NAME="training-content"
SOURCE_DIR="source_docs"

# MinIO Config (defaults, override with env vars)
MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_SECURE="${MINIO_SECURE:-false}"

# Check dependencies
if command -v uv &> /dev/null; then
    # We'll use uv run
    PYTHON_CMD="uv run python"
else
    PYTHON_CMD="python3"
fi

# --- Python Upload Script ---
cat <<EOF > prime_sensor.py
import os
import sys
import uuid
import json
from minio import Minio
from minio.error import S3Error

endpoint = "$MINIO_ENDPOINT"
access_key = "$MINIO_ACCESS_KEY"
secret_key = "$MINIO_SECRET_KEY"
secure = $MINIO_SECURE
bucket_name = "$BUCKET_NAME"
source_dir = r"$SOURCE_DIR"

# Fix: convert "false" string to boolean if needed, though bash string substitution is tricky
if isinstance(secure, str):
    secure = secure.lower() == "true"

client = Minio(
    endpoint,
    access_key=access_key,
    secret_key=secret_key,
    secure=secure
)

if not client.bucket_exists(bucket_name):
    print(f"Bucket '{bucket_name}' does not exist. Creating...")
    client.make_bucket(bucket_name)

if not os.path.exists(source_dir):
    print(f"Source directory '{source_dir}' not found.")
    sys.exit(1)

files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]

if not files:
    print("No files found in source directory.")
    sys.exit(0)

print(f"Found {len(files)} files to upload.")

for filename in files:
    # Check if it's a metadata json (skip, will be uploaded with main file) or a content file
    if filename.endswith("_metadata.json"):
        continue
        
    file_path = os.path.join(source_dir, filename)
    
    # Generate Course ID
    course_id = str(uuid.uuid4())
    
    # Define object paths
    object_name = f"{course_id}/{filename}"
    metadata_object_name = f"{course_id}/metadata.json"
    
    print(f"Uploading '{filename}' to '{object_name}'...")
    try:
        client.fput_object(bucket_name, object_name, file_path)
        
        # Look for sidecar metadata
        # Candidates: {filename}.json, {filename}_metadata.json, metadata.json (fallback)
        meta_candidates = [
            file_path + ".json",
            os.path.splitext(file_path)[0] + "_metadata.json",
            os.path.join(source_dir, "metadata.json") 
        ]
        
        metadata_path = None
        for cand in meta_candidates:
            if os.path.exists(cand):
                metadata_path = cand
                break
        
        if metadata_path:
            print(f"  Found metadata: {metadata_path}")
            client.fput_object(bucket_name, metadata_object_name, metadata_path)
        else:
            print("  No sidecar metadata found. Uploading default.")
            default_meta = {
                "course_title": os.path.splitext(filename)[0],
                "engineering_discipline": "General",
                "business_unit": "Unknown",
                "version": "1.0"
            }
            with open("temp_meta.json", "w") as f:
                json.dump(default_meta, f)
            client.fput_object(bucket_name, metadata_object_name, "temp_meta.json")
            os.remove("temp_meta.json")
            
    except S3Error as e:
        print(f"Error uploading {filename}: {e}")

print("Done.")
EOF

echo "Priming Sensor with documents from '$SOURCE_DIR'..."
$PYTHON_CMD prime_sensor.py
rm prime_sensor.py
