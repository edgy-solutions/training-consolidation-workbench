from typing import List, Optional
from pydantic import BaseModel, Field

class Section(BaseModel):
    title: str
    level: int
    page_number: Optional[int] = None
    subsections: List["Section"] = Field(default_factory=list)

class Outline(BaseModel):
    sections: List[Section]

class Concept(BaseModel):
    name: str
    description: str
    related_terms: List[str] = Field(default_factory=list)

class LearningObjective(BaseModel):
    description: str

class SlideContent(BaseModel):
    concepts: List[Concept]
    objectives: List[LearningObjective]
    summary: str
