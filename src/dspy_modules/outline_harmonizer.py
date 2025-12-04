"""
DSPy module for harmonizing multiple course outlines into a single consolidated curriculum
following a Standard Engineering Course Template.
"""
import dspy
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- 1. Input Models ---

class SourceOutline(BaseModel):
    """A section from a source course"""
    bu: str = Field(description="Business unit this section is from")
    section_title: str = Field(description="Title of the section")
    concepts: List[str] = Field(description="Key concepts taught in this section")

# --- 2. Output Models (The "Sandwich" Structure) ---

class TargetSection(BaseModel):
    """A proposed section in the consolidated curriculum"""
    title: str = Field(description="Title for the target section")
    rationale: str = Field(description="Why this section is needed")
    key_concepts: List[str] = Field(description="Top 3-5 concepts to teach")
    # Note: 'suggested_slides' will be populated by the Service layer, not the LLM

class StandardCoursePlan(BaseModel):
    """
    The enforced structure for all Engineering Courses.
    The LLM must populate these specific slots.
    """
    overview: TargetSection = Field(
        description="Module 0: Intro, Purpose, Scope, and Prerequisites."
    )
    safety_module: TargetSection = Field(
        description="Module 1: Safety, Hazards, and Compliance relevant to these specific topics."
    )
    technical_modules: List[TargetSection] = Field(
        description="The core teaching modules. Merge source topics into a logical flow (Fundamentals -> Advanced)."
    )
    assessment: TargetSection = Field(
        description="Module N: Knowledge checks, quizzes, and final review."
    )

# --- 3. The Signature ---

class GenerateConsolidatedSkeleton(dspy.Signature):
    """
    You are an expert Instructional Designer for Engineering.
    Given outlines from multiple business units, create a Unified Standard Course.
    
    You MUST follow the standard template:
    1. Introduction (Overview)
    2. Safety (Mandatory)
    3. Technical Content (Merged & De-duplicated)
    4. Assessment
    
    Output as JSON matching this structure:
    {
      "overview": {"title": "...", "rationale": "...", "key_concepts": [...]},
      "safety_module": {"title": "...", "rationale": "...", "key_concepts": [...]},
      "technical_modules": [{"title": "...", "rationale": "...", "key_concepts": [...]}],
      "assessment": {"title": "...", "rationale": "...", "key_concepts": [...]}
    }
    
    If sources lack safety/assessment content, define placeholder sections anyway.

    CRITICAL INSTRUCTIONS FOR MISSING CONTENT:
    1. You MUST include the standard modules (Introduction, Safety, Assessment) even if source material is missing.
    2. However, if the source material does NOT contain concepts relevant to a module (e.g., no safety info provided):
       - Create the module in the JSON.
       - Set 'key_concepts' to an EMPTY LIST [].
       - Set 'rationale' to "NO_SOURCE_DATA".
    3. DO NOT invent or hallunicate concepts to fill these gaps. Only use concepts derived from the input.
    """
    
    # Input: Raw string representation of the source JSON
    source_outlines: str = dspy.InputField(
        desc="JSON list of source sections with BU, title, and concepts"
    )
    
    # Output: JSON string matching StandardCoursePlan structure
    consolidated_plan: str = dspy.OutputField(
        desc="JSON object with overview, safety_module, technical_modules, and assessment"
    )


# --- 4. The Module ---

class OutlineHarmonizer(dspy.Module):
    """Module that harmonizes outlines into a Standard Template"""
    
    def __init__(self):
        super().__init__()
        # ChainOfThought works with all DSPy versions
        self.generate = dspy.ChainOfThought(GenerateConsolidatedSkeleton)
    
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
            # The LLM should return a JSON object matching StandardCoursePlan
            plan_data = json.loads(prediction.consolidated_plan)
            
            # Validate structure
            if not isinstance(plan_data, dict):
                raise ValueError("Expected dict for StandardCoursePlan")
            
            # 4. Flatten to List (Standard Template Order)
            final_tree = []
            
            # Slot 1: Overview/Introduction
            if 'overview' in plan_data:
                overview_dict = plan_data['overview']
                overview_dict['type'] = 'introduction'
                final_tree.append(overview_dict)
            
            # Slot 2: Safety (Mandatory)
            if 'safety_module' in plan_data:
                safety_dict = plan_data['safety_module']
                safety_dict['type'] = 'mandatory_safety'
                final_tree.append(safety_dict)
            
            # Slot 3: Technical Modules (Core Content)
            if 'technical_modules' in plan_data and isinstance(plan_data['technical_modules'], list):
                for module in plan_data['technical_modules']:
                    module['type'] = 'technical'
                    final_tree.append(module)
            
            # Slot 4: Assessment
            if 'assessment' in plan_data:
                assess_dict = plan_data['assessment']
                assess_dict['type'] = 'mandatory_assessment'
                final_tree.append(assess_dict)
            
            print(f"[DEBUG] Generated standard course with {len(final_tree)} modules")
            return final_tree
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[WARN] Failed to parse StandardCoursePlan: {e}")
            print(f"[WARN] Raw LLM output: {prediction.consolidated_plan}")
            
            # Fallback: Try to parse as a simple list (old format)
            try:
                sections_list = json.loads(prediction.consolidated_plan)
                if isinstance(sections_list, list):
                    # Add default types
                    for s in sections_list:
                        if 'type' not in s:
                            s['type'] = 'technical'
                    return sections_list
            except:
                pass
            
            # Last resort: return source outlines as-is
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