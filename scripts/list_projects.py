import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from src.storage.neo4j import Neo4jClient

def main():
    neo = Neo4jClient()
    results = neo.execute_query("MATCH (p:Project) RETURN p.id as id, p.title as title LIMIT 5")
    with open("project_id.txt", "w") as f:
        for r in results:
            f.write(r['id'])
            break

if __name__ == "__main__":
    main()
