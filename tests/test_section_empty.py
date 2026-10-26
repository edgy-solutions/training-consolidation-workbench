"""The sections route says which sections are empty, while still sending fallback concepts."""
from src.workbench.source_routes import _port_course_sections
from tests.test_section_parent_id import _sections, client  # noqa: F401


class _Reader:
    """One course: a section with slides and concepts, one empty, one with slides but no concepts.
    Built here because tr's goldens sample their sections (step g), so no deck keeps an empty one."""

    def course_sections(self, cid):
        return [{"id": "c_s1", "title": "Full", "start_page": 1, "covers": [{"concept": "Pumps"}], "slide_ids": ["a"]},
                {"id": "c_s2", "title": "Empty", "start_page": 2, "covers": [], "slide_ids": []},
                {"id": "c_s3", "title": "Concept-less", "start_page": 3, "covers": [], "slide_ids": ["b"]}]

    def course_slides(self, cid):
        return [{"id": "a"}, {"id": "b"}]

    def slides(self, ids):
        return [{"id": "a", "teaches": [{"concept": "Pumps", "salience": 1.0}]}, {"id": "b", "teaches": []}]


class _Alignment:
    def display_names(self, names):
        return {n: n for n in names}


def test_slide_less_concept_less_sections_are_flagged():
    secs = {s["title"]: s for s in _port_course_sections(_Reader(), _Alignment(), "c")}
    assert secs["Empty"]["slide_count"] == 0 and secs["Empty"]["concepts_inherited"]
    assert secs["Empty"]["concepts"] == ["Pumps"]  # the course fallback still shows
    assert secs["Concept-less"]["concepts_inherited"] and secs["Concept-less"]["slide_count"] == 1
    assert not secs["Full"]["concepts_inherited"]


def test_inherited_concepts_are_kept_for_display(client):  # noqa: F811
    _, secs = _sections(client, "Hydraulic Systems Fundamentals")
    inherited = [s for s in secs if s["concepts_inherited"]]
    assert len(inherited) == 1
    assert inherited[0]["concepts"]  # the course fallback still shows
    assert inherited[0]["slide_count"] > 0  # concept-less but not empty
    assert all(not s["concepts_inherited"] for s in secs if s is not inherited[0])
