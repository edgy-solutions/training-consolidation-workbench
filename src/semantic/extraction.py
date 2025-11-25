import os
import instructor
from openai import OpenAI
from src.semantic.models import Outline, SlideContent

class LLMExtractor:
    def __init__(self, base_url=None, api_key=None, model=None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY", "ollama") # Ollama doesn't strictly need this, but client might
        self.model = model or os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
        
        # Initialize instructor client
        self.client = instructor.from_openai(
            OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            ),
            mode=instructor.Mode.JSON,
        )

    def extract_outline(self, document_text: str) -> Outline:
        """
        Extract hierarchical outline from the full document text (or TOC text).
        """
        # Truncate if too long? For now assume it fits in context or we pass TOC only.
        prompt = f"""
        Analyze the following document text and extract the hierarchical outline (Table of Contents).
        Identify sections, their levels, and titles.
        
        Document Text:
        {document_text[:20000]} # Naive truncation for now
        """
        
        return self.client.chat.completions.create(
            model=self.model,
            response_model=Outline,
            messages=[{"role": "user", "content": prompt}],
        )

    def extract_concepts(self, slide_text: str) -> SlideContent:
        """
        Extract concepts and learning objectives from a single slide's text.
        """
        prompt = f"""
        Analyze the following text from a training slide.
        Extract key technical concepts taught, define them briefly, and identify learning objectives.
        Also provide a brief summary of the slide.
        
        Slide Text:
        {slide_text}
        """
        
        return self.client.chat.completions.create(
            model=self.model,
            response_model=SlideContent,
            messages=[{"role": "user", "content": prompt}],
        )
