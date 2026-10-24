"""Pre-step-d goldens carry salience null on every TEACHES edge; the routes must still answer."""
import json
import shutil
from urllib.parse import quote

import pytest

from src.workbench.source_reader import reset_source_reader_cache
from src.workbench.source_routes import _max_salience

from tests.test_fixture_multi_deck import SRC


def test_max_salience_treats_none_as_unknown():
    assert _max_salience(None, None) is None
    assert _max_salience(None, 0.4) == 0.4
    assert _max_salience(0.4, None) == 0.4
    assert _max_salience(0.4, 0.9) == 0.9


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "root"
    shutil.copytree(SRC, root)
    g = json.loads((root / "golden.json").read_text(encoding="utf-8"))
    teaches = g["neo4j"]["nondeterministic"]["edges"]["TEACHES"]
    for e in teaches:
        e["salience"] = None
    teaches.append(dict(teaches[0]))  # same slide, same concept twice: exercises the max
    (root / "golden.json").write_text(json.dumps(g), encoding="utf-8")
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("SOURCE_FIXTURE_DIR", str(root))
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    try:
        yield TestClient(app), teaches[0]
    finally:
        reset_source_reader_cache()


def test_slide_detail_with_null_salience(client):
    c, edge = client
    r = c.get(f"/source/slide/{quote(edge['from'], safe='')}")
    assert r.status_code == 200
    concepts = r.json()["concepts"]
    assert concepts and all(x["salience"] is None for x in concepts)


def test_search_with_null_salience(client):
    c, edge = client
    r = c.post("/source/search", json={"query": edge["to"], "filters": {}})
    assert r.status_code == 200
    slides = [s for bu in r.json() for course in bu["children"] for s in course["slides"]]
    assert any(s["id"] == edge["from"] for s in slides)
