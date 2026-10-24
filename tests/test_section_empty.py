"""The sections route says which sections are empty, while still sending fallback concepts."""
from tests.test_section_parent_id import _sections, client  # noqa: F401


def test_slide_less_concept_less_sections_are_flagged(client):  # noqa: F811
    _, secs = _sections(client, "Corrosion Control")
    inherited = [s for s in secs if s["concepts_inherited"]]
    assert len(secs) == 15 and len(inherited) == 10
    assert all(s["slide_count"] == 0 for s in inherited)
    assert sum(1 for s in secs if s["slide_count"] == 0) == 10


def test_inherited_concepts_are_kept_for_display(client):  # noqa: F811
    _, secs = _sections(client, "Hydraulic Systems Fundamentals")
    inherited = [s for s in secs if s["concepts_inherited"]]
    assert len(inherited) == 1
    assert inherited[0]["concepts"]  # the course fallback still shows
    assert inherited[0]["slide_count"] > 0  # concept-less but not empty
    assert all(not s["concepts_inherited"] for s in secs if s is not inherited[0])
