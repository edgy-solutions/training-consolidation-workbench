import os
import sys
import uuid
import json
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()

# 1. Get MinIO settings from environment or use defaults
endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

bucket_name = "training-content"
source_dir = r"source_docs"

# Fix: convert "false" string to boolean if needed, though bash string substitution is tricky
if isinstance(secure, str):
    secure = secure.lower() == "true"

client = Minio(
    endpoint=endpoint,
    access_key=access_key,
    secret_key=secret_key,
    secure=secure
)

if not client.bucket_exists(bucket_name=bucket_name):
    print(f"Bucket '{bucket_name}' does not exist. Creating...")
    client.make_bucket(bucket_name=bucket_name)

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
    if filename.endswith(".json"):
        continue
        
    file_path = os.path.join(source_dir, filename)
    
    # Generate Course ID
    course_id = str(uuid.uuid4())
    
    # Define object paths
    object_name = f"{course_id}/{filename}"
    metadata_object_name = f"{course_id}/metadata.json"
    
    print(f"Uploading '{filename}' to '{object_name}'...")
    try:
        client.fput_object(bucket_name=bucket_name, object_name=object_name, file_path=file_path)
        
        # Look for sidecar metadata
        # Candidates: {filename}.json, {filename}_metadata.json, metadata.json (fallback)
        meta_candidates = [
            file_path + ".json",
            os.path.splitext(file_path)[0] + "_metadata.json",
            os.path.join(source_dir, "metadata.json") 
        ]
        print(meta_candidates)
        metadata_path = None
        for cand in meta_candidates:
            print(f'trying {cand}')
            if os.path.exists(cand):
                metadata_path = cand
                break
        
        if metadata_path:
            print(f"  Found metadata: {metadata_path}")
            client.fput_object(bucket_name=bucket_name, object_name=metadata_object_name, file_path=metadata_path)
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
            client.fput_object(bucket_name=bucket_name, object_name=metadata_object_name, file_path="temp_meta.json")
            os.remove("temp_meta.json")
            
    except S3Error as e:
        print(f"Error uploading {filename}: {e}")

print("Done.")
