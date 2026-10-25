"""Project and node routes answer only for drafts the signed-in user owns (404 otherwise)."""
import pytest
from fastapi.testclient import TestClient

OWNERSHIP_MARK = "-[:HAS_CHILD*0..]->(n)"

# (method, url, json body) -- one per scoped route
SCOPED = [
    ("GET", "/draft/structure/n1", None),
    ("GET", "/synthesis/preview/n1", None),
    ("POST", "/draft/node/add?parent_id=n1&title=T", None),
    ("PUT", "/draft/node/map?node_id=n1", ["s1"]),
    ("PUT", "/draft/node/content?node_id=n1", {"content": "x"}),
    ("PUT", "/draft/node/layout?node_id=n1", {"layout": "x"}),
    ("PUT", "/draft/node/title?node_id=n1", {"title": "x"}),
    ("POST", "/synthesis/trigger", {"target_node_id": "n1", "tone_instruction": "plain"}),
    ("POST", "/draft/node/accept?node_id=n1", None),
    ("DELETE", "/draft/node/reject?node_id=n1", None),
    ("POST", "/render/trigger", {"project_id": "n1"}),
]


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    from src.auth.security import get_current_user
    from src.workbench import main
    from src.auth.security import User

    state = {"owned": False, "calls": []}

    def execute_query(query, params=None):
        state["calls"].append((query, params))
        if OWNERSHIP_MARK in query:
            return [{"n.id": "n1"}] if state["owned"] else []
        return []

    monkeypatch.setattr(main.neo4j_client, "execute_query", execute_query, raising=False)
    main.app.dependency_overrides[get_current_user] = lambda: User(id="u1", email="u1@example.com")
    yield TestClient(main.app, raise_server_exceptions=False), state
    main.app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("method,url,body", SCOPED)
def test_not_owned_is_404_and_nothing_else_runs(harness, method, url, body):
    client, state = harness
    r = client.request(method, url, json=body)
    assert r.status_code == 404
    assert r.json()["detail"] == "Draft not found"
    assert len(state["calls"]) == 1
    query, params = state["calls"][0]
    assert OWNERSHIP_MARK in query
    assert params == {"uid": "u1", "id": "n1"}


@pytest.mark.parametrize("method,url,body", SCOPED)
def test_owned_goes_past_the_check(harness, method, url, body):
    client, state = harness
    state["owned"] = True
    client.request(method, url, json=body)
    assert OWNERSHIP_MARK in state["calls"][0][0]
    assert len(state["calls"]) > 1


def test_list_is_filtered_by_the_users_id(harness):
    client, state = harness
    assert client.get("/draft/list").status_code == 200
    query, params = state["calls"][0]
    assert "(u:User {id: $user_id})-[:OWNS]->(p:Project)" in query
    assert params == {"user_id": "u1"}
