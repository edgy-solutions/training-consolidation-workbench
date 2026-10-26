"""Generate Outline reads a section's slides over HAS_CHILD too: the live graph has no Section HAS_SLIDE."""
from src.services.generator_service import GeneratorService


class Graph:
    def __init__(self):
        self.queries = []

    def execute_query(self, query, params=None):
        self.queries.append(query)
        if "HAS_SLIDE|HAS_CHILD" not in query:
            return []  # the live graph: no Section HAS_SLIDE, so no concepts and no rows
        return [{"section_id": "sec1", "section_title": "Mechanical Seals", "level": 0, "parent_section_id": None,
                 "bu": "Fixture Business Unit", "course_id": "sha256:c1",
                 "concepts": [{"name": "Seal face", "score": 0.9}, {"name": "O-ring", "score": 0.4}]}]


def test_sections_reached_over_has_child_give_an_outline():
    svc = GeneratorService.__new__(GeneratorService)
    svc.neo4j_client = Graph()
    outlines, course_ids, concepts = svc._fetch_source_outlines(["sha256:c1"])
    assert list(course_ids) == ["sha256:c1"]
    assert set(concepts) == {"Seal face", "O-ring"}
    assert len(outlines) == 1
