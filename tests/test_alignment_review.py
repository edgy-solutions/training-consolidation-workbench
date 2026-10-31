"""Proposal review routes: list open proposals for a course, accept or reject one (contract section 4.7)."""
import pytest
from fastapi.testclient import TestClient

from src.auth.security import User, get_current_user
from src.workbench import alignment, main


class _Fake:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute_query(self, q, params=None):
        self.calls.append((q, params))
        return self.rows


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "store")
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    monkeypatch.setitem(main.app.dependency_overrides, main.require_platform_reader, lambda: None)
    monkeypatch.setitem(main.app.dependency_overrides, get_current_user, lambda: User(id="u1", email="u1@example.com"))
    return TestClient(main.app)


def _fake(monkeypatch, rows):
    fake = _Fake(rows)
    monkeypatch.setattr(main, "neo4j_client", fake)
    return fake


BODY = {"concept_id": "c1", "canonical_id": "cc1", "decision": "accept"}


def test_accept_writes_the_review_query(client, monkeypatch):
    fake = _fake(monkeypatch, [{"n": 1}])
    r = client.post("/alignment/proposals/review", json=BODY)
    assert r.status_code == 200
    q, params = fake.calls[0]
    assert q == alignment.REVIEW_QUERY
    assert (params["status"], params["uid"], params["concept_id"], params["canonical_id"]) == ("accepted", "u1", "c1", "cc1")
    assert params["at"].endswith("Z")
    assert r.json() == {"concept_id": "c1", "canonical_id": "cc1", "status": "accepted",
                        "reviewed_by": "u1", "reviewed_at": params["at"]}


def test_reject(client, monkeypatch):
    fake = _fake(monkeypatch, [{"n": 1}])
    r = client.post("/alignment/proposals/review", json={**BODY, "decision": "reject"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert fake.calls[0][1]["status"] == "rejected"


def test_no_open_proposal_is_404(client, monkeypatch):
    _fake(monkeypatch, [{"n": 0}])
    r = client.post("/alignment/proposals/review", json=BODY)
    assert r.status_code == 404 and r.json()["detail"] == "No open proposal for that pair"


def test_store_writes_off_is_403(client, monkeypatch):
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 403
    assert fake.calls == []


def test_bad_decision_is_422(client, monkeypatch):
    _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json={**BODY, "decision": "maybe"}).status_code == 422


def test_proposals_in_fixture_mode_are_empty(client, monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    fake = _fake(monkeypatch, [{"concept_id": "x"}])
    r = client.get("/alignment/proposals", params={"course_id": "k1"})
    assert r.status_code == 200 and r.json() == [] and fake.calls == []


def test_proposals_in_store_mode_pass_rows_through_in_order(client, monkeypatch):
    rows = [{"concept_id": "b", "shared": 2}, {"concept_id": "a", "shared": 1}]
    fake = _fake(monkeypatch, rows)
    r = client.get("/alignment/proposals", params={"course_id": "k1"})
    assert r.json() == rows
    assert fake.calls == [(alignment.PROPOSALS_QUERY, {"cid": "k1"})]
