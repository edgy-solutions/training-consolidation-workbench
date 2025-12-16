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
    
    CRITICAL: You must use ONLY the information provided in the slide_text. 
    Do NOT invent facts, procedures, or technical details not present in the source material.
    The user instruction can modify tone, emphasis, or focus, but cannot add new information.
    
    You must:
    1. Merge the provided slide text into a cohesive narrative (Markdown).
    2. Use ONLY facts, procedures, and details explicitly stated in the slides.
    3. Select the most relevant diagrams/images to support the text.
    4. Extract specific safety warnings into structured 'Callouts'.
    5. Insert placeholders like {{asset_id}} in the markdown where the image should visually appear.
    6. Format content according to the target layout requirements.
    7. DO NOT start with the section title as a heading - the title is already displayed separately in the UI.
       Jump straight into the content.
    
    If the user instruction asks you to "focus on" or "emphasize" something, prioritize that content
    from the slides but do not fabricate new content to fulfill the request.
    
    Output must be valid JSON with these fields:
    - markdown_content: string (the consolidated markdown with {{ASSET_ID}} placeholders)
    - selected_assets: array of strings (asset IDs to include)
    - callouts: array of objects with 'type' and 'text' fields
    """
    
    # Inputs
    slide_text: str = dspy.InputField(desc="Combined text from all source slides - this is the ONLY source of truth for content")
    available_assets: str = dspy.InputField(desc="List of available images/tables with IDs and descriptions")
    section_context: str = dspy.InputField(desc="Context about this section: its title and why it exists (rationale from the AI planner)")
    layout_guidance: str = dspy.InputField(desc="Specific formatting requirements based on the target slide layout")
    instruction: str = dspy.InputField(desc="User's goal for tone/focus (e.g. 'Focus on safety procedures') - cannot add new facts")
    
    # Output (JSON string)
    rich_content: str = dspy.OutputField(desc="JSON object with markdown_content, selected_assets, and callouts")


# --- The Module ---

class ContentSynthesizer(dspy.Module):
    """Module that synthesizes slides into Rich Content"""
    
    def __init__(self):
        super().__init__()
        # Use ChainOfThought like the OutlineHarmonizer
        self.generate = dspy.ChainOfThought(GenerateRichContent)
    
    def forward(self, slides: List[Dict[str, Any]], instruction: str, section_title: str = "", section_rationale: str = "", target_layout: str = "documentary") -> Dict[str, Any]:
        """
        Args:
            slides: List of dicts with keys: id, text, assets (List[SourceAsset])
            instruction: User instructions
            section_title: Title of this section
            section_rationale: AI-generated rationale explaining why this section exists
            target_layout: Layout archetype (hero, documentary, split, grid, content_caption, table, blank)
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

        # 3. Build Section Context
        section_context_parts = []
        if section_title:
            section_context_parts.append(f"Section Title: {section_title}")
        if section_rationale:
            section_context_parts.append(f"Purpose: {section_rationale}")
        section_context_block = "\n".join(section_context_parts) if section_context_parts else "General content section"

        # 4. Build Layout-Specific Guidance
        layout_guidance = self._get_layout_guidance(target_layout)

        # 5. Debug Printing
        print(f"\n[DEBUG] Input Text Length: {len(slide_text_block)}")
        print(f"[DEBUG] Available Assets: {len(asset_descriptions)}")
        print(f"[DEBUG] Section Context: {section_context_block}")
        print(f"[DEBUG] Target Layout: {target_layout}")

        # 6. Call DSPy
        prediction = self.generate(
            slide_text=slide_text_block,
            available_assets=asset_context_block,
            section_context=section_context_block,
            layout_guidance=layout_guidance,
            instruction=instruction
        )
        
        # 5. Parse JSON response
        raw_output = prediction.rich_content
        
        # Strip markdown code blocks if present (LLMs often wrap JSON in ```json ... ```)
        if raw_output.strip().startswith('```'):
            lines = raw_output.strip().split('\n')
            # Remove first line (```json) and last line (```)
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            raw_output = '\n'.join(lines)
        
        try:
            result_data = json.loads(raw_output)
            
            # Validate and create RichSection object
            result = RichSection(**result_data)
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON from LLM: {e}")
            print(f"[ERROR] Raw output: {raw_output[:500]}...")
            
            # Try to extract markdown_content even if JSON is malformed
            import re
            md_match = re.search(r'"markdown_content"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_output, re.DOTALL)
            if md_match:
                markdown = md_match.group(1)
                # Unescape JSON string escapes
                markdown = markdown.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                return {
                    "markdown": markdown,
                    "assets": [],
                    "callouts": []
                }
            
            # Fallback: return a placeholder
            return {
                "markdown": "Error: Failed to parse synthesized content. Please try again.",
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
        # Clean up common LLM artifacts
        markdown = result.markdown_content
        
        # Remove common artifact phrases
        artifacts_to_remove = [
            r'\*?\(End of slide content\)\*?',
            r'\*?End of slide\*?',
            r'\*?---END---\*?',
        ]
        
        import re
        for pattern in artifacts_to_remove:
            markdown = re.sub(pattern, '', markdown, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        markdown = markdown.strip()

        # Fix literal newline characters that were escaped by the LLM
        # Sometimes LLMs output literal "\n" strings instead of actual newlines in JSON
        # This handles both single \n and double \n\n (paragraph breaks)
        markdown = markdown.replace('\\n', '\n')
        
        # We return a dict that the Frontend can easily render
        return {
            "markdown": markdown,
            "assets": [
                # Find the full asset object for the IDs the LLM selected
                next((a for a in all_assets if (a.get('asset_id') if isinstance(a, dict) else a.asset_id) == sel_id), None)
                for sel_id in result.selected_assets
            ],
            "callouts": result.callouts
        }

    def _get_layout_guidance(self, layout: str) -> str:
        """
        Returns specific content formatting guidance based on the target slide layout.
        This helps the LLM generate content that fits the visual structure.
        """
        guidance = {
            "hero": """
LAYOUT: Hero (Title Slide)
FORMAT REQUIREMENTS:
- Keep content VERY brief - this is a title/intro slide
- Create ONE compelling headline (use # H1 heading)
- Optionally add ONE short subtitle or tagline (use ## H2)
- At most 2-3 bullet points if absolutely necessary
- Total word count should be under 50 words
- If there's a key image, select it for background use
- Focus on impact, not details
""",
            "documentary": """
LAYOUT: Documentary (Full Content)
FORMAT REQUIREMENTS:
- Create full narrative content with complete paragraphs
- Use proper heading hierarchy (## for sections, ### for subsections)
- Include detailed explanations and context
- Use bullet lists for procedures or key points
- Can include multiple images/diagrams inline
- This is the most content-rich layout - be thorough
- Include safety callouts where relevant
""",
            "split": """
LAYOUT: Split (Two Columns)
FORMAT REQUIREMENTS:
- Structure content so the FIRST HALF goes in the left column and SECOND HALF goes in the right column
- DO NOT write "Left Column" or "Right Column" as visible headings
- Use a horizontal rule (---) to separate content for the two columns
- Left side (before ---): typically the main text content, procedures, explanations
- Right side (after ---): typically supporting content, image, or related information
- Keep both halves roughly balanced in length
- Example structure:
  Main content paragraph here...
  - Bullet point 1
  - Bullet point 2
  ---
  Supporting content or image reference here...
""",
            "grid": """
LAYOUT: Grid (2x2 or Multi-Image)
FORMAT REQUIREMENTS:
- Structure content as 3-4 SHORT distinct sections
- DO NOT write "Slot 1", "Slot 2" etc as visible headings
- Use horizontal rules (---) to separate each grid item
- Each section should have: a brief topic + 1-2 sentences OR an image reference
- Keep each section under 30 words
- Great for comparing items, showing variations, or step sequences
- Select up to 4 images if available
""",
            "content_caption": """
LAYOUT: Content with Caption (Image Focus)
FORMAT REQUIREMENTS:
- This layout features ONE dominant image
- Select the MOST important/relevant image as the main visual
- Write a concise caption (1-2 sentences) for ## Caption section  
- Add brief supporting text (2-3 bullet points max) for ## Content section
- Total text should be under 75 words
- The image is the star - text is supplementary
""",
            "table": """
LAYOUT: Table/Data
FORMAT REQUIREMENTS:
- Present information in markdown table format where appropriate
- Use | Column1 | Column2 | format for tables
- If no tabular data, structure as key-value pairs
- Keep explanatory text minimal
- Focus on structured, scannable data presentation
""",
            "blank": """
LAYOUT: Blank/Flexible
FORMAT REQUIREMENTS:
- Use your best judgment for content structure
- Keep it reasonably concise
- Default to documentary-style if unclear
"""
        }
        
        return guidance.get(layout, guidance["documentary"])
