# Verification Script for Sensor-Driven Flow
import os
import uuid
from dotenv import load_dotenv
from src.storage.minio import MinioClient

def main():
    # 0. Load environment variables from .env
    load_dotenv()

    # 1. Get MinIO settings from environment or use defaults
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    # 2. Create a test file
    course_id = str(uuid.uuid4())
    filename = "sensor_test_doc.txt"
    content = b"Hello, this is a test document triggered by the MinIO sensor."
    
    bucket_name = "training-content"
    object_name = f"{course_id}/{filename}"
    
    print(f"Using MinIO endpoint: {endpoint}")
    print(f"Uploading test artifact to MinIO: {bucket_name}/{object_name}")
    
    # 3. Upload to MinIO
    client = MinioClient(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure
    )
    client.ensure_bucket(bucket_name)
    client.upload_bytes(bucket_name, object_name, content, content_type="text/plain")
    
    print("\n--- Instructions ---")
    print("1. Start the Dagster Daemon and Webserver if not running:")
    print("   dagster dev -m src.pipelines.definitions")
    print("2. In the UI, enable the 'course_upload_sensor'.")
    print(f"3. The sensor should detect '{object_name}' and trigger 'process_course_job'.")
    print(f"4. Check MinIO for artifacts at '{course_id}/generated/'.")

if __name__ == "__main__":
    main()
