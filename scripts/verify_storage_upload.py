import os
import sys
from dotenv import load_dotenv

# Ensure src in path
sys.path.append(os.getcwd())
load_dotenv()

from src.storage.minio import MinioClient

def main():
    minio = MinioClient()
    bucket = "cib-sources"
    minio.ensure_bucket(bucket)

    # Upload the stand-in template (mapping + pptx) under templates/standin/
    folder = "tests/fixtures/templates/standin"
    for name in ("deck-template.yaml", "standin.pptx"):
        local = f"{folder}/{name}"
        key = f"templates/standin/{name}"
        if os.path.exists(local):
            minio.upload_file(bucket, key, local)
            print(f"Uploaded {local} to {bucket}/{key}")
        else:
            print(f"Error: {local} not found")

if __name__ == "__main__":
    main()
