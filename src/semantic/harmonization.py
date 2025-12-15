import os
import dspy
from typing import List, Dict
from pydantic import BaseModel, Field
from src.storage.neo4j import Neo4jClient
from src.dspy_modules.config import shared_lm
from dotenv import load_dotenv

# Token estimation constants
TOKENS_PER_CONCEPT = 15  # Average tokens per concept name + JSON overhead
RESERVED_PROMPT_TOKENS = 2000  # System prompt, instructions
RESERVED_RESPONSE_TOKENS = 1000  # Output buffer


class ConceptCluster(BaseModel):
    canonical_name: str = Field(description="The standardized, canonical name for this group of concepts.")
    description: str = Field(description="A consolidated definition of what this concept represents.")
    source_concepts: List[str] = Field(description="List of original concept names that belong to this cluster.")


class HarmonizationSignature(dspy.Signature):
    """
    STRICT SYNONYM DETECTION ONLY.
    
    Your task is to identify ONLY true synonyms - concepts that mean EXACTLY the same thing
    but are written differently (different wording, abbreviations, acronyms, or typos).
    
    DO group together:
    - "E-Stop" and "Emergency Stop" and "Emergency Halt" (same safety procedure, different names)
    - "LOTO" and "Lock Out Tag Out" (acronym and full form)
    - "Create a branch from main" and "Branch Creation from Main" (same action, different phrasing)
    
    DO NOT group together:
    - "Git" and "Branch" and "Commit" (different concepts in same domain)
    - "SolidWorks" and "AutoCAD" (different tools, not synonyms)
    - "Thermodynamics" and "Entropy" (related but distinct concepts)
    
    If a concept has no synonyms, DO NOT include it in any cluster.
    Only output clusters where you are CERTAIN the concepts are true synonyms.
    When in doubt, do NOT cluster - leave concepts separate.
    """
    concepts: List[str] = dspy.InputField(desc="List of concept names to analyze for duplicate/synonym detection.")
    clusters: List[ConceptCluster] = dspy.OutputField(desc="List of synonym clusters. Only include concepts that are TRUE synonyms. Many concepts will have no synonyms - that's expected.")


class Harmonizer:
    def __init__(self, neo4j_client: Neo4jClient):
        self.neo4j = neo4j_client
        
        # Use shared LM
        self.lm = shared_lm
        
        self.module = dspy.Predict(HarmonizationSignature)
        
        # Calculate batch size from LLM context
        self.batch_size = self._calculate_batch_size()

    def _calculate_batch_size(self) -> int:
        """Calculate optimal batch size based on LLM context window."""
        context_size = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        usable_tokens = context_size - RESERVED_PROMPT_TOKENS - RESERVED_RESPONSE_TOKENS
        batch_size = max(50, usable_tokens // TOKENS_PER_CONCEPT)  # Minimum 50 concepts
        print(f"[Harmonizer] Context: {context_size}, Batch size: {batch_size} concepts")
        return batch_size

    def fetch_concepts(self) -> List[str]:
        """Fetch all unique concept names from Neo4j."""
        query = "MATCH (c:Concept) RETURN DISTINCT c.name as name"
        results = self.neo4j.execute_query(query)
        return [r["name"] for r in results if r.get("name")]

    def _batch_concepts(self, concepts: List[str]) -> List[List[str]]:
        """Split concepts into batches."""
        return [concepts[i:i + self.batch_size] for i in range(0, len(concepts), self.batch_size)]

    def _harmonize_batch(self, concepts: List[str]) -> List[ConceptCluster]:
        """Run harmonization on a single batch of concepts."""
        if not concepts:
            return []
        
        prediction = self.module(concepts=concepts)
        
        if hasattr(prediction, "clusters"):
            return prediction.clusters
        else:
            print("Warning: Unexpected DSPy output format.")
            return []

    def harmonize(self) -> List[ConceptCluster]:
        """
        Two-pass batched harmonization:
        1. Pass 1: Process concepts in batches
        2. Pass 2: Consolidate canonical names across batches
        """
        concepts = self.fetch_concepts()
        if not concepts:
            return []
        
        print(f"Harmonizing {len(concepts)} concepts...")
        
        # Check if batching is needed
        if len(concepts) <= self.batch_size:
            print("Single batch - no batching needed")
            clusters = self._harmonize_batch(concepts)
            
            # Inspect DSPy history
            try:
                self.lm.inspect_history(n=1)
            except Exception as e:
                print(f"Could not inspect DSPy history: {e}")
            
            return clusters
        
        # ===== PASS 1: Batch processing =====
        batches = self._batch_concepts(concepts)
        print(f"Pass 1: Processing {len(batches)} batches...")
        
        all_clusters = []
        for i, batch in enumerate(batches):
            print(f"  Batch {i+1}/{len(batches)}: {len(batch)} concepts")
            batch_clusters = self._harmonize_batch(batch)
            all_clusters.extend(batch_clusters)
            print(f"    Found {len(batch_clusters)} clusters")
        
        if not all_clusters:
            print("Pass 1 complete: No clusters found")
            return []
        
        # ===== PASS 2: Consolidate canonical names =====
        # Get all canonical names from pass 1
        canonical_names = [c.canonical_name for c in all_clusters]
        
        if len(canonical_names) <= 1:
            print("Pass 2: Only 0-1 canonical names, skipping consolidation")
            return all_clusters
        
        print(f"Pass 2: Consolidating {len(canonical_names)} canonical names...")
        
        # Run harmonization on canonical names to find cross-batch synonyms
        consolidation_clusters = self._harmonize_batch(canonical_names)
        
        if not consolidation_clusters:
            print("Pass 2: No cross-batch synonyms found")
            return all_clusters
        
        # Merge clusters based on pass 2 results
        print(f"Pass 2: Found {len(consolidation_clusters)} cross-batch synonym groups")
        
        # Build mapping from old canonical -> new canonical
        canonical_mapping = {}
        for cluster in consolidation_clusters:
            new_canonical = cluster.canonical_name
            for old_name in cluster.source_concepts:
                canonical_mapping[old_name] = new_canonical
        
        # Merge clusters
        merged = {}
        for cluster in all_clusters:
            # Check if this canonical needs to be merged
            new_canonical = canonical_mapping.get(cluster.canonical_name, cluster.canonical_name)
            
            if new_canonical not in merged:
                merged[new_canonical] = ConceptCluster(
                    canonical_name=new_canonical,
                    description=cluster.description,
                    source_concepts=list(cluster.source_concepts)
                )
            else:
                # Merge source concepts
                merged[new_canonical].source_concepts.extend(cluster.source_concepts)
        
        # Deduplicate source concepts
        for cluster in merged.values():
            cluster.source_concepts = list(set(cluster.source_concepts))
        
        final_clusters = list(merged.values())
        print(f"Final: {len(final_clusters)} clusters after consolidation")
        
        return final_clusters

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
