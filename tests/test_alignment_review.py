"""Proposal review routes: list open proposals for a course, accept or reject one (contract section 4.7)."""
import pytest
import requests
from fastapi.testclient import TestClient

from src.auth.security import User, get_current_user
from src.workbench import alignment, main


class _Fake:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute_query(self, q, params=None):
        self.calls.append((q, params))
        return self.rows


class _Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code, self._body, self._text = status, body, text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._body


class _Decider:
    """Stands in for requests.post in src.auth.security; records calls, answers granted by default."""

    def __init__(self):
        self.calls, self.result = [], _Resp(200, {"check": True})

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def decider(monkeypatch):
    d = _Decider()
    monkeypatch.setattr("src.auth.security.requests.post", d)
    return d


@pytest.fixture
def client(monkeypatch, decider):
    monkeypatch.setenv("TOPAZ_DIRECTORY_URL", "http://topaz.test:9393")
    monkeypatch.setenv("ALIGNMENT_REVIEW_SUBJECT", "alignment")
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
    assert "reviewed_at = datetime($at)" in q
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


def test_store_writes_off_is_403(client, monkeypatch, decider):
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 403
    assert fake.calls == [] and decider.calls == []


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


def test_decider_request_shape(client, monkeypatch, decider):
    _fake(monkeypatch, [{"n": 1}])
    client.post("/alignment/proposals/review", json=BODY)
    assert len(decider.calls) == 1
    url, kwargs = decider.calls[0]
    assert url == "http://topaz.test:9393/api/v3/directory/check"
    assert kwargs["json"] == {"object_type": "capability", "object_id": "can_review:alignment",
                              "relation": "can_invoke", "subject_type": "user", "subject_id": "u1"}


def test_subject_is_config(client, monkeypatch, decider):
    monkeypatch.setenv("ALIGNMENT_REVIEW_SUBJECT", "other")
    _fake(monkeypatch, [{"n": 1}])
    client.post("/alignment/proposals/review", json=BODY)
    assert decider.calls[0][1]["json"]["object_id"] == "can_review:other"


def test_granted_runs_the_write(client, monkeypatch, decider):
    decider.result = _Resp(200, {"check": True})
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 200
    assert len(fake.calls) == 1


@pytest.mark.parametrize("result", [_Resp(200, {"check": False}), _Resp(200, {}), _Resp(404, {})],
                         ids=["false", "absent", "404"])
def test_denied_is_403_and_no_write(client, monkeypatch, decider, result):
    decider.result = result
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 403
    assert fake.calls == []


@pytest.mark.parametrize("result", [
    requests.ConnectionError("down"), requests.Timeout("slow"),
    _Resp(500, {}), _Resp(503, {}), _Resp(400, {}), _Resp(302, {}),
    _Resp(200, text="<html>"), _Resp(200, []),
    _Resp(200, {"check": "true"}), _Resp(200, {"check": None}), _Resp(200, {"check": 1}),
], ids=["conn", "timeout", "500", "503", "400", "302", "nonjson", "list", "str", "null", "int"])
def test_unavailable_is_503_not_403_and_no_write(client, monkeypatch, decider, result):
    decider.result = result
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 503
    assert fake.calls == []


@pytest.mark.parametrize("var", ["TOPAZ_DIRECTORY_URL", "ALIGNMENT_REVIEW_SUBJECT"])
def test_unconfigured_is_403_and_decider_not_called(client, monkeypatch, decider, var):
    monkeypatch.delenv(var)
    fake = _fake(monkeypatch, [{"n": 1}])
    assert client.post("/alignment/proposals/review", json=BODY).status_code == 403
    assert decider.calls == [] and fake.calls == []


def test_listing_does_not_ask_the_decider(client, monkeypatch, decider):
    _fake(monkeypatch, [])
    assert client.get("/alignment/proposals", params={"course_id": "k1"}).status_code == 200
    assert decider.calls == []


def test_review_access_flag_off_asks_nothing(client, monkeypatch, decider):
    monkeypatch.delenv("WB_ALIGNMENT_REVIEW_UI", raising=False)
    r = client.get("/alignment/review-access")
    assert r.status_code == 200 and r.json() == {"enabled": False, "can_review": False}
    assert decider.calls == []


def test_review_access_granted(client, monkeypatch, decider):
    monkeypatch.setenv("WB_ALIGNMENT_REVIEW_UI", "on")
    assert client.get("/alignment/review-access").json() == {"enabled": True, "can_review": True}
    assert len(decider.calls) == 1


def test_review_access_denied(client, monkeypatch, decider):
    monkeypatch.setenv("WB_ALIGNMENT_REVIEW_UI", "on")
    decider.result = _Resp(200, {"check": False})
    assert client.get("/alignment/review-access").json() == {"enabled": True, "can_review": False}


def test_review_access_unavailable_is_503(client, monkeypatch, decider):
    monkeypatch.setenv("WB_ALIGNMENT_REVIEW_UI", "on")
    decider.result = requests.ConnectionError("down")
    assert client.get("/alignment/review-access").status_code == 503


def test_review_access_needs_a_token(monkeypatch, decider):
    monkeypatch.setenv("WB_ALIGNMENT_REVIEW_UI", "on")
    monkeypatch.setitem(main.app.dependency_overrides, main.require_platform_reader, lambda: None)
    monkeypatch.delitem(main.app.dependency_overrides, get_current_user, raising=False)
    assert TestClient(main.app).get("/alignment/review-access").status_code == 401
    assert decider.calls == []
