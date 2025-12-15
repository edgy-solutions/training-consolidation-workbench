"""
Service for generating consolidated curricula from source materials.
"""
import uuid
import os
import yaml
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.outline_harmonizer import OutlineHarmonizer
from src.dspy_modules.config import shared_lm as lm
import dspy

# Configure DSPy using shared configuration
# load_dotenv() and dspy.configure() are handled in src.dspy_modules.config

# Load curriculum template from YAML
def load_curriculum_template() -> List[Dict]:
    """Load the curriculum template from YAML config."""
    config_path = os.path.join(
        os.path.dirname(__file__), 
        '..', '..', 'config', 'curriculum_template.yaml'
    )
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('modules', [])
    except FileNotFoundError:
        print(f"[WARN] Template config not found at {config_path}, using defaults")
        return []

TEMPLATE_MODULES = load_curriculum_template()

# Configure DSPy using shared configuration
# load_dotenv() and dspy.configure() are handled in src.dspy_modules.config


class GeneratorService:
    """Service for generating consolidated curricula"""
    
    def __init__(self):
        self.neo4j_client = Neo4jClient()
        self.weaviate_client = WeaviateClient()
        self.harmonizer = OutlineHarmonizer()
    
    def _normalize_concepts(self, concepts: List[str]) -> List[str]:
        """
        Normalize a list of concept names via CanonicalConcept lookup.
        Returns deduplicated list of canonical names (or original if no canonical exists).
        """
        if not concepts:
            return []
        
        query = """
        UNWIND $concepts as concept_name
        MATCH (c:Concept {name: concept_name})
        OPTIONAL MATCH (c)-[:ALIGNS_TO]->(cc:CanonicalConcept)
        RETURN concept_name, coalesce(cc.name, c.name) as display_name
        """
        results = self.neo4j_client.execute_query(query, {"concepts": concepts})
        
        # Build lookup map
        name_map = {r['concept_name']: r['display_name'] for r in results}
        
        # Normalize and deduplicate while preserving order
        seen = set()
        normalized = []
        for concept in concepts:
            display = name_map.get(concept, concept)  # Fallback to original if not in graph
            if display not in seen:
                seen.add(display)
                normalized.append(display)
        
        return normalized
    
    def generate_skeleton(self, selected_source_ids: List[str], title: str = "New Curriculum", master_course_id: Optional[str] = None, template_name: str = "standard", user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a curriculum skeleton from selected source sections/courses.
        
        Args:
            selected_source_ids: List of Section IDs or Course IDs
            title: Title for the new curriculum project
            master_course_id: If provided, use this course's outline as the master structure
            
        Returns:
            Dictionary with project_id and generated structure
        """
        # Step 1: Fetch source outlines from Neo4j
        source_outlines, source_course_ids, known_source_concepts = self._fetch_source_outlines(selected_source_ids)
        
        if not source_outlines:
            raise ValueError("No source outlines found for the given IDs")
        
        print(f"DEBUG: Found {len(source_course_ids)} source course IDs: {source_course_ids}")
        
        # Step 2: Generate consolidated plan
        if master_course_id:
            # Use the master course's outline as the structure
            print(f"DEBUG: Using master outline from course: {master_course_id}")
            consolidated_sections = self._use_master_outline(master_course_id)
        else:
            print("DEBUG: Cal Harmonizer with Weighted Concepts...")
            # Create harmonizer with selected template
            harmonizer = OutlineHarmonizer(template_name=template_name)
            # The Harmonizer now sees "Voltage (Primary)" vs "Safety (Mention)"
            consolidated_sections = harmonizer(source_outlines)
            
            # Inspect DSPy history to see prompt and response in console
            try:
                lm.inspect_history(n=1)
            except Exception as e:
                print(f"Could not inspect DSPy history: {e}")
                
            print(f"DEBUG: Harmonizer returned {len(consolidated_sections)} sections")
            for s in consolidated_sections:
                section_type = s.get('type', 'technical')
                print(f"DEBUG: Section '{s['title']}' (type: {section_type}) has concepts: {s.get('key_concepts')}")
        
        # Step 3: For each target section, find matching slides (FILTERED by source courses)
        enriched_sections = []
        for section in consolidated_sections:
            
            # New Logic: Trust the explicit signal from the LLM
            if section.get('rationale') == "NO_SOURCE_DATA" or not section.get('key_concepts'):
                print(f"DEBUG: Section '{section['title']}' is explicitly empty. Creating placeholder.")
                
                enriched_sections.append({
                    **section,
                    'suggested_slides': [],
                    'is_placeholder': True # Frontend renders this with a "Missing Content" warning
                })
                continue

            # Normal logic for populated sections
            suggested_slides = self._find_matching_slides_iterative(
                section.get('key_concepts', []),
                allowed_course_ids=source_course_ids
            )

            enriched_sections.append({
                **section,
                'suggested_slides': suggested_slides
            })
        
        # Step 4: Calculate Unassigned Slides (Parking Lot)
        all_source_slides = self._fetch_all_slides_for_courses(source_course_ids)
        all_slide_ids = set(s['id'] for s in all_source_slides)
        
        assigned_slide_ids = set()
        for section in enriched_sections:
            for slide in section.get('suggested_slides', []):
                assigned_slide_ids.add(slide['slide_id'])
                
        unassigned_ids = all_slide_ids - assigned_slide_ids
        
        if unassigned_ids:
            print(f"DEBUG: Found {len(unassigned_ids)} unassigned slides")
            unassigned_slides_data = [
                {'slide_id': s['id'], 'text_preview': s['text'][:100] + "..."}
                for s in all_source_slides if s['id'] in unassigned_ids
            ]
            
            enriched_sections.append({
                'title': "⚠️ Unassigned / For Review",
                'rationale': "Slides available in source material but not used by the AI strategy.",
                'key_concepts': [],
                'suggested_slides': unassigned_slides_data,
                'is_unassigned': True
            })

        # Step 5: Persist
        project_id = self._persist_project(enriched_sections, title=title, user_id=user_id)
        
        return {
            'project_id': project_id,
            'sections': enriched_sections
        }

    def _fetch_all_slides_for_courses(self, course_ids: List[str]) -> List[Dict]:
        """Fetch all slides for the given list of course IDs"""
        if not course_ids:
            return []
            
        query = """
        MATCH (c:Course)-[:HAS_SLIDE]->(s:Slide)
        WHERE c.id IN $course_ids
        RETURN s.id as id, s.text as text
        """
        results = self.neo4j_client.execute_query(query, {"course_ids": course_ids})
        return results
    
    
    def _use_master_outline(self, master_course_id: str) -> List[Dict]:
        """
        Use a master course's outline as the structure for the new curriculum.
        Wraps sections into the template defined in config/curriculum_template.yaml
        Returns a list of sections with titles, rationale, key_concepts, and type.
        """
        query = """
        MATCH (c:Course {id: $course_id})-[:HAS_SECTION*]->(s:Section)
        OPTIONAL MATCH (s)-[:COVERS]->(con:Concept)
        WITH s, collect(distinct con.name) as concepts
        RETURN s.id as id,
               s.title as title,
               s.level as level,
               coalesce(s.concept_summary, concepts, []) as concepts
        ORDER BY s.id
        """
        results = self.neo4j_client.execute_query(query, {"course_id": master_course_id})
        
        if not results:
            print("[WARN] No sections found in master course")
            return []
        
        # Build sections from YAML config
        standard_sections = []
        remaining_results = list(results)  # Copy for technical modules
        
        for module_config in TEMPLATE_MODULES:
            key = module_config['key']
            default_title = module_config.get('title', key.replace('_', ' ').title())
            module_type = module_config.get('type', 'technical')
            is_list = module_config.get('is_list', False)
            is_mandatory = module_config.get('mandatory', False)
            default_concepts = module_config.get('default_concepts', [])
            
            if is_list:
                # Technical modules: use remaining source sections
                # Skip first (intro) and last (assessment) if they exist
                if len(remaining_results) > 2:
                    tech_results = remaining_results[1:-1]
                elif len(remaining_results) > 1:
                    tech_results = remaining_results[1:]
                else:
                    tech_results = []
                
                for section in tech_results:
                    standard_sections.append({
                        'title': section['title'],
                        'rationale': f"Technical content from master course: {section['title']}",
                        'key_concepts': section.get('concepts', [])[:10],
                        'type': module_type
                    })
            else:
                # Single module
                if key == 'overview' and remaining_results:
                    # Use first section for intro
                    intro = remaining_results[0]
                    standard_sections.append({
                        'title': intro['title'],
                        'rationale': f"Introduction from master course: {intro['title']}",
                        'key_concepts': intro.get('concepts', [])[:10],
                        'type': module_type
                    })
                elif key == 'assessment' and len(remaining_results) > 1:
                    # Use last section for assessment
                    last = remaining_results[-1]
                    standard_sections.append({
                        'title': last['title'],
                        'rationale': f"Assessment from master course: {last['title']}",
                        'key_concepts': last.get('concepts', [])[:10],
                        'type': module_type
                    })
                elif is_mandatory:
                    # Create placeholder for mandatory modules
                    standard_sections.append({
                        'title': default_title,
                        'rationale': f"Mandatory {key} module - review and populate with relevant information",
                        'key_concepts': default_concepts,
                        'type': module_type
                    })
        
        print(f"[DEBUG] Master outline wrapped into {len(standard_sections)} standard sections")
        return standard_sections

    
    def _fetch_source_outlines(self, source_ids: List[str]) -> tuple:
        """
        Fetch outlines with HIERARCHY preserved (section levels).
        Returns: (outlines, course_ids, all_known_concepts_set)
        
        The outlines are structured hierarchically for the LLM to understand parent-child relationships.
        """
        query = """
        UNWIND $source_ids as sid
        MATCH (n) WHERE n.id = sid
        
        // Expand Course into Sections (with variable length path to get levels)
        OPTIONAL MATCH path = (n)-[:HAS_SECTION*]->(child:Section)
        WITH n, child, 
             CASE WHEN child IS NOT NULL THEN length(path) - 1 ELSE 0 END as level
        WITH n, CASE WHEN child IS NOT NULL THEN child ELSE n END as target, level
        
        // Determine Context
        OPTIONAL MATCH (target)<-[:HAS_SECTION*]-(c:Course)
        WITH n, target, level,
             coalesce(c.business_unit, target.business_unit, n.business_unit, 'Unknown') as bu, 
             coalesce(c.id, n.id) as course_id
        
        // Get parent section ID for hierarchy
        OPTIONAL MATCH (parent:Section)-[:HAS_SECTION]->(target)
        WITH n, target, level, bu, course_id, parent.id as parent_section_id
        
        // Get Concepts WITH MAX SCORE (Aggregation)
        OPTIONAL MATCH (target)-[:HAS_SLIDE]->(slide:Slide)-[t:TEACHES]->(con:Concept)
        WITH target, level, bu, course_id, parent_section_id, 
             con.name as c_name, max(coalesce(t.salience, 0)) as max_score
        WHERE c_name IS NOT NULL
        
        RETURN target.id as section_id,
               target.title as section_title,
               level,
               parent_section_id,
               bu,
               course_id,
               collect({name: c_name, score: max_score}) as concepts
        ORDER BY bu, course_id, level, section_id
        """
        results = self.neo4j_client.execute_query(query, {"source_ids": source_ids})
        
        # Build hierarchical structure
        sections_by_id = {}
        outlines = []
        all_known_concepts = set()
        course_ids = set()

        for r in results:
            if not r['section_title']: continue
            
            course_ids.add(r['course_id'])
            
            # Format Concepts: "Name (Primary)"
            formatted_concepts = []
            sorted_concepts = sorted(r['concepts'], key=lambda x: x['score'], reverse=True)
            
            for c in sorted_concepts[:15]:
                all_known_concepts.add(c['name'])
                
                if c['score'] >= 0.8:
                    tag = "(Primary)"
                elif c['score'] >= 0.5:
                    tag = "(Secondary)"
                else:
                    tag = "(Mention)"
                
                formatted_concepts.append(f"{c['name']} {tag}")

            section_data = {
                'id': r['section_id'],
                'bu': r['bu'],
                'section_title': r['section_title'],
                'level': r['level'],
                'parent_id': r['parent_section_id'],
                'concepts': formatted_concepts,
                'subsections': []  # Will be populated below
            }
            
            sections_by_id[r['section_id']] = section_data
        
        # Build hierarchy: attach subsections to their parents
        for section_id, section in sections_by_id.items():
            parent_id = section.get('parent_id')
            if parent_id and parent_id in sections_by_id:
                sections_by_id[parent_id]['subsections'].append(section)
            elif section['level'] == 0:
                # Top-level section
                outlines.append(section)
        
        # If no hierarchy was detected (level always 0), just use flat list
        if not outlines:
            outlines = list(sections_by_id.values())
        
        return outlines, list(course_ids), all_known_concepts
    
    def _find_matching_slides_iterative(self, key_concepts: List[str], allowed_course_ids: List[str] = None) -> List[Dict]:
        """
        Iterative Search: Queries each concept individually to ensure specific coverage.
        Deduplicates results.
        """
        if not key_concepts:
            return []
        
        unique_slides = {} # Map slide_id -> slide_data
        
        # 1. Prioritize the first 5 concepts (usually the most important)
        priority_concepts = key_concepts[:5]
        
        print(f"DEBUG: Searching for concepts: {priority_concepts} in courses: {allowed_course_ids}")

        for concept in priority_concepts:
            try:
                # Build Filter
                where_filter = None
                if allowed_course_ids:
                    where_filter = {
                        "operator": "Or",
                        "operands": [{
                            "path": ["course_id"],
                            "operator": "Equal",
                            "valueString": cid
                        } for cid in allowed_course_ids]
                    }

                # Targeted Query: Just ONE concept at a time
                query = self.weaviate_client.client.query.get(
                    "SlideText", ["slide_id", "text", "course_id"]
                ).with_near_text({
                    "concepts": [concept],
                    "certainty": 0.5  # Lowered from 0.65 for debugging
                }).with_limit(5) # Increased limit for debugging
                
                if where_filter:
                    query = query.with_where(where_filter)
                
                response = query.do()
                
                if "data" in response and "Get" in response["data"]:
                    hits = response["data"]["Get"]["SlideText"]
                    print(f"DEBUG: Concept '{concept}' found {len(hits)} hits")
                    if hits:
                        for hit in hits:
                            sid = hit['slide_id']
                            print(f"DEBUG: Hit: {sid} (Course: {hit.get('course_id')})")
                            if sid not in unique_slides:
                                unique_slides[sid] = {
                                    'slide_id': sid,
                                    'text_preview': hit['text'][:100] + "...",
                                    'match_reason': concept
                                }
                else:
                    print(f"DEBUG: Unexpected Weaviate response: {response}")

            except Exception as e:
                print(f"Search failed for concept '{concept}': {e}")

        # Return list (limit to reasonable number, e.g. 6 slides max per section)
        return list(unique_slides.values())[:6]
    
    def _persist_project(self, sections: List[Dict], title: str = "New Curriculum", user_id: Optional[str] = None) -> str:
        """Create Project and TargetNode entries in Neo4j with hierarchy support"""
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

        # Link to User if provided
        if user_id:
            self.neo4j_client.execute_query(
                """
                MATCH (u:User {id: $user_id})
                MATCH (p:Project {id: $project_id})
                MERGE (u)-[:OWNS]->(p)
                """,
                {"user_id": user_id, "project_id": project_id}
            )
        
        # Create TargetNode entries
        # First pass: create all nodes and build ID mapping
        target_ids = []
        for i, section in enumerate(sections):
            target_id = f"{project_id}_target_{i}"
            target_ids.append(target_id)
            
            level = section.get('level', 0)
            parent_idx = section.get('parent_idx')
            
            # Determine parent node ID
            parent_node_id = project_id if parent_idx is None else target_ids[parent_idx]
            
            # Create TargetNode linked to parent (Project or another TargetNode)
            self.neo4j_client.execute_query(
                """
                MATCH (parent {id: $parent_id})
                CREATE (t:TargetNode {
                    id: $target_id,
                    title: $title,
                    rationale: $rationale,
                    key_concepts: $key_concepts,
                    status: 'suggestion',
                    order: $order,
                    level: $level,
                    is_unassigned: $is_unassigned,
                    is_placeholder: $is_placeholder,
                    section_type: $section_type
                })
                CREATE (parent)-[:HAS_CHILD]->(t)
                """,
                {
                    "parent_id": parent_node_id,
                    "target_id": target_id,
                    "title": section['title'],
                    "rationale": section.get('rationale', ''),
                    "key_concepts": self._normalize_concepts(section.get('key_concepts', [])),
                    "order": i,
                    "level": level,
                    "is_unassigned": section.get('is_unassigned', False),
                    "is_placeholder": section.get('is_placeholder', False),
                    "section_type": section.get('type', 'technical')
                }
            )
            
            # Link to suggested slides
            suggested_layouts = []
            for slide_info in section.get('suggested_slides', []):
                # Query slide layout
                sl_layout_res = self.neo4j_client.execute_query(
                    "MATCH (s:Slide {id: $id}) RETURN s.layout_style as layout",
                    {"id": slide_info['slide_id']}
                )
                if sl_layout_res and sl_layout_res[0]['layout']:
                    suggested_layouts.append(sl_layout_res[0]['layout'])

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
            
            # Smart Default: Set target_layout based on majority of suggested slides
            if suggested_layouts:
                from collections import Counter
                most_common = Counter(suggested_layouts).most_common(1)
                majority_layout = most_common[0][0]
                
                # Update the node with the calculated layout
                self.neo4j_client.execute_query(
                    """
                    MATCH (t:TargetNode {id: $target_id})
                    SET t.target_layout = $layout,
                        t.suggested_layout = $layout
                    """,
                    {"target_id": target_id, "layout": majority_layout}
                )
        
        return project_id
    
    def close(self):
        """Close database connections"""
        self.neo4j_client.close()
