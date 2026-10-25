"""Routes that write to the shared Neo4j graph answer 403 unless WB_STORE_WRITES is on."""
import pytest
from fastapi.testclient import TestClient

GUARDED = [
    ("POST", "/draft/create", {"title": "t"}),
    ("POST", "/draft/node/add", {}),
    ("PUT", "/draft/node/map", {}),
    ("PUT", "/draft/node/content", {}),
    ("PUT", "/draft/node/layout", {}),
    ("PUT", "/draft/node/title", {}),
    ("POST", "/synthesis/trigger", {}),
    ("POST", "/curriculum/generate", {}),
    ("POST", "/project/generate_skeleton", {}),
    ("POST", "/draft/node/accept", {}),
    ("DELETE", "/draft/node/reject", {}),
]


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    from src.workbench import main

    calls = []
    monkeypatch.setattr(main.neo4j_client, "execute_query", lambda *a, **k: calls.append(a) or [], raising=False)
    return TestClient(main.app), calls


@pytest.mark.parametrize("method,path,body", GUARDED)
def test_held_without_flag(app_client, monkeypatch, method, path, body):
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    client, calls = app_client
    r = client.request(method, path, json=body)
    assert r.status_code == 403
    assert "WB_STORE_WRITES" in r.json()["detail"]
    assert calls == []


def test_flag_on_lets_the_route_run(app_client, monkeypatch):
    monkeypatch.setenv("WB_STORE_WRITES", " ON ")
    client, _ = app_client
    assert client.post("/draft/create", json={"title": "t"}).status_code != 403


def test_source_reads_work_while_writes_held(app_client, monkeypatch):
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    client, _ = app_client
    assert client.get("/source/tree").status_code == 200
