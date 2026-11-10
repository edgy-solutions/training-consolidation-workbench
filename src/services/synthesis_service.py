import json
import os
import posixpath
import dspy
from typing import List, Dict, Any
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.synthesizer import ContentSynthesizer
from src.dspy_modules.config import shared_lm as lm
from src.publishing.concept_terms import concept_terms
from src.publishing.course import effective_concepts
from src.publishing.image_ids import qualify, qualify_placeholders
from src.workbench.alignment import Neo4jAlignmentStore


def asset_menu(rows) -> Dict[str, List[Dict[str, Any]]]:
    """{slide_id: image assets} from content rows (id, elements JSON, course_id).

    Asset ids are '<deck>--<name>'; a row without a course_id offers none."""
    menu: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        course_id = row.get("course_id")
        if not course_id:
            continue
        elements = row.get("elements")
        if isinstance(elements, str):
            try:
                elements = json.loads(elements)
            except ValueError:
                elements = []
        found: Dict[str, Dict[str, Any]] = {}
        for el in elements or []:
            path = (el.get("metadata") or {}).get("image_path")
            if not path:
                continue
            base = posixpath.basename(path.replace("\\", "/"))
            asset_id = qualify(course_id, base)
            if asset_id not in found:
                found[asset_id] = {"asset_id": asset_id, "slide_id": row["id"], "type": "image",
                                   "description": (el.get("text") or "").strip() or base}
        menu[row["id"]] = list(found.values())
    return menu

SECTION_NOTES_QUERY = """
UNWIND $slide_ids AS sid
MATCH (sec:Section)-[:HAS_SLIDE]->(:Slide {id: sid})
WHERE coalesce(sec.summary, '') <> '' OR size(coalesce(sec.objectives, [])) > 0
RETURN sid AS slide_id, sec.id AS id, sec.title AS title, sec.level AS level, sec.start_page AS start_page, sec.end_page AS end_page, sec.summary AS summary, sec.objectives AS objectives
"""


SLIDE_TEACHES_QUERY = """
UNWIND $slide_ids AS sid
MATCH (s:Slide {id: sid})
OPTIONAL MATCH (s)-[t:TEACHES]->(k:Concept)
OPTIONAL MATCH (k)-[:ALIGNS_TO]->(cc:CanonicalConcept)
RETURN s.id AS id,
       collect(CASE WHEN k IS NULL THEN NULL ELSE {name: k.name, salience: t.salience, canonical: cc.name,
                                                    related_terms: t.related_terms} END) AS teaches
"""


def section_notes(rows) -> List[Dict[str, Any]]:
    """The source Section notes (summary, objectives) that speak for the slides.

    A slide has many Section parents, as ranges nest; its most specific one with notes speaks
    for it: deepest level, then narrowest span (an open end_page is widest), then smallest id."""
    best: Dict[Any, Any] = {}
    for row in rows:
        summary = (row.get("summary") or "").strip()
        objectives = [o.strip() for o in (row.get("objectives") or []) if isinstance(o, str) and o.strip()]
        if not summary and not objectives:
            continue
        start = row.get("start_page") or 0
        end = row.get("end_page")
        span = (end - start) if end else float("inf")
        key = (-(row.get("level") or 0), span, str(row.get("id")))
        slide_id = row.get("slide_id")
        if slide_id not in best or key < best[slide_id][0]:
            best[slide_id] = (key, row, summary, objectives)
    notes: Dict[Any, Dict[str, Any]] = {}
    for _, row, summary, objectives in best.values():
        notes.setdefault(row.get("id"), {"id": row.get("id"), "title": row.get("title"), "summary": summary,
                                         "objectives": objectives, "_start": row.get("start_page") or 0})
    ordered = sorted(notes.values(), key=lambda n: (n["_start"], str(n["id"])))
    for n in ordered:
        del n["_start"]
    return ordered

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
                   t.target_layout as target_layout,
                   t.key_concepts as key_concepts
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
            key_concepts = result[0].get('key_concepts') or []
            
            # 2. Get slide content (structured) from Neo4j (previously Weaviate)
            # We now prefer the structured 'elements' from Neo4j over flat text
            slides_content = []
            print(f"DEBUG: Fetching content for slide IDs: {slide_ids}")
            
            # Fetch elements json from Neo4j
            content_query = """
            UNWIND $slide_ids as sid
            MATCH (s:Slide {id: sid})
            OPTIONAL MATCH (c:Course)-[:HAS_SLIDE]->(s)
            RETURN s.id as id, s.elements as elements, s.text as text, c.id as course_id
            """
            content_results = self.neo4j_client.execute_query(content_query, {"slide_ids": slide_ids})
            
            menu = asset_menu(content_results)
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
                    slides_content.append({"id": s_id, "text": formatted_text, "assets": menu.get(s_id, [])})
                else:
                    print(f"Warning: No text found for slide {s_id}")

            if not slides_content:
                print(f"No content found for any slides for node {target_node_id}")
                self._update_status(target_node_id, 'error', "No content found for source slides")
                return

            teaches = [t for r in self.neo4j_client.execute_query(SLIDE_TEACHES_QUERY, {"slide_ids": slide_ids})
                       for t in r.get("teaches") or [] if t]
            on_slides = [{"teaches": teaches}]
            concepts = effective_concepts({"key_concepts": key_concepts}, on_slides)[0]
            terms = concept_terms(concepts, on_slides, Neo4jAlignmentStore(self.neo4j_client))
            focus = [{"concept": c, "terms": terms[c][1:]} for c in concepts]

            notes = section_notes(self.neo4j_client.execute_query(SECTION_NOTES_QUERY, {"slide_ids": slide_ids}))

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
                        target_layout=target_layout,
                        section_notes=notes,
                        section_concepts=focus
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
            
            # a bare {{x}} becomes the deck-prefixed id it stands for; the export refuses what stays bare
            offered = [a["asset_id"] for s in slides_content for a in s["assets"]]
            markdown = qualify_placeholders(markdown, offered)

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
