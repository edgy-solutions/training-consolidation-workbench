"""
Service for generating consolidated curricula from source materials.
"""
import uuid
import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from src.storage.neo4j import Neo4jClient
from src.storage.weaviate import WeaviateClient
from src.dspy_modules.outline_harmonizer import OutlineHarmonizer
from src.dspy_modules.config import shared_lm as lm
import dspy

# Configure DSPy using shared configuration
# load_dotenv() and dspy.configure() are handled in src.dspy_modules.config


class GeneratorService:
    """Service for generating consolidated curricula"""
    
    def __init__(self):
        self.neo4j_client = Neo4jClient()
        self.weaviate_client = WeaviateClient()
        self.harmonizer = OutlineHarmonizer()
    
    def generate_skeleton(self, selected_source_ids: List[str], title: str = "New Curriculum", master_course_id: Optional[str] = None) -> Dict[str, Any]:
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
        source_outlines, source_course_ids = self._fetch_source_outlines(selected_source_ids)
        
        if not source_outlines:
            raise ValueError("No source outlines found for the given IDs")
        
        print(f"DEBUG: Found {len(source_course_ids)} source course IDs: {source_course_ids}")
        
        # Step 2: Generate consolidated plan
        if master_course_id:
            # Use the master course's outline as the structure
            print(f"DEBUG: Using master outline from course: {master_course_id}")
            consolidated_sections = self._use_master_outline(master_course_id)
        else:
            # Call DSPy to generate consolidated plan using Standard Template
            print("DEBUG: Calling harmonizer with Standard Course Template...")
            consolidated_sections = self.harmonizer(source_outlines)
            
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
            suggested_slides = self._find_matching_slides(
                section.get('key_concepts', []),
                allowed_course_ids=source_course_ids
            )
            enriched_sections.append({
                **section,
                'suggested_slides': suggested_slides
            })
        
        # Step 4: Calculate Unassigned Slides (Set Difference)
        # Get all available slides from the source courses
        all_source_slides = self._fetch_all_slides_for_courses(source_course_ids)
        all_slide_ids = set(s['id'] for s in all_source_slides)
        
        # Get all assigned slides
        assigned_slide_ids = set()
        for section in enriched_sections:
            for slide in section.get('suggested_slides', []):
                assigned_slide_ids.add(slide['slide_id'])
                
        # Calculate difference
        unassigned_ids = all_slide_ids - assigned_slide_ids
        
        # Create "Unassigned" section if there are leftovers
        if unassigned_ids:
            print(f"DEBUG: Found {len(unassigned_ids)} unassigned slides")
            # We need text previews for these. We can get them from all_source_slides
            unassigned_slides_data = [
                {
                    'slide_id': s['id'],
                    'text_preview': s['text'][:100] + "..."
                }
                for s in all_source_slides if s['id'] in unassigned_ids
            ]
            
            enriched_sections.append({
                'title': "Unassigned / For Review",
                'rationale': "Slides available in source material but not explicitly assigned to a specific section by the AI.",
                'key_concepts': [],
                'suggested_slides': unassigned_slides_data,
                'is_unassigned': True  # Flag for frontend styling
            })

        # Step 5: Create Project and persist to Neo4j
        project_id = self._persist_project(enriched_sections, title=title)
        
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
        Wraps sections into the standard template: Introduction → Safety → Technical → Assessment
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
        
        # Build standard template structure from master sections
        standard_sections = []
        
        # 1. Introduction (use first section or create placeholder)
        intro_section = results[0] if results else None
        if intro_section:
            standard_sections.append({
                'title': intro_section['title'],
                'rationale': f"Introduction from master course: {intro_section['title']}",
                'key_concepts': intro_section.get('concepts', [])[:10],
                'type': 'introduction'
            })
        else:
            standard_sections.append({
                'title': 'Course Introduction',
                'rationale': 'Placeholder introduction section',
                'key_concepts': [],
                'type': 'introduction'
            })
        
        # 2. Safety Module (create placeholder - master courses typically don't have explicit safety sections)
        standard_sections.append({
            'title': 'Safety and Compliance',
            'rationale': 'Mandatory safety module - review and populate with relevant safety information',
            'key_concepts': ['Safety Procedures', 'Hazard Identification', 'Compliance Requirements'],
            'type': 'mandatory_safety'
        })
        
        # 3. Technical Content (all remaining master sections except last)
        technical_sections = results[1:-1] if len(results) > 2 else results[1:] if len(results) > 1 else []
        for section in technical_sections:
            standard_sections.append({
                'title': section['title'],
                'rationale': f"Technical content from master course: {section['title']}",
                'key_concepts': section.get('concepts', [])[:10],
                'type': 'technical'
            })
        
        # 4. Assessment (use last section or create placeholder)
        if len(results) > 1:
            last_section = results[-1]
            standard_sections.append({
                'title': last_section['title'],
                'rationale': f"Assessment from master course: {last_section['title']}",
                'key_concepts': last_section.get('concepts', [])[:10],
                'type': 'mandatory_assessment'
            })
        else:
            standard_sections.append({
                'title': 'Knowledge Assessment',
                'rationale': 'Placeholder assessment section',
                'key_concepts': ['Quiz', 'Review', 'Final Assessment'],
                'type': 'mandatory_assessment'
            })
        
        print(f"[DEBUG] Master outline wrapped into {len(standard_sections)} standard sections")
        return standard_sections

    
    def _fetch_source_outlines(self, source_ids: List[str]) -> tuple:
        """
        Fetch section titles and concept summaries from Neo4j.
        Handles both Course and Section IDs.
        Returns (outlines, course_ids).
        """
        # We need to handle two cases:
        # 1. Input is a Course -> Get all its concepts
        # 2. Input is a Section -> Get its specific concepts via HAS_SLIDE
        
        query = """
        UNWIND $source_ids as sid
        MATCH (n) WHERE n.id = sid
        
        // Expand Course into Sections if available
        OPTIONAL MATCH (n)-[:HAS_SECTION*]->(child:Section)
        WITH n, collect(child) as children
        
        // If we found sections, use them. Otherwise, treat the input node 'n' as the unit (e.g. a flat Course or a single Section)
        WITH n, CASE WHEN size(children) > 0 THEN children ELSE [n] END as targets
        
        UNWIND targets as target
        
        // Determine context (Business Unit and Course ID)
        OPTIONAL MATCH (target)<-[:HAS_SECTION*]-(c:Course)
        WITH n, target, 
             coalesce(c.business_unit, target.business_unit, n.business_unit, 'Unknown') as bu, 
             coalesce(c.id, n.id) as course_id
        
        // Get concepts from linked slides (HAS_SLIDE)
        OPTIONAL MATCH (target)-[:HAS_SLIDE]->(slide:Slide)-[t:TEACHES]->(con:Concept)
        WHERE coalesce(t.salience, 0) >= 0.5
        
        WITH target, bu, course_id, collect(DISTINCT con.name) as concepts
        
        // Filter out empty targets unless they are explicitly sections (to preserve structure)
        // WHERE size(concepts) > 0 OR target:Section
        
        RETURN target.title as section_title,
               bu,
               course_id,
               concepts[0..15] as concepts
        ORDER BY bu, course_id
        """
        results = self.neo4j_client.execute_query(query, {"source_ids": source_ids})
        
        outlines = [
            {
                'bu': r['bu'],
                'section_title': r['section_title'],
                'concepts': r['concepts'] or []
            }
            for r in results if r['section_title']
        ]
        
        # Collect unique course IDs for slide filtering
        course_ids = list(set(r['course_id'] for r in results if r.get('course_id')))
        
        return outlines, course_ids
    
    def _find_matching_slides(self, key_concepts: List[str], top_n: int = 3, allowed_course_ids: List[str] = None) -> List[Dict]:
        """Use Weaviate to find slides that best match the concepts, optionally filtered by course IDs"""
        if not key_concepts:
            return []
        
        # Combine concepts into a search query
        search_query = " ".join(key_concepts)
        
        try:
            # Build the query
            query = self.weaviate_client.client.query.get(
                "SlideText", ["slide_id", "text", "course_id"]  # Also retrieve course_id for debugging
            ).with_near_text({
                "concepts": [search_query],
                "certainty": 0.6
            }).with_limit(top_n * 3 if allowed_course_ids else top_n)  # Get more results before filtering
            
            # Add course ID filter if provided
            if allowed_course_ids:
                # Weaviate where filter for course_id
                where_filter = {
                    "operator": "Or",
                    "operands": [
                        {
                            "path": ["course_id"],
                            "operator": "Equal",
                            "valueString": course_id
                        }
                        for course_id in allowed_course_ids
                    ]
                }
                query = query.with_where(where_filter)
            
            response = query.do()
            
            if "data" in response and "Get" in response["data"]:
                slides = response["data"]["Get"]["SlideText"]
                if not slides:
                    print(f"DEBUG: No slides found for query: '{search_query}' with {len(allowed_course_ids) if allowed_course_ids else 'no'} course filters")
                else:
                    print(f"DEBUG: Found {len(slides)} slides for query: '{search_query}', courses: {allowed_course_ids}")
                
                # Return top_n results
                return [
                    {
                        'slide_id': s['slide_id'],
                        'text_preview': s['text'][:100] + "..."
                    }
                    for s in slides[:top_n]
                ]
        except Exception as e:
            print(f"Error finding matching slides: {e}")
            import traceback
            traceback.print_exc()
        
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
                    order: $order,
                    is_unassigned: $is_unassigned
                })
                CREATE (p)-[:HAS_CHILD]->(t)
                """,
                {
                    "project_id": project_id,
                    "target_id": target_id,
                    "title": section['title'],
                    "rationale": section['rationale'],
                    "key_concepts": section.get('key_concepts', []),
                    "order": i,
                    "is_unassigned": section.get('is_unassigned', False)
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
