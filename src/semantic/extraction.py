# NOTE: This file assumes 'baml_client' is generated and available in the path.
# If 'baml_client' is missing, you must run `baml-cli generate`.

import os
import asyncio
from typing import List, Tuple

try:
    from baml_client import b
    from baml_client.types import Outline, SlideContent, Section
except ImportError:
    # Fallback or mock for when generation hasn't happened yet (e.g. initial setup)
    # This prevents import errors from crashing Dagster before the user can generate code.
    print("Warning: baml_client not found. Please run `baml-cli generate`.")
    class MockBaml:
        def ExtractOutline(self, text): raise NotImplementedError("BAML not generated")
        def ExtractConcepts(self, text): raise NotImplementedError("BAML not generated")
    b = MockBaml()
    Outline = None
    SlideContent = None
    Section = None

# Token estimation constants
CHARS_PER_TOKEN = 3  # Conservative estimate
RESERVED_TOKENS = 4000  # System prompt, instructions


class LLMExtractor:
    def __init__(self):
        # Calculate chunk size from context
        self.context_size = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        self.max_chars = (self.context_size - RESERVED_TOKENS) * CHARS_PER_TOKEN
        # Overlap at 10% of chunk size
        self.overlap_chars = max(1000, self.max_chars // 10)
        print(f"[LLMExtractor] Context: {self.context_size}, Max chars: {self.max_chars}, Overlap: {self.overlap_chars}")

    def _chunk_text(self, document_text: str) -> List[Tuple[str, int]]:
        """
        Split document into overlapping chunks.
        Returns list of (chunk_text, start_char_position).
        """
        if len(document_text) <= self.max_chars:
            return [(document_text, 0)]
        
        chunks = []
        start = 0
        
        while start < len(document_text):
            end = start + self.max_chars
            chunk = document_text[start:end]
            chunks.append((chunk, start))
            
            # Move start forward, accounting for overlap
            start = end - self.overlap_chars
            
            # Avoid infinite loop if overlap >= chunk size
            if start <= chunks[-1][1]:
                break
        
        print(f"[LLMExtractor] Split document into {len(chunks)} chunks")
        return chunks

    def _merge_outlines(self, partial_outlines: List[Outline]) -> Outline:
        """
        Merge multiple partial outlines into one, deduplicating by page number.
        """
        if not partial_outlines:
            # Return empty outline
            return Outline(sections=[])
        
        if len(partial_outlines) == 1:
            return partial_outlines[0]
        
        # Collect all sections with their page ranges
        all_sections = []
        seen_pages = set()
        
        for outline in partial_outlines:
            if not outline or not hasattr(outline, 'sections'):
                continue
                
            for section in outline.sections:
                start_page = getattr(section, 'start_page', None)
                
                # Skip if we've already seen this page
                if start_page is not None and start_page in seen_pages:
                    continue
                
                if start_page is not None:
                    seen_pages.add(start_page)
                
                all_sections.append(section)
        
        # Sort by start_page
        all_sections.sort(key=lambda s: getattr(s, 'start_page', 0) or 0)
        
        print(f"[LLMExtractor] Merged {len(all_sections)} unique sections from {len(partial_outlines)} chunks")
        
        # Create merged outline
        return Outline(sections=all_sections)

    def extract_outline(self, document_text: str) -> Outline:
        """
        Extract hierarchical outline from the full document text.
        Uses chunking for large documents to avoid context overflow.
        """
        # Check if chunking is needed
        if len(document_text) <= self.max_chars:
            print(f"[LLMExtractor] Document fits in context ({len(document_text)} chars)")
            return asyncio.run(b.ExtractOutline(document_text=document_text))
        
        # Chunk and process
        print(f"[LLMExtractor] Document too large ({len(document_text)} chars), chunking...")
        chunks = self._chunk_text(document_text)
        
        partial_outlines = []
        for i, (chunk_text, start_pos) in enumerate(chunks):
            print(f"[LLMExtractor] Processing chunk {i+1}/{len(chunks)} (starts at char {start_pos})")
            try:
                partial = asyncio.run(b.ExtractOutline(document_text=chunk_text))
                partial_outlines.append(partial)
            except Exception as e:
                print(f"[LLMExtractor] Chunk {i+1} failed: {e}")
        
        # Merge partial outlines
        return self._merge_outlines(partial_outlines)

    def extract_concepts(self, slide_text: str) -> SlideContent:
        """
        Extract concepts and learning objectives from a single slide's text.
        """
        return asyncio.run(b.ExtractConcepts(slide_text=slide_text))
