"""SourceReader fixture implementation and the port-backed routes, against the vendored golden.

No stores needed.
"""
import json
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest

from src.publishing.image_ids import qualify
from src.workbench.fixture_reader import FixtureReader
from src.workbench.source_reader import get_source_reader, reset_source_reader_cache

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "training"
GOLDEN = json.loads((FIXTURE_DIR / "golden.json").read_text(encoding="utf-8"))
NEO = GOLDEN["neo4j"]
COURSE_ID = GOLDEN["ingest_id"]
EDGES = NEO["nondeterministic"]["edges"]
SLIDES = NEO["slides"]["nodes"]
SLIDE4 = next(s for s in SLIDES if s["number"] == 4)
IMG_NAME = next(k for k in GOLDEN["minio"]["keys_required"] if "/images/" in k).rsplit("/", 1)[-1]


@pytest.fixture
def reader():
    return FixtureReader(FIXTURE_DIR)


def q(s):
    return quote(s, safe="")


def test_courses(reader):
    cs = reader.list_courses(None)
    assert [c["id"] for c in cs] == [COURSE_ID]
    assert cs[0]["title"] == NEO["course"]["props"]["title"]
    assert reader.list_courses("MECH")[0]["id"] == COURSE_ID
    assert reader.list_courses("software") == []


def test_course_slides_numbers(reader):
    assert [s["number"] for s in reader.course_slides(COURSE_ID)] == [s["number"] for s in SLIDES]


def test_sections_parentage_and_covers(reader):
    secs = {s["id"]: s for s in reader.course_sections(COURSE_ID)}
    for e in EDGES["HAS_SECTION"]:
        expected = None if e["from"] == COURSE_ID else e["from"]
        assert secs[e["to"]]["parent_id"] == expected
    for sid, s in secs.items():
        golden = sorted((e for e in EDGES["COVERS"] if e["from"] == sid), key=lambda e: -e["score"])
        assert s["covers"] == [{"concept": e["to"], "score": e["score"]} for e in golden]


def test_slide_teaches(reader):
    for s in SLIDES:
        got = reader.slide(s["id"])["teaches"]
        want = [{"concept": e["to"], "salience": e["salience"]} for e in EDGES["TEACHES"] if e["from"] == s["id"]]
        assert got == want
    assert reader.slide("nope") is None


def test_slides_teaching_shared_concept(reader):
    rows = reader.slides_teaching(["Hydraulic pressure"])
    assert {r["slide_id"] for r in rows} == {SLIDES[1]["id"], SLIDE4["id"]}


def test_embedded_images(reader):
    imgs = reader.embedded_images(COURSE_ID)
    assert [i["name"] for i in imgs] == [IMG_NAME]
    assert imgs[0]["page_number"] == 4
    assert reader.resolve_ref(imgs[0]["ref"]) == f"/source/fixture-asset/{IMG_NAME}"
    assert reader.resolve_ref("minio://x/y") is None


# --- routes ---

@pytest.fixture
def client(monkeypatch, tmp_path):
    # The hydraulics deck alone: FIXTURE_DIR also carries tr's case-deck subfolders.
    for f in FIXTURE_DIR.iterdir():
        if f.is_file():
            shutil.copy(f, tmp_path / f.name)
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("SOURCE_FIXTURE_DIR", str(tmp_path))
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    yield TestClient(app)
    reset_source_reader_cache()


def test_get_source_reader_modes(monkeypatch):
    reset_source_reader_cache()
    monkeypatch.delenv("SOURCE_READER", raising=False)
    assert get_source_reader() is None
    monkeypatch.setenv("SOURCE_READER", "direct")
    assert get_source_reader() is None
    monkeypatch.setenv("SOURCE_READER", "bogus")
    with pytest.raises(ValueError):
        get_source_reader()
    monkeypatch.setenv("SOURCE_READER", "fixture")
    assert get_source_reader() is get_source_reader()
    reset_source_reader_cache()


def test_route_tree(client):
    r = client.get("/source/tree").json()
    assert r[0]["type"] == "BusinessUnit"
    c = r[0]["children"][0]
    assert c["id"] == COURSE_ID and c["type"] == "Course" and c["has_children"] is True
    assert client.get("/source/tree", params={"engineering_discipline": "zzz"}).json() == []


def test_route_filters(client):
    r = client.get("/source/filters").json()
    assert set(r) == {"origins", "domains", "intents", "types"}
    assert r["types"] == ["PPTX"]


def test_route_slides(client):
    r = client.get(f"/source/course/{q(COURSE_ID)}/slides").json()
    assert [s["number"] for s in r] == [1, 2, 3, 4]
    assert all(set(s) == {"id", "number", "text", "s3_url", "text_preview", "concepts", "elements",
                          "course_id", "course_title"}
               for s in r)
    # row-ready: identical to what /source/slide/{id} returns for the same slide
    for s in r:
        d = client.get(f"/source/slide/{q(s['id'])}").json()
        for k in ("id", "number", "s3_url", "text_preview", "concepts", "elements",
                  "course_id", "course_title"):
            assert s[k] == d[k], (s["id"], k)


def test_route_sections(client):
    r = client.get(f"/source/course/{q(COURSE_ID)}/sections").json()
    assert {s["id"] for s in r} == set(n["id"] for n in NEO["nondeterministic"]["sections"]["nodes"])
    s1 = next(s for s in r if s["id"].endswith("_s1"))
    assert s1["concepts"][0] == "Pascal's law" and set(s1) == {"id", "title", "level", "parent_id", "concepts", "slide_count", "concepts_inherited"}
    s0 = next(s for s in r if s["id"].endswith("_s0"))
    assert s0["concepts"]  # empty summary falls back to course concepts


def test_route_slide_shows_all_taught_concepts_like_legacy(client):
    r = client.get(f"/source/slide/{q(SLIDE4['id'])}").json()
    got = {c["name"]: c["salience"] for c in r["concepts"]}
    want = {e["to"]: e["salience"] for e in EDGES["TEACHES"] if e["from"] == SLIDE4["id"]}
    assert got == want  # includes Hydraulic pressure at 0.3: legacy slide detail has no cut
    assert r["id"] == SLIDE4["id"] and r["elements"]
    assert client.get(f"/source/slide/{q('missing')}").status_code == 404


def test_route_heatmap(client):
    r = client.get("/source/heatmap/pump").json()
    assert r[SLIDES[2]["id"]]["type"] == "slide"
    assert r[COURSE_ID] == {"score": pytest.approx(1.5), "type": "course"}


def test_route_search(client):
    r = client.post("/source/search", json={"query": "pascal"}).json()
    slides = r[0]["children"][0]["slides"]
    assert [s["id"] for s in slides] == [SLIDES[1]["id"]]
    assert client.post("/source/search", json={"query": "zzzz"}).json() == []


def test_route_embedded_and_asset(client):
    imgs = client.get(f"/source/embedded-images/{q(COURSE_ID)}").json()["images"]
    assert imgs[0]["filename"] == IMG_NAME and imgs[0]["page_number"] == 4
    r = client.get(imgs[0]["url"])
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert r.headers["content-type"] == "image/png"
    for_slides = client.post("/source/embedded-images-for-slides", json=[SLIDE4["id"]]).json()
    assert len(for_slides["images"]) == 1
    res = client.get("/source/resolve-image-url", params={"url": f"fixture://images/{qualify(COURSE_ID, IMG_NAME)}"}).json()
    assert res["presigned"] == imgs[0]["url"]


def test_asset_404_unless_fixture(monkeypatch):
    monkeypatch.delenv("SOURCE_READER", raising=False)
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    assert TestClient(app).get(f"/source/fixture-asset/{IMG_NAME}").status_code == 404
