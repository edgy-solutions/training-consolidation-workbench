"""
DSPy module for synthesizing slide content into a Rich Content Section (Text + Assets).
"""
import dspy
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# --- Data Models for Structured IO ---

class SourceAsset(BaseModel):
    """Metadata about an image or table available on a slide."""
    asset_id: str
    slide_id: str
    type: str = Field(description="'image', 'table', 'diagram', or 'chart'")
    description: str = Field(description="What is depicted? e.g. 'Wiring Diagram for Pump'")


class RichSection(BaseModel):
    """The synthesized output containing text and asset references."""
    markdown_content: str = Field(
        description="The consolidated text. Use placeholders like {{ASSET_ID}} where images should appear."
    )
    selected_assets: List[str] = Field(
        description="List of asset_ids that were chosen to be included in this section."
    )
    callouts: List[Dict[str, str]] = Field(
        description="Key safety warnings extracted. Format: {'type': 'danger', 'text': '...'}"
    )


# --- DSPy Signature ---

class GenerateRichContent(dspy.Signature):
    """
    Synthesize technical training content from multiple slides.
    
    You must:
    1. Merge the text into a cohesive narrative (Markdown).
    2. Select the most relevant diagrams/images to support the text.
    3. Extract specific safety warnings into structured 'Callouts'.
    4. Insert placeholders like {{asset_id}} in the markdown where the image should visually appear.
    
    Output must be valid JSON with these fields:
    - markdown_content: string (the consolidated markdown with {{ASSET_ID}} placeholders)
    - selected_assets: array of strings (asset IDs to include)
    - callouts: array of objects with 'type' and 'text' fields
    """
    
    # Inputs
    slide_text: str = dspy.InputField(desc="Combined text from all slides")
    available_assets: str = dspy.InputField(desc="List of available images/tables with IDs and descriptions")
    instruction: str = dspy.InputField(desc="User's goal (e.g. 'Focus on safety procedures')")
    
    # Output (JSON string)
    rich_content: str = dspy.OutputField(desc="JSON object with markdown_content, selected_assets, and callouts")


# --- The Module ---

class ContentSynthesizer(dspy.Module):
    """Module that synthesizes slides into Rich Content"""
    
    def __init__(self):
        super().__init__()
        # Use ChainOfThought like the OutlineHarmonizer
        self.generate = dspy.ChainOfThought(GenerateRichContent)
    
    def forward(self, slides: List[Dict[str, Any]], instruction: str) -> Dict[str, Any]:
        """
        Args:
            slides: List of dicts with keys: id, text, assets (List[SourceAsset])
            instruction: User instructions
        """
        
        # 1. Format Text Context
        slide_text_block = "\n\n".join([
            f"--- Slide {s['id']} ---\n{s.get('text', '')}"
            for s in slides
        ])
        
        # 2. Format Asset Context (So the LLM knows what visuals exist)
        # We flatten the list of assets from all slides into one "Menu" for the LLM
        all_assets = []
        asset_descriptions = []
        
        for s in slides:
            for asset in s.get('assets', []):
                # asset is expected to be a dict or SourceAsset object
                a_id = asset.get('asset_id') if isinstance(asset, dict) else asset.asset_id
                desc = asset.get('description', 'No description') if isinstance(asset, dict) else asset.description
                a_type = asset.get('type', 'image') if isinstance(asset, dict) else asset.type
                
                all_assets.append(asset)
                asset_descriptions.append(f"ID: {a_id} | Type: {a_type} | Slide: {s['id']} | Desc: {desc}")

        asset_context_block = "\n".join(asset_descriptions) if asset_descriptions else "No assets available"

        # 3. Debug Printing
        print(f"\n[DEBUG] Input Text Length: {len(slide_text_block)}")
        print(f"[DEBUG] Available Assets: {len(asset_descriptions)}")

        # 4. Call DSPy
        prediction = self.generate(
            slide_text=slide_text_block,
            available_assets=asset_context_block,
            instruction=instruction
        )
        
        # 5. Parse JSON response
        try:
            result_data = json.loads(prediction.rich_content)
            
            # Validate and create RichSection object
            result = RichSection(**result_data)
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON from LLM: {e}")
            print(f"[ERROR] Raw output: {prediction.rich_content}")
            # Fallback: return simple markdown without assets
            return {
                "markdown": prediction.rich_content,  # Use raw output as markdown
                "assets": [],
                "callouts": []
            }
        except Exception as e:
            print(f"[ERROR] Failed to create RichSection: {e}")
            return {
                "markdown": result_data.get("markdown_content", ""),
                "assets": [],
                "callouts": result_data.get("callouts", [])
            }
        
        # 6. Post-Processing / Formatting for UI
        # We return a dict that the Frontend can easily render
        return {
            "markdown": result.markdown_content,
            "assets": [
                # Find the full asset object for the IDs the LLM selected
                next((a for a in all_assets if (a.get('asset_id') if isinstance(a, dict) else a.asset_id) == sel_id), None)
                for sel_id in result.selected_assets
            ],
            "callouts": result.callouts
        }
