from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ConceptNode(BaseModel):
    name: str
    domain: str
    salience: Optional[float] = None


class SourceSlide(BaseModel):
    id: str             # {doc_uuid}_{page_index}
    s3_url: str         # Presigned URL
    text_preview: str
    concepts: List[ConceptNode]
    elements: Optional[List[Dict[str, Any]]] = None


class TargetDraftNode(BaseModel):
    id: str             # UUID
    title: str
    parent_id: Optional[str] = None
    source_refs: List[str] = [] # List of SourceSlide IDs mapped to this node
    status: str         # "empty", "suggestion", "draft", "complete"
    content_markdown: Optional[str] = None
    
    # Fields for suggestion workflow
    is_suggestion: bool = False
    is_placeholder: bool = False # Flag for "NO_SOURCE_DATA" sections
    is_unassigned: bool = False # Flag for "Unassigned / For Review" section
    section_type: Optional[str] = None # Template section type (introduction, mandatory_safety, technical, mandatory_assessment)
    rationale: Optional[str] = None  # AI-generated rationale for this section
    suggested_source_ids: List[str] = []  # Slide IDs suggested by AI
    
    # Layout Control
    target_layout: str = "documentary"  # Default layout
    suggested_layout: Optional[str] = None # Derived from source slides
    
    order: Optional[int] = 0 # Display order
    level: Optional[int] = 0 # Hierarchy level: 0 = top-level, 1+ = subsection
    created_at: Optional[Any] = None # Creation timestamp


class SynthesisRequest(BaseModel):
    target_node_id: str
    tone_instruction: str


class SearchRequest(BaseModel):
    query: Optional[str] = None
    filters: Dict[str, Any] = {} # domain, origin, intent, type


class GenerateSkeletonRequest(BaseModel):
    """Request to generate a consolidated curriculum skeleton"""
    source_ids: List[str] = Field(
        description="List of Section or Course IDs to merge into curriculum"
    )


class SuggestedSlide(BaseModel):
    """A slide suggested as source material for a target section"""
    slide_id: str
    text_preview: str


class TargetSectionResponse(BaseModel):
    """A section in the generated curriculum"""
    title: str
    rationale: str
    key_concepts: List[str]
    suggested_slides: List[SuggestedSlide]


class GenerateSkeletonResponse(BaseModel):
    """Response from curriculum generation"""
    project_id: str
    sections: List[TargetSectionResponse]


class SkeletonRequest(BaseModel):
    """Request to generate a curriculum skeleton for a new project"""
    title: str = Field(description="Title for the new curriculum project")
    domain: Optional[str] = Field(None, description="Engineering domain/discipline")
    selected_source_ids: List[str] = Field(description="Source section/course IDs to merge")
    master_course_id: Optional[str] = Field(None, description="If provided, use this course's outline as the master structure")
    template_name: Optional[str] = Field("standard", description="Template to use for curriculum generation")


class RenderRequest(BaseModel):
    project_id: str
    format: str = "pptx" # "pptx" or "typ"
    template_name: Optional[str] = "standard"

class ProjectTreeResponse(BaseModel):
    """Full project tree structure with all nodes"""
    project_id: str
    title: str
    status: str
    nodes: List[TargetDraftNode]
