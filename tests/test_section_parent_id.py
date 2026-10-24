"""The sections route names each section's parent (HAS_SECTION), so the UI need not trust order."""
from urllib.parse import quote

import pytest

from src.workbench.source_reader import reset_source_reader_cache
from tests.test_source_reader_fixture import FIXTURE_DIR


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("SOURCE_FIXTURE_DIR", str(FIXTURE_DIR))
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    try:
        yield TestClient(app)
    finally:
        reset_source_reader_cache()


def _sections(c, title):
    tree = c.get("/source/tree").json()
    cid = next(k["id"] for bu in tree for k in bu["children"] if k["name"] == title)
    r = c.get(f"/source/course/{quote(cid, safe='')}/sections")
    assert r.status_code == 200
    return cid, r.json()


def test_nested_sections_carry_parent_id(client):
    cid, secs = _sections(client, "Avionics Fundamentals")
    ids = {s["id"] for s in secs}
    assert all("parent_id" in s for s in secs)
    roots = [s for s in secs if s["parent_id"] is None]
    assert roots and len(roots) < len(secs)
    for s in secs:
        if s["parent_id"] is not None:
            assert s["parent_id"] in ids
            assert s["id"].startswith(s["parent_id"] + "_s")  # the id scheme agrees with the edge
