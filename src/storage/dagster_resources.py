import os
from dagster import ConfigurableResource
from src.storage.minio import MinioClient
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient

class MinioResource(ConfigurableResource):
    endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    def get_client(self) -> MinioClient:
        return MinioClient(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

class Neo4jResource(ConfigurableResource):
    uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user: str = os.getenv("NEO4J_USER", "neo4j")
    password: str = os.getenv("NEO4J_PASSWORD", "password")

    def get_client(self) -> Neo4jClient:
        return Neo4jClient(
            uri=self.uri,
            user=self.user,
            password=self.password
        )

class WeaviateResource(ConfigurableResource):
    url: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")

    def get_client(self) -> WeaviateClient:
        return WeaviateClient(
            url=self.url
        )
