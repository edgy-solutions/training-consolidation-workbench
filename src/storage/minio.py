import os
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error

class MinioClient:
    def __init__(self, endpoint=None, access_key=None, secret_key=None, secure=False, external_endpoint=None, region=None, external_secure=None):
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.secure = secure
        self.region = region or os.getenv("MINIO_REGION", "us-east-1")
        self.external_endpoint = external_endpoint or os.getenv("MINIO_EXTERNAL_ENDPOINT", self.endpoint)
        # External secure defaults to internal secure if not explicitly set
        if external_secure is None:
            external_secure_env = os.getenv("MINIO_EXTERNAL_SECURE", None)
            if external_secure_env is not None:
                self.external_secure = external_secure_env.lower() == "true"
            else:
                self.external_secure = self.secure
        else:
            self.external_secure = external_secure
        
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            region=self.region
        )

        if self.external_endpoint != self.endpoint or self.external_secure != self.secure:
            self.signer_client = Minio(
                endpoint=self.external_endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.external_secure,
                region=self.region
            )
        else:
            self.signer_client = self.client

    def ensure_bucket(self, bucket_name: str):
        """Check if bucket exists, otherwise create it."""
        if not self.client.bucket_exists(bucket_name=bucket_name):
            self.client.make_bucket(bucket_name=bucket_name)
            print(f"Bucket '{bucket_name}' created.")
        else:
            print(f"Bucket '{bucket_name}' already exists.")

    def upload_file(self, bucket_name: str, object_name: str, file_path: str, content_type: str = None):
        """Upload a file from the local filesystem."""
        self.ensure_bucket(bucket_name)
        try:
            self.client.fput_object(bucket_name=bucket_name, object_name=object_name, file_path=file_path, content_type=content_type)
            print(f"'{file_path}' is successfully uploaded as object '{object_name}' to bucket '{bucket_name}'.")
            return f"http://{self.endpoint}/{bucket_name}/{object_name}" 
        except S3Error as exc:
            print("error occurred.", exc)
            raise

    def upload_bytes(self, bucket_name: str, object_name: str, data: bytes, content_type: str = "application/octet-stream"):
        """Upload bytes data."""
        self.ensure_bucket(bucket_name)
        try:
            data_stream = io.BytesIO(data)
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=content_type
            )
            print(f"Bytes uploaded as object '{object_name}' to bucket '{bucket_name}'.")
            return f"http://{self.endpoint}/{bucket_name}/{object_name}"
        except S3Error as exc:
            print("error occurred.", exc)
            raise

    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        """Download a file from the bucket to the local filesystem."""
        try:
            self.client.fget_object(bucket_name=bucket_name, object_name=object_name, file_path=file_path)
            print(f"Downloaded object '{object_name}' from bucket '{bucket_name}' to '{file_path}'.")
        except S3Error as exc:
            print("error occurred.", exc)
            raise
    
    def list_objects(self, bucket_name: str, prefix: str = None, recursive: bool = False):
        """List objects in a bucket."""
        try:
            return self.client.list_objects(bucket_name=bucket_name, prefix=prefix, recursive=recursive)
        except S3Error as exc:
            print("error occurred.", exc)
            raise

    def get_presigned_url(self, bucket_name: str, object_name: str, expires: timedelta = timedelta(hours=1)):
        """Generate a presigned URL for GET request."""
        try:
            return self.signer_client.presigned_get_object(bucket_name=bucket_name, object_name=object_name, expires=expires)
        except S3Error as exc:
            print("error occurred.", exc)
            raise
