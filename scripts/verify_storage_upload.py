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

    # 1. Upload YAML
    yaml_local = "config/templates/master_engineering.yaml"
    yaml_key = "templates/master_engineering.yaml"
    
    if os.path.exists(yaml_local):
        minio.upload_file(bucket, yaml_key, yaml_local)
        print(f"Uploaded {yaml_local} to {bucket}/{yaml_key}")
    else:
        print(f"Error: {yaml_local} not found")

    # 2. Upload PPTX
    pptx_local = "test_docs/course_b_git_workflows.pptx"
    pptx_key = "templates/Training Template.pptx"
    
    if os.path.exists(pptx_local):
        minio.upload_file(bucket, pptx_key, pptx_local)
        print(f"Uploaded {pptx_local} to {bucket}/{pptx_key}")
    else:
        print(f"Error: {pptx_local} not found")

if __name__ == "__main__":
    main()
