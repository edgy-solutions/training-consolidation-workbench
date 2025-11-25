from dagster import ConfigurableResource
from src.storage.minio import MinioClient
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient

class MinioResource(ConfigurableResource):
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    secure: bool = False

    def get_client(self) -> MinioClient:
        return MinioClient(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

class Neo4jResource(ConfigurableResource):
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "password"

    def get_client(self) -> Neo4jClient:
        return Neo4jClient(
            uri=self.uri,
            user=self.user,
            password=self.password
        )

class WeaviateResource(ConfigurableResource):
    url: str = "http://localhost:8080"

    def get_client(self) -> WeaviateClient:
        return WeaviateClient(
            url=self.url
        )
