$ErrorActionPreference = "Stop"

# --- Configuration ---
$bucketName = "training-content"
$sourceDir = "source_docs"

# MinIO Config (defaults, override with env vars)
$minioEndpoint = if ($env:MINIO_ENDPOINT) { $env:MINIO_ENDPOINT } else { "localhost:9000" }
$minioAccessKey = if ($env:MINIO_ACCESS_KEY) { $env:MINIO_ACCESS_KEY } else { "minioadmin" }
$minioSecretKey = if ($env:MINIO_SECRET_KEY) { $env:MINIO_SECRET_KEY } else { "minioadmin" }
$secure = if ($env:MINIO_SECURE -eq "true") { $true } else { $false }

# Check dependencies
if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    # Ensure minio library is available in the venv
    # We'll run a python script using 'uv run' or just assume 'py' has it if not using uv directly for script exec
} else {
    # Fallback check
}

# --- Python Upload Script ---
$pyScript = @"
import os
import sys
import uuid
import json
from minio import Minio
from minio.error import S3Error

endpoint = "$minioEndpoint"
access_key = "$minioAccessKey"
secret_key = "$minioSecretKey"
secure = $secure
bucket_name = "$bucketName"
source_dir = r"$sourceDir"

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
        
        # Look for matching metadata file
        # Convention: if file is "doc.pdf", metadata is "doc.pdf_metadata.json" or "doc_metadata.json"
        # Adjust logic based on how source_docs are populated. 
        # Assuming standard naming from generate_test_docs: "filename_metadata.json" isn't standard output of that script actually.
        # generate_test_docs returns metadata dict.
        # IF source_docs just contains raw files, we might generate dummy metadata.
        # IF source_docs was populated by a tool that saved metadata side-by-side, use it.
        
        # Let's look for {filename}.json or {filename}_metadata.json
        meta_candidates = [
            file_path + ".json",
            os.path.splitext(file_path)[0] + "_metadata.json",
            os.path.join(source_dir, "metadata.json") # fallback?
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
            # Upload default minimal metadata so sensor works
            default_meta = {
                "course_title": os.path.splitext(filename)[0],
                "engineering_discipline": "General",
                "business_unit": "Unknown",
                "version": "1.0"
            }
            # Write temp file
            with open("temp_meta.json", "w") as f:
                json.dump(default_meta, f)
            client.fput_object(bucket_name, metadata_object_name, "temp_meta.json")
            os.remove("temp_meta.json")
            
    except S3Error as e:
        print(f"Error uploading {filename}: {e}")

print("Done.")
"@

$pyFile = "prime_sensor.py"
Set-Content -Path $pyFile -Value $pyScript

Write-Host "Priming Sensor with documents from '$sourceDir'..."

if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    # Assuming 'minio' is installed in the project environment
    uv run python $pyFile
} else {
    python $pyFile
}

Remove-Item $pyFile
