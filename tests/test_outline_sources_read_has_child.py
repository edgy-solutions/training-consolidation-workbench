"""Generate Outline on the live graph: sections reach slides over HAS_CHILD, and slides are matched
through the source reader's search (the legacy SlideText class does not exist live)."""
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


class Reader:
    def __init__(self, hits):
        self.hits, self.calls = hits, []

    def search(self, query, course_ids, limit):
        self.calls.append((query, course_ids, limit))
        return self.hits.get(query, [])


def test_section_slides_come_from_the_reader_search():
    svc = GeneratorService.__new__(GeneratorService)
    svc.reader = Reader({"Seal face": ["s1", "s2"], "O-ring": ["s2", "s3"]})
    got = svc._find_matching_slides_iterative(["Seal face", "O-ring"], allowed_course_ids=["sha256:c1"])
    assert [s["slide_id"] for s in got] == ["s1", "s2", "s3"]
    assert got[2]["match_reason"] == "O-ring"
    assert svc.reader.calls == [("Seal face", ["sha256:c1"], 5), ("O-ring", ["sha256:c1"], 5)]


def test_a_failing_search_leaves_the_section_without_slides():
    class Down:
        def search(self, *a):
            raise ConnectionError("weaviate down")
    svc = GeneratorService.__new__(GeneratorService)
    svc.reader = Down()
    assert svc._find_matching_slides_iterative(["Seal face"], allowed_course_ids=["sha256:c1"]) == []
