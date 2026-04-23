import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from src.storage.minio import MinioClient

def main():
    minio = MinioClient()
    bucket = "cib-sources"
    prefix = "templates/"
    
    print(f"Listing objects in {bucket}/{prefix}...")
    objects = minio.list_objects(bucket, prefix=prefix, recursive=True)
    
    found = False
    for obj in objects:
        print(f" - {obj.object_name}")
        found = True
        
    if not found:
        print("No objects found.")

if __name__ == "__main__":
    main()
