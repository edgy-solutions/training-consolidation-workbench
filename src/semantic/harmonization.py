import os
import dspy
from typing import List, Dict
from pydantic import BaseModel, Field
from src.storage.neo4j import Neo4jClient
from src.dspy_modules.config import shared_lm
from dotenv import load_dotenv

class ConceptCluster(BaseModel):
    canonical_name: str = Field(description="The standardized, canonical name for this group of concepts.")
    description: str = Field(description="A consolidated definition of what this concept represents.")
    source_concepts: List[str] = Field(description="List of original concept names that belong to this cluster.")

class HarmonizationSignature(dspy.Signature):
    """
    Analyze a list of technical concepts and group them into semantic clusters.
    Identify synonyms, acronyms, and variations (e.g., 'E-Stop' and 'Emergency Halt').
    Produce a list of canonical concepts.
    """
    concepts: List[str] = dspy.InputField(desc="List of concept names to analyze.")
    clusters: List[ConceptCluster] = dspy.OutputField(desc="List of consolidated concept clusters.")

class Harmonizer:
    def __init__(self, neo4j_client: Neo4jClient):
        self.neo4j = neo4j_client
        
        # Use shared LM
        self.lm = shared_lm
        
        self.module = dspy.Predict(HarmonizationSignature)

    def fetch_concepts(self) -> List[str]:
        """Fetch all unique concept names from Neo4j."""
        query = "MATCH (c:Concept) RETURN DISTINCT c.name as name"
        results = self.neo4j.execute_query(query)
        return [r["name"] for r in results if r.get("name")]

    def harmonize(self) -> List[ConceptCluster]:
        """Fetch, cluster, and return clusters."""
        concepts = self.fetch_concepts()
        if not concepts:
            return []
            
        print(f"Harmonizing {len(concepts)} concepts...")
        
        # DSPy Predict returns a Prediction object, access fields by name
        prediction = self.module(concepts=concepts)
        
        # Inspect DSPy history to see prompt and response in console
        try:
            self.lm.inspect_history(n=1)
        except Exception as e:
            print(f"Could not inspect DSPy history: {e}")

        # Check if prediction has 'clusters' attribute directly or via other means
        # TypedPredictor usually returns strict types, but Predict might return a dspy.Prediction
        if hasattr(prediction, "clusters"):
            return prediction.clusters
        else:
            # Fallback parsing if something goes wrong or standard Predict is used
            print("Warning: Unexpected DSPy output format.")
            return []

    def apply_clusters(self, clusters: List[ConceptCluster]):
        """Write CanonicalConcept nodes and relationships to Neo4j."""
        for cluster in clusters:
            # Create Canonical Node
            self.neo4j.execute_query(
                """
                MERGE (cc:CanonicalConcept {name: $name})
                SET cc.description = $desc
                """,
                {"name": cluster.canonical_name, "desc": cluster.description}
            )
            
            # Link sources
            for source_name in cluster.source_concepts:
                self.neo4j.execute_query(
                    """
                    MATCH (c:Concept {name: $source_name})
                    MATCH (cc:CanonicalConcept {name: $canon_name})
                    MERGE (c)-[:ALIGNS_TO]->(cc)
                    """,
                    {"source_name": source_name, "canon_name": cluster.canonical_name}
                )
                print(f"Linked '{source_name}' -> '{cluster.canonical_name}'")
