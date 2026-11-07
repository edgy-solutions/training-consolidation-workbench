"""The render gate: unfinished sections, build problems, concept overlaps and the recorded reason."""
import json

import pytest
from pptx import Presentation

from src.publishing import render_jobs
from src.publishing.course import DeckExportError, GraphLookup, ReaderLookup
from src.publishing.render import RENDER_OVERRIDE_QUERY, render_project, render_readiness
from tests.deck_fixtures import reader
from tests.test_render_local import FakeNeo4j, harness  # noqa: F401  (harness is a fixture)

SOURCE = "sha256:895392accf240f84d20c095c97384eee337541266ac21b31f9e09d1781597ebc_p2"
SHARED = "Pascal's law"


class Neo(FakeNeo4j):
    def __init__(self):
        super().__init__()
        self.writes = []

    def execute_query(self, query, params=None):
        if query.strip() == RENDER_OVERRIDE_QUERY.strip():
            self.writes.append(params)
            return []
        return super().execute_query(query, params)


def with_overlap(fake):
    """The reservoir leaf now also names a concept of the Pascal leaf."""
    fake.nodes = [{**n, "key_concepts": ["Hydraulic reservoir", SHARED]} if n["id"] == "n-reservoir" else n
                  for n in fake.nodes]
    return fake


def with_problem(fake):
    fake.nodes = [{**n, "source_refs": ["gone"]} if n["id"] == "n-reservoir" else n for n in fake.nodes]
    return fake


def eight(finished):
    return [{"id": f"l{i}", "parent_id": "proj-hydraulics", "title": f"Leaf {i}", "order": i,
             "content_markdown": "text" if i < finished else "", "key_concepts": [f"c{i}"],
             "source_refs": [SOURCE] if i < finished else []} for i in range(8)]


OVERRIDE = {"reason": "the safety recap is on purpose", "by": "u1", "at": "2026-11-02T10:00:00Z"}


def render(fake, out, **kw):
    return render_project("proj-hydraulics", "pptx", None, out, neo4j_client=fake, minio_client=None,
                          reader=reader(), **kw)


# ---- readiness

def test_readiness_is_none_for_the_golden_course():
    assert render_readiness("proj-hydraulics", neo4j_client=Neo(), reader=reader()) is None


def test_readiness_unfinished_first_with_real_numbers():
    fake = Neo()
    fake.nodes = eight(1)
    r = render_readiness("proj-hydraulics", neo4j_client=fake, reader=reader())
    assert r["kind"] == "unfinished" and r["message"] == "7 of 8 sections unfinished"
    assert (r["unfinished"], r["total"]) == (7, 8) and r["sections"][0] == {"id": "l1", "title": "Leaf 1"}


def test_readiness_problems_then_overlaps():
    r = render_readiness("proj-hydraulics", neo4j_client=with_problem(Neo()), reader=reader())
    assert r["kind"] == "problems" and r["message"] == "The deck cannot be built" and r["problems"]
    r = render_readiness("proj-hydraulics", neo4j_client=with_overlap(Neo()), reader=reader())
    assert r["kind"] == "concept_overlap" and r["message"] == "1 concept is taught in more than one section"
    assert r["overlaps"] == [{"concept": SHARED, "sections": [{"id": "n-pascal", "title": "Pascal's Law"},
                                                              {"id": "n-reservoir", "title": "Reservoir Schematic"}]}]


# ---- render_project

def test_overlap_without_an_override_raises_and_writes_nothing(tmp_path):
    fake = with_overlap(Neo())
    out = tmp_path / "d.pptx"
    with pytest.raises(DeckExportError) as e:
        render(fake, out)
    assert e.value.problems == [
        f"concept '{SHARED}' is on 2 sections: 'Pascal's Law', 'Reservoir Schematic'; rendering needs a reason"]
    assert not out.exists() and fake.writes == []


def test_overlap_with_an_override_exports_and_records_it(tmp_path):
    fake = with_overlap(Neo())
    out = tmp_path / "d.pptx"
    render(fake, out, override=OVERRIDE)
    assert len(fake.writes) == 1 and fake.writes[0]["id"] == "proj-hydraulics"
    entry = json.loads(fake.writes[0]["entry"])
    comments = Presentation(str(out)).core_properties.comments
    assert entry["slides_sha256"]
    assert comments == f"deck_export/1 slides_sha256={entry['slides_sha256']} render_anyway=yes"
    assert {k: entry[k] for k in ("reason", "by", "at", "filename", "schema")} == {
        **OVERRIDE, "filename": "d.pptx", "schema": "deck_export/1"}
    assert entry["overlaps"][0]["concept"] == SHARED


def test_no_overlap_ignores_an_override(tmp_path):
    fake = Neo()
    out = tmp_path / "d.pptx"
    render(fake, out, override=OVERRIDE)
    assert fake.writes == [] and "render_anyway" not in Presentation(str(out)).core_properties.comments


def test_typ_is_not_gated(tmp_path):
    fake = with_overlap(Neo())
    out = tmp_path / "d.typ"
    render_project("proj-hydraulics", "typ", None, out, neo4j_client=fake, minio_client=None, reader=reader())
    assert out.exists() and fake.writes == []


# ---- the route

class Spy:
    """Records create_job and run_job calls; run_job is not executed."""

    def __init__(self, monkeypatch, main):
        self.jobs, self.runs = [], []
        real_create = main.create_job
        monkeypatch.setattr(main, "create_job", lambda *a, **k: (self.jobs.append(a), real_create(*a, **k))[1])
        monkeypatch.setattr(main, "run_job", lambda run_id, tpl, **k: self.runs.append(k))


def post(client, **extra):
    return client.post("/render/trigger", json={"project_id": "proj-hydraulics", **extra})


def test_route_unfinished_stops_before_any_concept_check(harness, monkeypatch):
    client, fake, main = harness
    fake.nodes = eight(1)
    spy = Spy(monkeypatch, main)
    looked = []
    for cls in (ReaderLookup, GraphLookup):
        monkeypatch.setattr(cls, "deck_slides", lambda self, d: looked.append(d))
    for extra in ({}, {"render_anyway_reason": "because"}):
        r = post(client, **extra)
        assert r.status_code == 409
        assert r.json()["detail"]["kind"] == "unfinished"
        assert r.json()["detail"]["message"] == "7 of 8 sections unfinished"
    assert spy.jobs == [] and looked == []


def test_route_a_reason_does_not_get_past_problems(harness, monkeypatch):
    client, fake, main = harness
    with_problem(fake)
    spy = Spy(monkeypatch, main)
    r = post(client, render_anyway_reason="because")
    assert r.status_code == 409 and r.json()["detail"]["kind"] == "problems"
    assert spy.jobs == []


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_route_overlap_without_a_reason_is_409(harness, monkeypatch, reason):
    client, fake, main = harness
    with_overlap(fake)
    spy = Spy(monkeypatch, main)
    r = post(client, render_anyway_reason=reason)
    assert r.status_code == 409 and r.json()["detail"]["kind"] == "concept_overlap"
    assert spy.jobs == []


def test_route_overlap_with_a_reason_creates_the_job(harness, monkeypatch):
    client, fake, main = harness
    with_overlap(fake)
    spy = Spy(monkeypatch, main)
    r = post(client, render_anyway_reason="  on purpose  ")
    assert r.status_code == 200 and len(spy.jobs) == 1
    override = spy.runs[0]["override"]
    assert override["reason"] == "on purpose" and override["by"] == "u1" and override["at"].endswith("Z")


def test_route_no_overlap_passes_no_override(harness, monkeypatch):
    client, fake, main = harness
    spy = Spy(monkeypatch, main)
    r = post(client, render_anyway_reason="unneeded")
    assert r.status_code == 200 and spy.runs[0]["override"] is None


def test_route_reason_over_500_is_422(harness):
    client, _, _ = harness
    assert post(client, render_anyway_reason="x" * 501).status_code == 422


def test_route_is_403_while_writes_are_off(harness, monkeypatch):
    client, _, _ = harness
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    assert post(client).status_code == 403


def test_a_failing_record_fails_the_job_and_removes_the_file(harness, monkeypatch):
    client, fake, main = harness
    with_overlap(fake)
    real = fake.execute_query

    def execute(query, params=None):
        if "render_overrides" in query:
            raise RuntimeError("graph is down")
        return real(query, params)

    monkeypatch.setattr(main.neo4j_client, "execute_query", execute, raising=False)
    run_id = post(client, render_anyway_reason="on purpose").json()["run_id"]
    job = render_jobs.read_job(run_id)
    assert job["status"] == "FAILURE" and "graph is down" in job["problems"][0]
    assert not list((render_jobs.export_dir() / run_id).glob("*.pptx"))
