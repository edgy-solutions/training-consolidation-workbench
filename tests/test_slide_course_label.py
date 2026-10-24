"""/source/slide/{id} names its slide: number, course_id and course_title agree with the tree and slide list."""
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


def test_slide_details_name_their_course(client):
    courses = [k for bu in client.get("/source/tree").json() for k in bu["children"]]
    assert len(courses) >= 2
    tested = 0
    for c in courses[:6]:
        rows = client.get(f"/source/course/{quote(c['id'], safe='')}/slides").json()
        if not rows:
            continue
        for r in (rows[0], rows[-1]):
            assert r["course_id"] == c["id"] and r["course_title"] == c["name"]
            d = client.get(f"/source/slide/{quote(r['id'], safe='')}").json()
            tested += 1
            assert (d["number"], d["course_id"], d["course_title"]) == (r["number"], c["id"], c["name"])
    assert tested >= 4


def test_tree_tells_same_titled_courses_apart(client):
    courses = [k for bu in client.get("/source/tree").json() for k in bu["children"]]
    assert all("filename" in c and "version" in c for c in courses)
    pumps = {c["filename"]: c for c in courses if c["name"] == "Pump Maintenance Basics"}
    assert {"dup-title-a.pptx", "dup-title-b.pptx"} <= set(pumps)
    a, b = pumps["dup-title-a.pptx"], pumps["dup-title-b.pptx"]
    assert a["id"] != b["id"] and (a["version"], b["version"]) == ("1.0", "2.0")


def test_nameless_course_falls_back_to_filename_stem():
    from src.workbench.source_routes import _course_name, _course_tree
    assert _course_name({"title": None, "filename": "decks/Pump Intro.pptx"}) == "Pump Intro"
    assert _course_name({"title": "  ", "filename": "a.b.pptx"}) == "a.b"
    assert _course_name({"title": "", "filename": None}) == "Untitled course"
    assert _course_name({"title": "Real"}) == "Real"
    tree = _course_tree([{"id": "1", "title": None, "filename": "x.pptx"},
                         {"id": "2", "title": " ", "filename": ""}])
    assert [c["name"] for c in tree[0]["children"]] == ["x", "Untitled course"]
