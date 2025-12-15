"""
DSPy module for harmonizing multiple course outlines into a single consolidated curriculum
following a configurable Standard Engineering Course Template.

Supports iterative pairwise merging for large inputs to avoid context overflow.
"""
import dspy
import yaml
import os
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Token estimation constants
TOKENS_PER_SECTION = 150  # Average tokens per section (title + concepts + JSON)
RESERVED_PROMPT_TOKENS = 4000  # System prompt, instructions, template
RESERVED_RESPONSE_TOKENS = 2000  # Output buffer

# --- 0. Load Template Configuration ---

def load_curriculum_template(template_name: str = "standard") -> List[Dict]:
    """Load the curriculum template from YAML config."""
    config_path = os.path.join(
        os.path.dirname(__file__), 
        '..', '..', 'config', 'templates', f'{template_name}.yaml'
    )
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('modules', [])
    except FileNotFoundError:
        print(f"[WARN] Template '{template_name}' not found at {config_path}, using defaults")
        return []

TEMPLATE_MODULES = load_curriculum_template()

def build_dynamic_prompt(template_modules: List[Dict]) -> str:
    """Build the LLM prompt dynamically from YAML config."""
    if not template_modules:
        return "You are an expert Instructional Designer. Create a unified course structure."
    
    # Build numbered list and JSON structure
    numbered_list = []
    json_structure_lines = []
    
    for i, module in enumerate(template_modules):
        key = module['key']
        is_list = module.get('is_list', False)
        desc = module.get('description', '')
        
        # For list modules, use description; for single modules, use title
        if is_list:
            display_name = desc.split('.')[0] if desc else key.replace('_', ' ').title()
        else:
            display_name = module.get('title') or key.replace('_', ' ').title()
        
        numbered_list.append(f"{i+1}. {display_name}")
        
        if is_list:
            # List modules can have subsections
            json_structure_lines.append(f'  "{key}": [  // ARRAY of module objects')
            json_structure_lines.append(f'    {{"title": "...", "rationale": "...", "key_concepts": [...], "subsections": [')
            json_structure_lines.append(f'      {{"title": "...", "rationale": "...", "key_concepts": [...]}}')
            json_structure_lines.append(f'    ]}}')
            json_structure_lines.append(f'  ],')
        else:
            json_structure_lines.append(f'  "{key}": {{"title": "...", "rationale": "...", "key_concepts": [...]}},  // SINGLE object')
    
    # Remove trailing comma from last line
    if json_structure_lines:
        last_line = json_structure_lines[-1]
        if last_line.endswith(','):
            json_structure_lines[-1] = last_line.rstrip(',')
    
    prompt = f"""You are an expert Instructional Designer for Engineering.
Given outlines from multiple business units, create a Unified Standard Course.

The source outlines may include HIERARCHICAL sections (modules with subsections).
Preserve this hierarchy in your output where appropriate.

You MUST follow this template:
{chr(10).join(numbered_list)}

Output as JSON matching this EXACT structure:
{{
{chr(10).join(json_structure_lines)}
}}

CRITICAL INSTRUCTIONS:
1. You MUST include ALL keys shown above in your JSON response - do not omit any!
2. For keys marked "SINGLE object", provide exactly ONE object (not an array).
3. For keys marked "ARRAY of module objects", provide a JSON array.
4. Each object must have: title (string), rationale (string), key_concepts (array of strings).
5. For ARRAY modules (like technical_modules), you MAY include a "subsections" array to group related topics.
   - Subsections are OPTIONAL but encouraged for complex topics.
   - Each subsection has the same structure: title, rationale, key_concepts.
6. If source material does NOT contain relevant concepts for a module:
   - Still include that key in your JSON output
   - Set key_concepts to an EMPTY array []
   - Set rationale to exactly "NO_SOURCE_DATA"
7. DO NOT invent concepts - only use concepts from the source material provided.
8. For array fields, create MULTIPLE modules organized logically (Fundamentals -> Advanced).
"""
    
    return prompt

# --- 1. Input Models ---

class SourceOutline(BaseModel):
    """A section from a source course"""
    bu: str = Field(description="Business unit this section is from")
    section_title: str = Field(description="Title of the section")
    concepts: List[str] = Field(description="Key concepts taught in this section")

# --- 2. Output Models ---

class TargetSection(BaseModel):
    """A proposed section in the consolidated curriculum"""
    title: str = Field(description="Title for the target section")
    rationale: str = Field(description="Why this section is needed")
    key_concepts: List[str] = Field(description="Top 3-5 concepts to teach")

# --- 3. The Signature (Dynamic) ---

def create_signature_class(template_modules: List[Dict]):
    """Create a dynamic signature class based on template"""
    class GenerateConsolidatedSkeleton(dspy.Signature):
        __doc__ = build_dynamic_prompt(template_modules)
        
        # Input: Raw string representation of the source JSON
        source_outlines: str = dspy.InputField(
            desc="JSON list of source sections with BU, title, and concepts"
        )
        
        # Output: JSON string matching StandardCoursePlan structure
        consolidated_plan: str = dspy.OutputField(
            desc="JSON object matching the template structure with ALL required keys"
        )
    
    return GenerateConsolidatedSkeleton

# --- 4. The Module ---

class OutlineHarmonizer(dspy.Module):
    """Module that harmonizes outlines into a Standard Template with iterative merging"""
    
    def __init__(self, template_name: str = "standard"):
        super().__init__()
        self.template_modules = load_curriculum_template(template_name)
        print(f"[DEBUG] Loaded {len(self.template_modules)} template modules for '{template_name}'")
        signature_class = create_signature_class(self.template_modules)
        self.generate = dspy.ChainOfThought(signature_class)
        
        # Calculate max sections per merge based on context
        self.max_sections_per_merge = self._calculate_max_sections()
    
    def _calculate_max_sections(self) -> int:
        """Calculate maximum sections that fit in context window."""
        context_size = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        usable_tokens = context_size - RESERVED_PROMPT_TOKENS - RESERVED_RESPONSE_TOKENS
        max_sections = max(10, usable_tokens // TOKENS_PER_SECTION)  # Minimum 10 sections
        print(f"[OutlineHarmonizer] Context: {context_size}, Max sections per merge: {max_sections}")
        return max_sections
    
    def _estimate_section_count(self, outlines: List[Dict]) -> int:
        """Estimate total section count including subsections."""
        count = 0
        for outline in outlines:
            count += 1
            subsections = outline.get('subsections', [])
            if subsections:
                count += len(subsections)
        return count
    
    def _group_by_bu(self, outlines: List[Dict]) -> Dict[str, List[Dict]]:
        """Group outlines by business unit."""
        grouped = {}
        for outline in outlines:
            bu = outline.get('bu', 'Unknown')
            if bu not in grouped:
                grouped[bu] = []
            grouped[bu].append(outline)
        return grouped
    
    def _merge_two_groups(self, group1: List[Dict], group2: List[Dict]) -> List[Dict]:
        """Merge two groups of outlines using LLM."""
        combined = group1 + group2
        
        # Call LLM to merge
        source_json_str = json.dumps(combined, indent=2)
        prediction = self.generate(source_outlines=source_json_str)
        
        # Parse output and convert back to outline format
        try:
            json_str = prediction.consolidated_plan.strip()
            if json_str.startswith('```'):
                lines = json_str.split('\n')
                lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                json_str = '\n'.join(lines)
            
            plan_data = json.loads(json_str)
            
            # Flatten the plan back into outline format for further merging
            merged_outlines = []
            for module_config in self.template_modules:
                key = module_config['key']
                if key in plan_data:
                    data = plan_data[key]
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                merged_outlines.append({
                                    'bu': 'Merged',
                                    'section_title': item.get('title', key),
                                    'concepts': item.get('key_concepts', []),
                                    'subsections': item.get('subsections', [])
                                })
                    elif isinstance(data, dict):
                        merged_outlines.append({
                            'bu': 'Merged',
                            'section_title': data.get('title', key),
                            'concepts': data.get('key_concepts', []),
                            'subsections': data.get('subsections', [])
                        })
            
            return merged_outlines
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[WARN] Failed to parse merge result: {e}")
            # Fallback: just concatenate
            return combined
    
    def _iterative_merge(self, outlines: List[Dict]) -> List[Dict]:
        """
        Iteratively merge outlines in pairs to stay within context limits.
        Like merge sort - merge pairs until only one result remains.
        """
        # Group by BU first
        by_bu = self._group_by_bu(outlines)
        groups = list(by_bu.values())
        
        print(f"[IterativeMerge] Starting with {len(groups)} BU groups")
        
        round_num = 1
        while len(groups) > 1:
            print(f"[IterativeMerge] Round {round_num}: {len(groups)} groups")
            new_groups = []
            
            # Pair up groups
            i = 0
            while i < len(groups):
                if i + 1 < len(groups):
                    # Merge pair
                    combined_count = self._estimate_section_count(groups[i]) + self._estimate_section_count(groups[i+1])
                    
                    if combined_count <= self.max_sections_per_merge:
                        print(f"  Merging groups {i} and {i+1} ({combined_count} sections)")
                        merged = self._merge_two_groups(groups[i], groups[i+1])
                        new_groups.append(merged)
                    else:
                        # Too big to merge together, keep separate for now
                        print(f"  Groups {i} and {i+1} too large ({combined_count} > {self.max_sections_per_merge}), keeping separate")
                        new_groups.append(groups[i])
                        new_groups.append(groups[i+1])
                    i += 2
                else:
                    # Odd one out, carry forward
                    new_groups.append(groups[i])
                    i += 1
            
            # Check for progress
            if len(new_groups) >= len(groups):
                print(f"[IterativeMerge] No progress made, breaking")
                break
            
            groups = new_groups
            round_num += 1
        
        # Return the final merged group
        if groups:
            return groups[0]
        return outlines
    
    def forward(self, source_outlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Args:
            source_outlines: List of dicts from Neo4j (BU, Section, Concepts)
            
        Returns:
            List of dicts (The flattened tree structure for the UI)
        """
        # Check if iterative merging is needed
        section_count = self._estimate_section_count(source_outlines)
        print(f"[OutlineHarmonizer] Input: {section_count} sections (max per merge: {self.max_sections_per_merge})")
        
        if section_count > self.max_sections_per_merge:
            print(f"[OutlineHarmonizer] Using iterative merge strategy")
            source_outlines = self._iterative_merge(source_outlines)
        
        # 1. Prepare Input
        source_json_str = json.dumps(source_outlines, indent=2)
        
        # 2. Call DSPy
        prediction = self.generate(source_outlines=source_json_str)
        
        print(f"\n{'='*60}")
        print("[DEBUG] Raw LLM Response:")
        print(prediction.consolidated_plan)
        print(f"{'='*60}\n")
        
        # 3. Parse the JSON output
        try:
            # Strip markdown code fences if present
            json_str = prediction.consolidated_plan.strip()
            if json_str.startswith('```'):
                # Remove opening fence
                lines = json_str.split('\n')
                lines = lines[1:]  # Remove first line (```json or ```)
                # Remove closing fence
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                json_str = '\n'.join(lines)
            
            plan_data = json.loads(json_str)
            
            if not isinstance(plan_data, dict):
                raise ValueError("Expected dict for StandardCoursePlan")
            
            print(f"[DEBUG] LLM returned keys: {list(plan_data.keys())}")
            print(f"[DEBUG] Expected keys: {[m['key'] for m in self.template_modules]}")
            
            # 4. Flatten to List using YAML config order
            # Each item gets a 'level' field (0 = top-level, 1+ = subsections)
            final_tree = []
            
            def flatten_with_hierarchy(items: List, module_type: str, level: int = 0, parent_idx: int = None):
                """Recursively flatten items with subsections into flat list with level info"""
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    current_idx = len(final_tree)
                    item['type'] = module_type
                    item['level'] = level
                    item['parent_idx'] = parent_idx  # For linking later
                    final_tree.append(item)
                    
                    # Process subsections if present
                    subsections = item.pop('subsections', [])
                    if subsections and isinstance(subsections, list):
                        flatten_with_hierarchy(subsections, module_type, level + 1, current_idx)
            
            for module_config in self.template_modules:
                key = module_config['key']
                module_type = module_config.get('type', 'technical')
                is_list = module_config.get('is_list', False)
                
                if key in plan_data:
                    data = plan_data[key]
                    
                    # Handle Type Mismatches (LLM returning list for single item or vice versa)
                    if is_list:
                        # Expecting list, but got dict -> wrap in list
                        if isinstance(data, dict):
                            data = [data]
                        
                        if isinstance(data, list):
                            flatten_with_hierarchy(data, module_type, level=0)
                    else:
                        # Expecting single dict
                        if isinstance(data, list):
                            # Got list -> take first item if available
                            if len(data) > 0 and isinstance(data[0], dict):
                                data = data[0]
                            else:
                                print(f"[WARN] Key '{key}' is a list but empty or invalid")
                                continue
                        
                        if isinstance(data, dict):
                            data['type'] = module_type
                            data['level'] = 0
                            data['parent_idx'] = None
                            final_tree.append(data)
                        else:
                            print(f"[WARN] Unexpected type for key '{key}': {type(data)}")
                else:
                    print(f"[WARN] Missing expected key '{key}' in LLM response")
            
            print(f"[DEBUG] Generated standard course with {len(final_tree)} modules")
            return final_tree
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[WARN] Failed to parse StandardCoursePlan: {e}")
            print(f"[WARN] Raw LLM output: {prediction.consolidated_plan}")
            
            # Fallback: Try to parse as a simple list (old format)
            try:
                sections_list = json.loads(prediction.consolidated_plan)
                if isinstance(sections_list, list):
                    for s in sections_list:
                        if 'type' not in s:
                            s['type'] = 'technical'
                    return sections_list
            except:
                pass
            
            print("[ERROR] Using fallback: returning source outlines")
            return self._fallback_merge(source_outlines)
    
    def _fallback_merge(self, source_outlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Emergency fallback if DSPy fails completely"""
        sections = []
        for source in source_outlines:
            sections.append({
                "title": source['section_title'],
                "rationale": f"Based on content from {source['bu']}",
                "key_concepts": source['concepts'][:5],
                "type": "technical"
            })
        return sections