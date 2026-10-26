"""Generate Outline runs as a background job with polling; the synthesis status reads the node."""
import pytest
from fastapi.testclient import TestClient

from src.services import outline_jobs


@pytest.fixture(autouse=True)
def export_root(tmp_path, monkeypatch):
    monkeypatch.setenv("WB_EXPORT_DIR", str(tmp_path))


class FakeService:
    fail = None
    closed = False

    def __init__(self, reader=None):
        pass

    def generate_skeleton(self, **kw):
        progress = kw.pop("progress")
        for step in ("sources", "llm", "slides", "save"):
            progress(step)
            FakeService.seen.append(outline_jobs.read_job(self.job_id, "u1")["step"])
        if FakeService.fail:
            raise ValueError(FakeService.fail)
        return {"project_id": "p1", "unassigned_count": 3, "sections": [
            {"title": "A"}, {"title": "B"}, {"title": "U", "is_unassigned": True}]}

    def close(self):
        FakeService.closed = True


@pytest.fixture
def fake_service(monkeypatch):
    import src.services.generator_service as gs
    FakeService.seen, FakeService.fail, FakeService.closed = [], None, False
    monkeypatch.setattr(gs, "GeneratorService", FakeService)
    return FakeService


def run(fake_service, owner="u1"):
    job = outline_jobs.create_job(owner)
    fake_service.job_id = job["job_id"]
    outline_jobs.run_job(job["job_id"], reader=None, selected_source_ids=["s"], title="T")
    return job["job_id"]


def test_success_records_steps_and_counts(fake_service):
    job_id = run(fake_service)
    assert fake_service.seen == ["sources", "llm", "slides", "save"]
    job = outline_jobs.read_job(job_id, "u1")
    assert job["status"] == "SUCCESS"
    assert job["result"] == {"project_id": "p1", "section_count": 2, "unassigned_count": 3}
    assert job["started"] and job["finished"] and fake_service.closed


def test_failure_records_the_error(fake_service):
    fake_service.fail = "no outlines"
    job = outline_jobs.read_job(run(fake_service), "u1")
    assert job["status"] == "FAILURE" and job["error"] == "no outlines"
    assert fake_service.closed


def test_boot_mismatch_is_lost(monkeypatch):
    job = outline_jobs.create_job("u1")
    outline_jobs.set_step(job["job_id"], "llm")
    monkeypatch.setattr(outline_jobs, "BOOT_ID", "other")
    got = outline_jobs.read_job(job["job_id"], "u1")
    assert got["status"] == "LOST" and "restarted" in got["error"]
    assert outline_jobs.read_job(job["job_id"], "u1")["status"] == "LOST"


def test_other_owner_and_malformed_id_are_none():
    job = outline_jobs.create_job("u1")
    assert outline_jobs.read_job(job["job_id"], "u2") is None
    assert outline_jobs.read_job("../x", "u1") is None
    assert outline_jobs.read_job("outline-" + "0" * 32, "u1") is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    from src.auth.security import User, get_current_user
    from src.workbench import main
    state = {"as": "u1", "ran": []}
    monkeypatch.setattr(outline_jobs, "run_job", lambda job_id, **kw: state["ran"].append((job_id, kw)))
    main.app.dependency_overrides[get_current_user] = lambda: User(id=state["as"])
    yield TestClient(main.app, raise_server_exceptions=False), state, main
    main.app.dependency_overrides.pop(get_current_user, None)


def test_post_returns_a_job_and_get_polls_it(client):
    c, state, _ = client
    r = c.post("/project/generate_skeleton", json={"title": "T", "selected_source_ids": ["s1"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "QUEUED" and [s["key"] for s in body["steps"]] == ["sources", "llm", "slides", "save"]
    assert state["ran"][0][0] == body["job_id"] and state["ran"][0][1]["user_id"] == "u1"
    got = c.get(f"/project/generate_skeleton/{body['job_id']}").json()
    assert got["status"] == "QUEUED" and "owner" not in got and "boot" not in got
    assert "elapsed" in got and got["steps"]
    state["as"] = "u2"
    assert c.get(f"/project/generate_skeleton/{body['job_id']}").status_code == 404


def test_get_malformed_id_is_404(client):
    assert client[0].get("/project/generate_skeleton/nope").status_code == 404


@pytest.mark.parametrize("node,expect", [("drafting", "RUNNING"), ("complete", "SUCCESS"),
                                         ("error", "FAILURE"), ("draft", "draft")])
def test_synthesis_status_reads_the_node(client, monkeypatch, node, expect):
    c, state, main = client

    def boom(*a, **k):
        raise AssertionError("dagster called")
    monkeypatch.setattr(main, "dagster_client", type("D", (), {"__getattr__": boom})())

    def execute_query(query, params=None):
        if "reviewer_ids" in query:
            return [{"n.id": "n1"}] if params["uid"] == "u1" else []
        return [{"status": node}]
    monkeypatch.setattr(main.neo4j_client, "execute_query", execute_query, raising=False)
    r = c.get("/synthesis/status/n1")
    assert r.json() == {"run_id": "n1", "status": expect, "node_status": node}
    state["as"] = "u2"
    assert c.get("/synthesis/status/n1").status_code == 404
