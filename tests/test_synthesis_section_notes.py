"""Source Section notes reach synthesis as orientation, one per slide, and only when there are any."""
import json

from src.dspy_modules.synthesizer import ContentSynthesizer
from src.services.synthesis_service import SECTION_NOTES_QUERY, SynthesisService, section_notes


def row(sec_id, slide="s1", level=1, start=1, end=5, title=None, summary="sum", objectives=None):
    return {"slide_id": slide, "id": sec_id, "title": title or f"T-{sec_id}", "level": level,
            "start_page": start, "end_page": end, "summary": summary, "objectives": objectives}


def ids(rows):
    return [n["id"] for n in section_notes(rows)]


# 1. section_notes

def test_deepest_section_wins_over_parent():
    assert ids([row("parent", level=1), row("child", level=2)]) == ["child"]


def test_same_level_narrower_span_wins():
    assert ids([row("wide", start=1, end=20), row("narrow", start=3, end=5)]) == ["narrow"]


def test_open_end_page_loses_to_closed_range():
    assert ids([row("open", end=0), row("none", end=None), row("closed", start=1, end=40)]) == ["closed"]


def test_smallest_id_breaks_a_full_tie():
    assert ids([row("b"), row("a"), row("c")]) == ["a"]


def test_two_slides_in_one_section_give_one_entry():
    assert ids([row("a", slide="s1"), row("a", slide="s2")]) == ["a"]


def test_blank_deepest_section_gives_way_to_its_parent():
    rows = [row("child", level=2, summary="  ", objectives=[" ", ""]), row("parent", level=1)]
    assert ids(rows) == ["parent"]


def test_order_is_by_start_page_then_id():
    rows = [row("z", slide="s1", start=1), row("b", slide="s2", start=7), row("a", slide="s3", start=7)]
    assert ids(rows) == ["z", "a", "b"]


def test_none_level_counts_as_zero():
    assert ids([row("flat", level=None), row("deep", level=1)]) == ["deep"]


def test_summary_and_objectives_are_cleaned_and_objectives_may_be_none():
    notes = section_notes([row("a", summary="  Hi  ", objectives=[" x ", "", None, "y"]),
                           row("b", slide="s2", summary="", objectives=["o"]),
                           row("c", slide="s3", summary="s", objectives=None)])
    assert notes == [
        {"id": "a", "title": "T-a", "summary": "Hi", "objectives": ["x", "y"]},
        {"id": "b", "title": "T-b", "summary": "", "objectives": ["o"]},
        {"id": "c", "title": "T-c", "summary": "s", "objectives": []},
    ]


def test_empty_rows_give_nothing():
    assert section_notes([]) == []


# 2. forward

class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        payload = {"markdown_content": "body", "selected_assets": [], "callouts": []}
        return type("P", (), {"rich_content": json.dumps(payload)})()


def context(title="Intro", rationale="Why", **kw):
    synth = ContentSynthesizer()
    synth.generate = Recorder()
    out = synth([{"id": "s1", "text": "t", "assets": []}], "do it",
                section_title=title, section_rationale=rationale, **kw)
    assert out["markdown"] == "body"
    return synth.generate.calls[0]["section_context"]


HEADER = "Source section notes (orientation only; facts still come only from the slide text):"
TODAY = "Section Title: Intro\nPurpose: Why"


def test_notes_follow_the_title_and_purpose_in_the_exact_format():
    notes = [{"title": "A", "summary": "About A", "objectives": ["one", "two"]}]
    assert context(section_notes=notes) == f"{TODAY}\n{HEADER}\n- A: About A\n  Objectives: one; two"


def test_summary_only_and_objectives_only_forms():
    notes = [{"title": "A", "summary": "About A", "objectives": []},
             {"title": "B", "summary": "", "objectives": ["x"]}]
    assert context(section_notes=notes) == f"{TODAY}\n{HEADER}\n- A: About A\n- B\n  Objectives: x"


def test_a_note_with_no_title_gets_a_label_not_none():
    notes = [{"title": None, "summary": "About", "objectives": []}]
    assert context(section_notes=notes) == f"{TODAY}\n{HEADER}\n- Untitled section: About"


def test_no_notes_leave_the_context_as_it_was():
    assert context() == TODAY
    assert context(section_notes=None) == TODAY
    assert context(section_notes=[]) == TODAY


def test_general_fallback_still_applies_without_notes():
    assert context(title="", rationale="", section_notes=[]) == "General content section"


# 3. synthesize_node

class FakeNeo4j:
    def __init__(self, notes_rows=(), notes_error=None):
        self.notes_rows = list(notes_rows)
        self.notes_error = notes_error
        self.results = []
        self.statuses = []
        self.notes_params = None

    def execute_query(self, query, params=None):
        if query == SECTION_NOTES_QUERY:
            self.notes_params = params
            if self.notes_error:
                raise self.notes_error
            return self.notes_rows
        if "content_markdown" in query:
            self.results.append(params)
            return []
        if "SET n.status = $status" in query:
            self.statuses.append(params["status"])
            return []
        if "DERIVED_FROM" in query:
            return [{"slide_ids": ["s1"], "rationale": "Why", "title": "Intro", "target_layout": "split"}]
        if "RETURN s.id as id" in query:
            return [{"id": "s1", "elements": None, "text": "slide text", "course_id": None}]
        raise AssertionError(f"unexpected query: {query}")


class StubSynth:
    def __init__(self):
        self.calls = []

    def __call__(self, slides, instruction, **kwargs):
        self.calls.append(kwargs)
        return {"markdown": "out", "assets": [], "callouts": []}


def service(neo4j):
    svc = SynthesisService.__new__(SynthesisService)
    svc.neo4j_client = neo4j
    svc.synthesizer = StubSynth()
    return svc


def test_notes_rows_reach_the_synthesizer():
    neo4j = FakeNeo4j([row("a", summary=" Hi ", objectives=["o"])])
    svc = service(neo4j)
    svc.synthesize_node("n1", "go")
    assert neo4j.notes_params == {"slide_ids": ["s1"]}
    assert svc.synthesizer.calls[0]["section_notes"] == [
        {"id": "a", "title": "T-a", "summary": "Hi", "objectives": ["o"]}]
    assert neo4j.results == [{"id": "n1", "content": "out"}]


def test_no_notes_rows_give_an_empty_list():
    svc = service(FakeNeo4j())
    svc.synthesize_node("n1", "go")
    assert svc.synthesizer.calls[0]["section_notes"] == []


def test_a_failing_notes_query_sets_error_and_writes_no_result():
    neo4j = FakeNeo4j(notes_error=RuntimeError("boom"))
    svc = service(neo4j)
    svc.synthesize_node("n1", "go")
    assert neo4j.statuses == ["error"]
    assert neo4j.results == []
    assert svc.synthesizer.calls == []
