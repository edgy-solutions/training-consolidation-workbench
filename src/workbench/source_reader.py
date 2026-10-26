"""The workbench's read-side port: one method per need (N1-N8).

Implementations return plain JSON-able dicts/lists. Concept values are RAW
doc-tools concept names; display names (CanonicalConcept) are the workbench's
own business, see alignment.py.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "training"


class SourceReader(Protocol):
    def list_courses(self, discipline: Optional[str]) -> List[dict]:
        """{id, title, business_unit, discipline, filename, version} (last two null when absent); case-insensitive substring filter on
        discipline; sorted by (business_unit, title)."""

    def facets(self) -> Dict[str, List[str]]:
        """business_unit, discipline, pedagogical_intent, asset_type: distinct, sorted, no nulls."""

    def course_slides(self, course_id: str) -> List[dict]:
        """{id, number, text} sorted by number."""

    def course_sections(self, course_id: str) -> List[dict]:
        """{id, parent_id, title, level, start_page, end_page, concept_summary, slide_ids,
        covers: [{concept, score}] score desc}."""

    def slide(self, slide_id: str) -> Optional[dict]:
        """{id, course_id, number, text, elements (JSON string), asset_type, layout_style,
        teaches: [{concept, salience}]} or None."""

    def slides(self, slide_ids: List[str]) -> List[dict]:
        """Same shape as slide(); missing ids skipped."""

    def page_preview_url(self, slide_id: str) -> Optional[str]: ...

    def embedded_images(self, course_id: str) -> List[dict]:
        """{ref, name, page_number, coordinates|None}."""

    def resolve_ref(self, ref: str) -> Optional[str]:
        """Stable reference -> fetchable URL."""

    def concept_names(self) -> List[str]: ...

    def slides_teaching(self, names: List[str]) -> List[dict]:
        """{course_id, slide_id, concept, salience}."""

    def search(self, query: str, course_ids: Optional[List[str]], limit: int) -> List[str]:
        """Ranked slide ids."""


_cache: Dict[tuple, SourceReader] = {}


def reset_source_reader_cache() -> None:
    _cache.clear()


def serves_assets(reader) -> bool:
    """True for readers that hold image and page bytes (fixture and store)."""
    return callable(getattr(reader, "asset", None))


def get_source_reader() -> Optional[SourceReader]:
    """None for the legacy direct-store path (SOURCE_READER unset or 'direct')."""
    mode = os.getenv("SOURCE_READER", "").strip().lower()
    if mode in ("", "direct"):
        return None
    if mode == "fixture":
        fixture_dir = os.getenv("SOURCE_FIXTURE_DIR") or str(DEFAULT_FIXTURE_DIR)
        key = (mode, fixture_dir)
        if key not in _cache:
            from src.workbench.fixture_reader import load_fixture_reader
            _cache[key] = load_fixture_reader(fixture_dir)
        return _cache[key]
    if mode == "store":
        key = (mode,)
        if key not in _cache:
            from src.workbench.store_reader import build_store_reader
            _cache[key] = build_store_reader()
        return _cache[key]
    raise ValueError(f"Unknown SOURCE_READER value: {mode!r}")
