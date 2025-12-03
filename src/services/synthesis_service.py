import os
import dspy
from typing import List, Dict, Any
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.synthesizer import ContentSynthesizer

from dotenv import load_dotenv

# Configure DSPy (same as generator_service)
load_dotenv()
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").replace('/v1', '')
ollama_model = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

print(f"Configuring Synthesis Service DSPy with {ollama_base_url} and model {ollama_model}")
lm = dspy.LM(model=f"ollama_chat/{ollama_model}", api_base=ollama_base_url, api_key="")
dspy.configure(lm=lm)

class SynthesisService:
    def __init__(self):
        self.neo4j_client = Neo4jClient()
        self.weaviate_client = WeaviateClient()
        self.synthesizer = ContentSynthesizer()

    def synthesize_node(self, target_node_id: str, instruction: str):
        """
        Orchestrate the synthesis of a target node.
        1. Fetch source slide IDs from Neo4j
        2. Fetch slide text from Weaviate
        3. Call DSPy synthesizer
        4. Update Neo4j with result
        """
        print(f"Starting synthesis for node {target_node_id}...")
        
        try:
            # 1. Get source refs
            query = """
            MATCH (t:TargetNode {id: $id})
            OPTIONAL MATCH (t)-[:DERIVED_FROM]->(s:Slide)
            RETURN collect(s.id) as slide_ids
            """
            result = self.neo4j_client.execute_query(query, {"id": target_node_id})
            if not result or not result[0]['slide_ids']:
                print(f"No source slides found for node {target_node_id}")
                self._update_status(target_node_id, 'error', "No source slides found")
                return

            slide_ids = result[0]['slide_ids']
            
            # 2. Get slide text from Weaviate
            slides_content = []
            print(f"DEBUG: Fetching content for slide IDs: {slide_ids}")
            for slide_id in slide_ids:
                try:
                    # Weaviate query to get text for specific slide_id
                    # Note: This assumes 1-to-1 mapping or simple retrieval
                    # We might need to filter by slide_id in Weaviate
                    
                    # Using a simple filter query
                    response = self.weaviate_client.client.query.get(
                        "SlideText", ["text", "slide_id"]
                    ).with_where({
                        "path": ["slide_id"],
                        "operator": "Equal",
                        "valueString": slide_id
                    }).do()
                    
                    if "data" in response and "Get" in response["data"] and response["data"]["Get"]["SlideText"]:
                        text = response["data"]["Get"]["SlideText"][0]["text"]
                        print(f"DEBUG: Slide {slide_id} text length: {len(text)}")
                        print(f"DEBUG: Slide {slide_id} preview: {text[:100]}...")
                        slides_content.append({"id": slide_id, "text": text})
                    else:
                        print(f"Warning: No text found in Weaviate for slide {slide_id}")
                        
                except Exception as e:
                    print(f"Error fetching slide {slide_id} from Weaviate: {e}")

            if not slides_content:
                print(f"No content found for any slides for node {target_node_id}")
                self._update_status(target_node_id, 'error', "No content found for source slides")
                return

            # 3. Call Synthesizer with Retry Logic
            print(f"Synthesizing content from {len(slides_content)} slides...")
            
            max_retries = 3
            result = None
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    print(f"DEBUG: Synthesis attempt {attempt + 1}/{max_retries}")
                    result = self.synthesizer(slides_content, instruction)
                    if result:
                        break
                except Exception as e:
                    print(f"DEBUG: Attempt {attempt + 1} failed: {e}")
                    last_error = e
                    import time
                    time.sleep(1) # Brief pause before retry
            
            if not result:
                raise last_error or Exception("Failed to synthesize content after retries")
            
            # Extract markdown from structured output
            # The synthesizer now returns a dict with 'markdown', 'assets', 'callouts'
            if isinstance(result, dict):
                markdown = result.get('markdown', '')
                assets = result.get('assets', [])
                callouts = result.get('callouts', [])
                print(f"DEBUG: Synthesizer returned {len(assets)} assets and {len(callouts)} callouts")
            else:
                # Fallback for old string return (shouldn't happen anymore)
                markdown = str(result)
                assets = []
                callouts = []
            
            # 4. Update Neo4j
            self._update_result(target_node_id, markdown)
            print(f"Synthesis complete for node {target_node_id}")

        except Exception as e:
            print(f"Synthesis failed: {e}")
            self._update_status(target_node_id, 'error', str(e))

    def _update_status(self, node_id: str, status: str, error_msg: str = None):
        query = """
        MATCH (n:TargetNode {id: $id}) 
        SET n.status = $status
        """
        params = {"id": node_id, "status": status}
        if error_msg:
            # Optionally store error message on node
            pass 
        self.neo4j_client.execute_query(query, params)

    def _update_result(self, node_id: str, content: str):
        query = """
        MATCH (n:TargetNode {id: $id}) 
        SET n.content_markdown = $content, n.status = 'complete'
        """
        self.neo4j_client.execute_query(query, {"id": node_id, "content": content})

    def close(self):
        self.neo4j_client.close()
