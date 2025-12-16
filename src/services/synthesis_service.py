import os
import dspy
from typing import List, Dict, Any
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.synthesizer import ContentSynthesizer
from src.dspy_modules.config import shared_lm as lm
import dspy

# DSPy configuration is handled in src.dspy_modules.config

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
            # 1. Get source refs and section context (rationale, title, layout)
            query = """
            MATCH (t:TargetNode {id: $id})
            OPTIONAL MATCH (t)-[:DERIVED_FROM]->(s:Slide)
            RETURN collect(s.id) as slide_ids, 
                   t.rationale as rationale, 
                   t.title as title,
                   t.target_layout as target_layout
            """
            result = self.neo4j_client.execute_query(query, {"id": target_node_id})
            if not result or not result[0]['slide_ids']:
                print(f"No source slides found for node {target_node_id}")
                self._update_status(target_node_id, 'error', "No source slides found")
                return

            slide_ids = result[0]['slide_ids']
            section_rationale = result[0].get('rationale', '')
            section_title = result[0].get('title', '')
            target_layout = result[0].get('target_layout', 'documentary')  # Default to documentary
            
            # 2. Get slide content (structured) from Neo4j (previously Weaviate)
            # We now prefer the structured 'elements' from Neo4j over flat text
            slides_content = []
            print(f"DEBUG: Fetching content for slide IDs: {slide_ids}")
            
            # Fetch elements json from Neo4j
            content_query = """
            UNWIND $slide_ids as sid
            MATCH (s:Slide {id: sid})
            RETURN s.id as id, s.elements as elements, s.text as text
            """
            content_results = self.neo4j_client.execute_query(content_query, {"slide_ids": slide_ids})
            
            import json
            for row in content_results:
                s_id = row['id']
                elements_json = row.get('elements')
                text_fallback = row.get('text', '')
                
                formatted_text = ""
                
                if elements_json:
                    try:
                        elements = json.loads(elements_json)
                        # Format elements into a rich string
                        # e.g. [Title] Introduction
                        #      [NarrativeText] The system consists of...
                        for el in elements:
                            etype = el.get('type', 'Text')
                            etext = el.get('text', '')
                            if etext.strip():
                                formatted_text += f"[{etype}] {etext}\n"
                    except:
                        print(f"Warning: Failed to parse elements for slide {s_id}, using fallback.")
                        formatted_text = text_fallback
                else:
                    # Fallback for legacy slides without elements
                    formatted_text = text_fallback

                if formatted_text:
                    slides_content.append({"id": s_id, "text": formatted_text})
                else:
                    print(f"Warning: No text found for slide {s_id}")

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
                    # Pass section context (rationale, title, layout) along with slides and instruction
                    result = self.synthesizer(
                        slides_content, 
                        instruction,
                        section_title=section_title,
                        section_rationale=section_rationale,
                        target_layout=target_layout
                    )
                    if result:
                        break
                except Exception as e:
                    print(f"DEBUG: Attempt {attempt + 1} failed: {e}")
                    last_error = e
                    import time
                    time.sleep(1) # Brief pause before retry
            
            if not result:
                raise last_error or Exception("Failed to synthesize content after retries")
            
            # Inspect DSPy history to see prompt and response in console
            try:
                lm.inspect_history(n=1)
            except Exception as e:
                print(f"Could not inspect DSPy history: {e}")

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
