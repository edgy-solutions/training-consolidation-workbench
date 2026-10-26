import os
from neo4j import GraphDatabase

class Neo4jClient:
    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        
        # A long LLM call leaves pooled connections idle for minutes, and something on the path
        # drops them; check any connection idle over a minute before reusing it.
        self.driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password), liveness_check_timeout=60
        )

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None, db=None):
        with self.driver.session(database=db) as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]
