"""
DSPy module for harmonizing multiple course outlines into a single consolidated curriculum
following a configurable Standard Engineering Course Template.
"""
import dspy
import yaml
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

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
            json_structure_lines.append(f'  "{key}": [{{"title": "...", "rationale": "...", "key_concepts": [...]}}],  // MUST be an ARRAY of objects')
        else:
            json_structure_lines.append(f'  "{key}": {{"title": "...", "rationale": "...", "key_concepts": [...]}},  // MUST be a SINGLE object')
    
    # Remove trailing comma from last line
    if json_structure_lines:
        json_structure_lines[-1] = json_structure_lines[-1].rstrip(',  // MUST be a SINGLE object').rstrip(',  // MUST be an ARRAY of objects')
        if ' // MUST be a SINGLE object' in json_structure_lines[-1]:
            json_structure_lines[-1] += '  // MUST be a SINGLE object'
        else:
            json_structure_lines[-1] += '  // MUST be an ARRAY of objects'
    
    prompt = f"""You are an expert Instructional Designer for Engineering.
Given outlines from multiple business units, create a Unified Standard Course.

You MUST follow this template:
{chr(10).join(numbered_list)}

Output as JSON matching this EXACT structure:
{{
{chr(10).join(json_structure_lines)}
}}

CRITICAL INSTRUCTIONS:
1. You MUST include ALL keys shown above in your JSON response - do not omit any!
2. For keys marked "SINGLE object", provide exactly ONE object (not an array).
3. For keys marked "ARRAY of objects", provide a JSON array with multiple objects.
4. Each object must have: title (string), rationale (string), key_concepts (array of strings).
5. If source material does NOT contain relevant concepts for a module:
   - Still include that key in your JSON output
   - Set key_concepts to an EMPTY array []
   - Set rationale to exactly "NO_SOURCE_DATA"
6. DO NOT invent concepts - only use concepts from the source material provided.
7. For array fields like technical_modules, create MULTIPLE modules organized logically (Fundamentals -> Advanced).
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
    """Module that harmonizes outlines into a Standard Template"""
    
    def __init__(self, template_name: str = "standard"):
        super().__init__()
        self.template_modules = load_curriculum_template(template_name)
        print(f"[DEBUG] Loaded {len(self.template_modules)} template modules for '{template_name}'")
        signature_class = create_signature_class(self.template_modules)
        self.generate = dspy.ChainOfThought(signature_class)
    
    def forward(self, source_outlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Args:
            source_outlines: List of dicts from Neo4j (BU, Section, Concepts)
            
        Returns:
            List of dicts (The flattened tree structure for the UI)
        """
        import json
        
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
            final_tree = []
            
            for module_config in self.template_modules:
                key = module_config['key']
                module_type = module_config.get('type', 'technical')
                is_list = module_config.get('is_list', False)
                
                if key in plan_data:
                    if is_list and isinstance(plan_data[key], list):
                        for item in plan_data[key]:
                            item['type'] = module_type
                            final_tree.append(item)
                    elif isinstance(plan_data[key], dict):
                        # Single module
                        section_dict = plan_data[key]
                        section_dict['type'] = module_type
                        final_tree.append(section_dict)
                    else:
                        print(f"[WARN] Unexpected type for key '{key}': {type(plan_data[key])}")
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