"""
Service for generating consolidated curricula from source materials.
"""
import uuid
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.outline_harmonizer import OutlineHarmonizer
import dspy

# Configure DSPy once at module level to avoid thread conflicts
load_dotenv()
base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").replace('/v1', '')
model_name = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

try:
    print(f'Configuring DSPy with {base_url} and model {model_name}')
    lm = dspy.LM(model=f"ollama_chat/{model_name}", api_base=base_url, api_key='')
    dspy.configure(lm=lm)
except Exception as e:
    print(f'DSPy configuration warning: {e}')


class GeneratorService:
    """Service for generating consolidated curricula"""
    
    def __init__(self):
        self.neo4j_client = Neo4jClient()
        self.weaviate_client = WeaviateClient()
        self.harmonizer = OutlineHarmonizer()
    
    def generate_skeleton(self, selected_source_ids: List[str], title: str = "New Curriculum") -> Dict[str, Any]:
        """
        Generate a curriculum skeleton from selected source sections/courses.
        
        Args:
            selected_source_ids: List of Section IDs or Course IDs
            title: Title for the new curriculum project
            
        Returns:
            Dictionary with project_id and generated structure
        """
        # Step 1: Fetch source outlines from Neo4j
        source_outlines = self._fetch_source_outlines(selected_source_ids)
        
        if not source_outlines:
            raise ValueError("No source outlines found for the given IDs")
        
        # Step 2: Call DSPy to generate consolidated plan
        consolidated_sections = self.harmonizer(source_outlines)
        
        # Step 3: For each target section, find matching slides
        enriched_sections = []
        for section in consolidated_sections:
            suggested_slides = self._find_matching_slides(section.get('key_concepts', []))
            enriched_sections.append({
                **section,
                'suggested_slides': suggested_slides
            })
        
        # Step 4: Create Project and persist to Neo4j
        project_id = self._persist_project(enriched_sections, title=title)
        
        return {
            'project_id': project_id,
            'sections': enriched_sections
        }
    
    def _fetch_source_outlines(self, source_ids: List[str]) -> List[dict]:
        """Fetch section titles and concept summaries from Neo4j"""
        query = """
        MATCH (node)
        WHERE node.id IN $source_ids 
          AND (node:Section OR node:Course)
        OPTIONAL MATCH (node)-[:HAS_SECTION]->(sec:Section)
        WITH node, CASE 
            WHEN node:Section THEN [node]
            ELSE collect(sec)
        END as sections
        UNWIND sections as s
        RETURN s.title as section_title, 
               s.concept_summary as concepts,
               coalesce(node.business_unit, 'Unknown') as bu
        """
        results = self.neo4j_client.execute_query(query, {"source_ids": source_ids})
        
        return [
            {
                'bu': r['bu'],
                'section_title': r['section_title'],
                'concepts': r['concepts'] or []
            }
            for r in results if r['section_title']
        ]
    
    def _find_matching_slides(self, key_concepts: List[str], top_n: int = 3) -> List[Dict]:
        """Use Weaviate to find slides that best match the concepts"""
        if not key_concepts:
            return []
        
        # Combine concepts into a search query
        search_query = " ".join(key_concepts)
        
        try:
            response = self.weaviate_client.client.query.get(
                "SlideText", ["slide_id", "text"]
            ).with_near_text({
                "concepts": [search_query],
                "certainty": 0.6  # Lower than search threshold
            }).with_limit(top_n).do()
            
            if "data" in response and "Get" in response["data"]:
                slides = response["data"]["Get"]["SlideText"]
                return [
                    {
                        'slide_id': s['slide_id'],
                        'text_preview': s['text'][:100] + "..."
                    }
                    for s in slides
                ]
        except Exception as e:
            print(f"Error finding matching slides: {e}")
        
        return []
    
    def _persist_project(self, sections: List[Dict], title: str = "New Curriculum") -> str:
        """Create Project and TargetNode entries in Neo4j"""
        project_id = str(uuid.uuid4())
        
        # Create Project node with title
        self.neo4j_client.execute_query(
            """
            CREATE (p:Project {
                id: $project_id,
                title: $title,
                created_at: datetime(),
                status: 'draft'
            })
            """,
            {"project_id": project_id, "title": title}
        )
        
        # Create TargetNode entries
        for i, section in enumerate(sections):
            target_id = f"{project_id}_target_{i}"
            
            # Create TargetNode
            self.neo4j_client.execute_query(
                """
                MATCH (p:Project {id: $project_id})
                CREATE (t:TargetNode {
                    id: $target_id,
                    title: $title,
                    rationale: $rationale,
                    key_concepts: $key_concepts,
                    status: 'suggestion',
                    order: $order
                })
                CREATE (p)-[:HAS_CHILD]->(t)
                """,
                {
                    "project_id": project_id,
                    "target_id": target_id,
                    "title": section['title'],
                    "rationale": section['rationale'],
                    "key_concepts": section.get('key_concepts', []),
                    "order": i
                }
            )
            
            # Link to suggested slides
            for slide_info in section.get('suggested_slides', []):
                self.neo4j_client.execute_query(
                    """
                    MATCH (t:TargetNode {id: $target_id})
                    MATCH (s:Slide {id: $slide_id})
                    CREATE (t)-[:SUGGESTED_SOURCE]->(s)
                    """,
                    {
                        "target_id": target_id,
                        "slide_id": slide_info['slide_id']
                    }
                )
        
        return project_id
    
    def close(self):
        """Close database connections"""
        self.neo4j_client.close()
