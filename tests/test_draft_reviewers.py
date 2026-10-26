"""Drafts are read only by their owner or an authz_id on the draft's reviewer list, and written only
by the owner (architect, b4). No cross-user reads.

The fake graph answers each access query the way its Cypher reads: one project n1, owned by u1."""
import pytest
from fastapi.testclient import TestClient

READ_MARK = "$uid IN coalesce(p.reviewer_ids, [])"
OWN_MARK = "-[:OWNS]->(p:Project)-[:HAS_CHILD*0..]->(n)"
SET_MARK = "SET p.reviewer_ids = $ids"

WRITES = [
    ("POST", "/draft/node/add?parent_id=n1&title=T", None),
    ("PUT", "/draft/node/map?node_id=n1", ["s1"]),
    ("PUT", "/draft/node/content?node_id=n1", {"content": "x"}),
    ("PUT", "/draft/node/layout?node_id=n1", {"layout": "x"}),
    ("PUT", "/draft/node/title?node_id=n1", {"title": "x"}),
    ("POST", "/synthesis/trigger", {"target_node_id": "n1", "tone_instruction": "plain"}),
    ("POST", "/draft/node/accept?node_id=n1", None),
    ("DELETE", "/draft/node/reject?node_id=n1", None),
    ("POST", "/render/trigger", {"project_id": "n1"}),
    ("PUT", "/draft/reviewers?project_id=n1", {"reviewer_ids": ["u3"]}),
]
READS = ["/draft/structure/n1", "/synthesis/preview/n1", "/draft/reviewers/n1"]


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    from src.auth.security import User, get_current_user
    from src.workbench import main

    g = {"owner": "u1", "reviewers": [], "as": "u1", "passed": []}

    def execute_query(query, params=None):
        params = params or {}
        if READ_MARK in query:
            ok = params["uid"] == g["owner"] or params["uid"] in g["reviewers"]
            g["passed"].append(("read", ok))
            return [{"n.id": "n1"}] if ok else []
        if OWN_MARK in query:
            ok = params["uid"] == g["owner"]
            g["passed"].append(("own", ok))
            return [{"n.id": "n1"}] if ok else []
        if SET_MARK in query:
            if params["uid"] != g["owner"] or params["id"] != "n1":
                return []
            g["reviewers"] = params["ids"]
            return [{"reviewer_ids": params["ids"]}]
        if "RETURN n.content_markdown as content" in query:
            return [{"content": "x", "status": "draft"}]
        if "RETURN coalesce(p.reviewer_ids, [])" in query:
            return [{"reviewer_ids": g["reviewers"]}]
        return []

    monkeypatch.setattr(main.neo4j_client, "execute_query", execute_query, raising=False)
    monkeypatch.setattr(main, "slide_decks", lambda ids: {i: "c1" for i in ids})
    main.app.dependency_overrides[get_current_user] = lambda: User(id=g["as"])
    yield TestClient(main.app, raise_server_exceptions=False), g
    main.app.dependency_overrides.pop(get_current_user, None)


def test_owner_sets_the_list_without_itself_and_deduplicated(graph):
    client, g = graph
    r = client.put("/draft/reviewers?project_id=n1", json={"reviewer_ids": ["u2", " u2", "u1", "u4"]})
    assert r.status_code == 200
    assert r.json() == {"project_id": "n1", "reviewer_ids": ["u2", "u4"]}
    assert g["reviewers"] == ["u2", "u4"]


@pytest.mark.parametrize("body", [{}, {"reviewer_ids": "u2"}, {"reviewer_ids": ["u2", ""]}, {"reviewer_ids": [7]},
                                  {"reviewer_ids": [f"u{i}" for i in range(2, 53)]}])
def test_a_bad_list_is_400_and_nothing_is_written(graph, body):
    client, g = graph
    assert client.put("/draft/reviewers?project_id=n1", json=body).status_code == 400
    assert g["reviewers"] == []


@pytest.mark.parametrize("url", READS)
def test_a_reviewer_reads(graph, url):
    client, g = graph
    g["reviewers"], g["as"] = ["u2"], "u2"
    assert client.get(url).status_code == 200
    assert g["passed"] == [("read", True)]


@pytest.mark.parametrize("url", READS)
def test_a_stranger_reads_nothing(graph, url):
    client, g = graph
    g["reviewers"], g["as"] = ["u2"], "u3"
    r = client.get(url)
    assert r.status_code == 404 and r.json()["detail"] == "Draft not found"


@pytest.mark.parametrize("method,url,body", WRITES)
def test_a_reviewer_writes_nothing(graph, method, url, body):
    client, g = graph
    g["reviewers"], g["as"] = ["u2"], "u2"
    r = client.request(method, url, json=body)
    assert r.status_code == 404 and r.json()["detail"] == "Draft not found"
    assert g["reviewers"] == ["u2"]
    assert ("read", True) not in g["passed"]


def test_the_list_shows_owned_and_reviewed_drafts_with_the_role(graph, monkeypatch):
    client, g = graph
    from src.workbench import main
    seen = []

    def execute_query(query, params=None):
        seen.append((query, params))
        return [{"id": "n1", "title": "T", "status": "empty", "created_at": None, "role": "reviewer"}]

    monkeypatch.setattr(main.neo4j_client, "execute_query", execute_query, raising=False)
    g["as"] = "u2"
    r = client.get("/draft/list")
    assert r.status_code == 200 and r.json()[0]["role"] == "reviewer"
    query, params = seen[0]
    assert "OPTIONAL MATCH (u:User {id: $user_id})-[o:OWNS]->(p)" in query
    assert "$user_id IN coalesce(p.reviewer_ids, [])" in query
    assert params == {"user_id": "u2"}
