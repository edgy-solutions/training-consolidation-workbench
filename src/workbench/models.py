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


class TargetDraftNode(BaseModel):
    id: str             # UUID
    title: str
    parent_id: Optional[str] = None
    source_refs: List[str] = [] # List of SourceSlide IDs mapped to this node
    status: str         # "empty", "suggestion", "draft", "complete"
    content_markdown: Optional[str] = None
    
    # Fields for suggestion workflow
    is_suggestion: bool = False
    rationale: Optional[str] = None  # AI-generated rationale for this section
    suggested_source_ids: List[str] = []  # Slide IDs suggested by AI


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


class ProjectTreeResponse(BaseModel):
    """Full project tree structure with all nodes"""
    project_id: str
    title: str
    status: str
    nodes: List[TargetDraftNode]
