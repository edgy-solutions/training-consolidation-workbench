"""Fixture mode with several decks at once (root deck + subdirectory decks)."""
import json
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest

from src.workbench.fixture_reader import (FixtureReader, MultiFixtureReader, is_fixture_reader,
                                          load_fixture_reader)
from src.workbench.source_reader import reset_source_reader_cache

SRC = Path(__file__).resolve().parent / "fixtures" / "training"
GOLDEN_TEXT = (SRC / "golden.json").read_text(encoding="utf-8")
GOLDEN = json.loads(GOLDEN_TEXT)
ID1 = GOLDEN["ingest_id"]
HEX1 = ID1.split(":", 1)[1]
HEX2 = "ab" * 32
ID2 = "sha256:" + HEX2
IMG = "slide_4_img_0.png"


def q(s):
    return quote(s, safe="")


def _copy_root_deck(dst: Path) -> Path:
    """The hydraulics deck alone: SRC also carries tr's case-deck subfolders."""
    dst.mkdir()
    for f in SRC.iterdir():
        if f.is_file():
            shutil.copy(f, dst / f.name)
    return dst


def _make_second(root: Path, golden_text=None, name="second"):
    d = root / name
    d.mkdir()
    shutil.copy(SRC / GOLDEN["fixture"]["deck"], d / GOLDEN["fixture"]["deck"])
    text = (golden_text or GOLDEN_TEXT).replace(HEX1, HEX2)
    g = json.loads(text)
    g["neo4j"]["course"]["props"]["title"] = "Second Course"
    (d / "golden.json").write_text(json.dumps(g), encoding="utf-8")
    return d


@pytest.fixture
def root(tmp_path):
    r = _copy_root_deck(tmp_path / "root")
    _make_second(r)
    return r


@pytest.fixture
def multi(root):
    return load_fixture_reader(root)


def test_loads_multi(multi):
    assert isinstance(multi, MultiFixtureReader) and is_fixture_reader(multi)
    assert len(multi.list_courses()) == 2
    assert {c["id"] for c in multi.list_courses()} == {ID1, ID2}


def test_single_deck_is_still_a_multi_reader(tmp_path):
    assert type(load_fixture_reader(_copy_root_deck(tmp_path / "one"))) is MultiFixtureReader


def test_vendored_case_decks_load_as_one_course_per_deck():
    # dup-same-bytes-{a,b} are the same deck, so they are one course.
    shas = {json.loads(g.read_text(encoding="utf-8"))["fixture"]["deck_sha256"] for g in SRC.glob("**/golden.json")}
    assert len(load_fixture_reader(SRC).list_courses()) == len(shas)


def test_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fixture_reader(tmp_path)


def test_routing(multi):
    for cid, hx in ((ID1, HEX1), (ID2, HEX2)):
        slides = multi.course_slides(cid)
        assert slides and all(s["id"].startswith(f"sha256:{hx}") for s in slides)
        s = multi.slide(f"sha256:{hx}_p2")
        assert s["course_id"] == cid
    assert multi.course_slides("nope") == []
    ids = [f"sha256:{HEX2}_p2", "missing", f"sha256:{HEX1}_p1"]
    assert [s["id"] for s in multi.slides(ids)] == [ids[0], ids[2]]


def test_images_distinct_and_resolve(multi):
    refs = []
    for cid in (ID1, ID2):
        img = next(i for i in multi.embedded_images(cid) if i["name"] == IMG)
        k = cid.split(":", 1)[1][:12]
        assert multi.resolve_ref(img["ref"]) == f"/source/fixture-asset/{k}--{IMG}"
        data, mime = multi.asset(f"{k}--{IMG}")
        assert data[:4] == b"\x89PNG" and mime == "image/png"
        refs.append(img["ref"])
    assert len(set(refs)) == 2
    assert multi.asset(IMG) is None


def test_search(multi):
    assert multi.search("pascal", None, 10) == [f"sha256:{HEX1}_p2", f"sha256:{HEX2}_p2"]
    assert multi.search("pascal", [ID2], 10) == [f"sha256:{HEX2}_p2"]
    assert len(multi.search("pascal", None, 1)) == 1


def _dup(root, deck_sha=None):
    d = root / "dup"
    d.mkdir()
    shutil.copy(SRC / GOLDEN["fixture"]["deck"], d / GOLDEN["fixture"]["deck"])
    g = json.loads(GOLDEN_TEXT)
    if deck_sha:
        g["fixture"]["deck_sha256"] = deck_sha
    (d / "golden.json").write_text(json.dumps(g), encoding="utf-8")


def test_identical_duplicates_are_one_course(root):
    _dup(root)
    r = load_fixture_reader(root)
    assert len(r.list_courses()) == 2


def test_same_id_different_content_raises(root):
    _dup(root, deck_sha="0" * 64)
    with pytest.raises(ValueError):
        load_fixture_reader(root)


def test_sparse_golden_loads(tmp_path):
    g = json.loads(GOLDEN_TEXT)
    nd = g["neo4j"]["nondeterministic"]
    nd.pop("sections", None)
    nd.pop("concepts", None)
    for k in ("HAS_SECTION", "section_slide", "COVERS", "TEACHES"):
        nd["edges"].pop(k, None)
    g.pop("minio", None)
    d = tmp_path / "d"
    d.mkdir()
    shutil.copy(SRC / g["fixture"]["deck"], d / g["fixture"]["deck"])
    (d / "golden.json").write_text(json.dumps(g), encoding="utf-8")
    r = load_fixture_reader(d)
    assert r.course_sections(ID1) == []
    assert r.concept_names() == []
    assert r.embedded_images(ID1) == []


def test_non_zip_deck_has_no_bytes(tmp_path):
    g = json.loads(GOLDEN_TEXT)
    g["fixture"]["deck"] = "deck.pdf"
    d = tmp_path / "d"
    d.mkdir()
    (d / "deck.pdf").write_bytes(b"%PDF-1.4")
    (d / "golden.json").write_text(json.dumps(g), encoding="utf-8")
    r = load_fixture_reader(d)
    imgs = r.embedded_images(ID1)
    assert imgs
    assert r.resolve_ref(imgs[0]["ref"]) is None and r.asset(imgs[0]["name"]) is None


def test_routes_multi(root, monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.setenv("SOURCE_FIXTURE_DIR", str(root))
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    try:
        c = TestClient(app)
        tree = c.get("/source/tree").json()
        courses = [ch for bu in tree for ch in bu["children"]]
        assert {x["id"] for x in courses} == {ID1, ID2}
        imgs = c.get(f"/source/embedded-images/{q(ID2)}").json()["images"]
        r = c.get(imgs[0]["url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content[:4] == b"\x89PNG"
    finally:
        reset_source_reader_cache()
