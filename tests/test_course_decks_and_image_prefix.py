"""The course records its decks; image ids always carry the deck prefix."""
import json

import pytest
from fastapi.testclient import TestClient

from src.publishing.course import (
    DeckExportError, FixtureImageResolver, MinioImageResolver, ReaderLookup, build_course,
)
from src.publishing.deck_export import export_deck
from src.publishing.image_ids import ImageRefError, deck_prefix, qualify, qualify_placeholders, split
from src.publishing.render import COURSE_NODES_QUERY, PROJECT_QUERY, render_project
from src.services.synthesis_service import asset_menu
from src.workbench.fixture_reader import REF_PREFIX, load_fixture_reader
from tests.deck_fixtures import COURSE_ID, FIXTURE_DIR, copy_standin, course_data, image_id, reader, resolver
from tests.test_fixture_multi_deck import _copy_root_deck

PREFIX = deck_prefix(COURSE_ID)
BARE = "slide_3_img_0"


# 1. resolvers

@pytest.mark.parametrize("given", [BARE, f"fixture://images/{BARE}.png"])
def test_fixture_resolver_refuses_a_bare_id(given):
    # the exporter hands the resolver the text inside {{ }} or the markdown target
    with pytest.raises(ImageRefError, match="carries no deck prefix") as e:
        FixtureImageResolver(reader(), [COURSE_ID])(given)
    assert BARE in str(e.value)


def test_fixture_resolver_refuses_an_unknown_prefix():
    with pytest.raises(ImageRefError, match="not a deck this course was built from"):
        FixtureImageResolver(reader(), [COURSE_ID])("ffffffffffff--slide_4_img_0.png")


def test_fixture_resolver_resolves_a_recorded_deck():
    r = FixtureImageResolver(reader(), [COURSE_ID])
    assert r("fixture://images/" + image_id("slide_4_img_0.png"))[:4] == b"\x89PNG"
    assert r(image_id("slide_4_img_0"))[:4] == b"\x89PNG"


class _Obj:
    def __init__(self, name):
        self.object_name = name
        self.is_dir = False


class _Body:
    def read(self):
        return b"img"

    def close(self):
        pass

    release_conn = close


class _Minio:
    def __init__(self):
        self.listed = []
        self.got = []

    def list_objects(self, bucket, prefix=None, recursive=False):
        self.listed.append(prefix)
        return [_Obj(f"{prefix}1.0/images/slide_4_img_0.png"), _Obj(f"{prefix}1.0/text.json")]

    def get_object(self, bucket, key):
        self.got.append(key)
        return _Body()


def test_minio_resolver_refusals_and_prefixed_lookup():
    m = _Minio()
    r = MinioImageResolver(m, "bkt", [COURSE_ID])
    with pytest.raises(ImageRefError, match="carries no deck prefix"):
        r(BARE)
    with pytest.raises(ImageRefError, match="not a deck this course was built from"):
        r("ffffffffffff--slide_4_img_0.png")
    assert m.got == []
    assert r(image_id("slide_4_img_0.png")) == b"img"
    assert m.listed == [f"{COURSE_ID}/generated/"]
    assert m.got == [f"{COURSE_ID}/generated/1.0/images/slide_4_img_0.png"]


# 2. the export names a bare id

def test_export_fails_on_a_bare_placeholder(tmp_path):
    data = course_data()
    leaf = next(n for n in data["nodes"] if n["id"] == "n-pumps")
    leaf["content_markdown"] += "\n\n{{" + BARE + "}}"
    course = build_course(data["project"], data["nodes"], ReaderLookup(reader()))
    with pytest.raises(DeckExportError) as e:
        export_deck(course, copy_standin(tmp_path / "t"), tmp_path / "o.pptx", resolver())
    assert any(BARE in p and "carries no deck prefix" in p for p in e.value.problems)
    assert not (tmp_path / "o.pptx").exists()


# 3. qualify_placeholders

def test_qualify_placeholders():
    a, b, c = f"{PREFIX}--x.png", f"{PREFIX}--y.png", "aaaaaaaaaaaa--y.png"
    out = qualify_placeholders("{{" + a + "}} {{x.png}} {{y.png}} {{zzz}}", [a, b, c])
    assert out == "{{" + a + "}} {{" + a + "}} {{y.png}} {{zzz}}"
    assert qualify_placeholders("t {{ x.png }}", [a]) == "t {{" + a + "}}"
    assert qualify_placeholders("no refs", [a]) == "no refs"


def test_split_and_qualify():
    assert split(qualify(COURSE_ID, "n.png")) == (PREFIX, "n.png")
    assert split("n.png") is None and split(f"{PREFIX}--") is None and split("ABCDEF123456--n") is None


# 4. asset_menu

def test_asset_menu():
    els = json.dumps([
        {"type": "Image", "text": "Pump diagram", "metadata": {"image_path": "a/b/slide_3_img_0.png"}},
        {"type": "Image", "text": "", "metadata": {"image_path": "slide_3_img_0.png"}},
        {"type": "Text", "text": "hello", "metadata": {}},
        {"type": "Image", "text": "", "metadata": {"image_path": "c/slide_3_img_1.png"}},
    ])
    menu = asset_menu([
        {"id": "s1", "elements": els, "course_id": COURSE_ID},
        {"id": "s2", "elements": els, "course_id": None},
    ])
    assert menu["s1"] == [
        {"asset_id": qualify(COURSE_ID, "slide_3_img_0.png"), "slide_id": "s1", "type": "image",
         "description": "Pump diagram"},
        {"asset_id": qualify(COURSE_ID, "slide_3_img_1.png"), "slide_id": "s1", "type": "image",
         "description": "slide_3_img_1.png"},
    ]
    assert menu.get("s2", []) == []


# 5. single-deck fixture refs carry the prefix

def test_single_deck_refs_carry_the_prefix(tmp_path):
    r = load_fixture_reader(_copy_root_deck(tmp_path / "one"))
    imgs = r.embedded_images(COURSE_ID)
    assert imgs
    for im in imgs:
        assert im["ref"] == f"{REF_PREFIX}{PREFIX}--{im['name']}"
        name = im["ref"][len(REF_PREFIX):]
        assert r.asset(name) is not None and r.resolve_ref(im["ref"])
        assert r.asset(im["name"]) is None


# 6. the export resolves through the recorded list

class GraphFreeNeo4j:
    def __init__(self, deck_ids, nodes=None):
        self.data = course_data()
        self.deck_ids = deck_ids
        self.nodes = nodes if nodes is not None else self.data["nodes"]

    def execute_query(self, query, params=None):
        assert "Slide" not in query, query
        if query == PROJECT_QUERY:
            return [{"title": self.data["project"]["title"], "deck_ids": self.deck_ids}]
        if query == COURSE_NODES_QUERY:
            return [dict(n) for n in self.nodes]
        raise AssertionError(query)


def _render(tmp_path, neo, rd=None):
    return render_project("proj-hydraulics", "pptx", None, tmp_path / "o.pptx",
                          neo4j_client=neo, minio_client=None, reader=rd or reader())


def test_export_without_any_slide_query(tmp_path):
    assert _render(tmp_path, GraphFreeNeo4j([COURSE_ID])).exists()


def test_slide_of_an_unrecorded_deck_fails(tmp_path):
    rd = load_fixture_reader(FIXTURE_DIR)
    other = next(c["id"] for c in rd.list_courses() if c["id"] != COURSE_ID)
    foreign = rd.course_slides(other)[0]["id"]
    nodes = course_data()["nodes"]
    next(n for n in nodes if n["id"] == "n-pumps")["source_refs"] = [foreign]
    with pytest.raises(DeckExportError) as e:
        _render(tmp_path, GraphFreeNeo4j([COURSE_ID], nodes), rd)
    assert f"leaf 'Hydraulic Pumps': source slide '{foreign}' is not in any deck this course was built from"         in e.value.problems


def test_no_recorded_decks_fails(tmp_path):
    with pytest.raises(DeckExportError) as e:
        _render(tmp_path, GraphFreeNeo4j([]))
    assert "the course records no source decks" in e.value.problems


def test_unknown_recorded_deck_fails(tmp_path):
    with pytest.raises(DeckExportError) as e:
        _render(tmp_path, GraphFreeNeo4j([COURSE_ID, "sha256:nope"]))
    assert e.value.problems == ["source deck 'sha256:nope' was not found"]


# 7 and 8. the draft routes record slides and decks

@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    monkeypatch.delenv("SOURCE_FIXTURE_DIR", raising=False)
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    from src.auth.security import User, get_current_user
    from src.workbench import main

    calls = []

    def execute_query(query, params=None):
        calls.append((query, params))
        if "-[:HAS_CHILD*0..]->(n)" in query:
            return [{"n.id": "n1"}]
        return []

    monkeypatch.setattr(main.neo4j_client, "execute_query", execute_query, raising=False)
    main.app.dependency_overrides[get_current_user] = lambda: User(id="u1", email="u1@example.com")
    yield TestClient(main.app, raise_server_exceptions=False), calls
    main.app.dependency_overrides.pop(get_current_user, None)


def _writes(calls):
    return [(q, p) for q, p in calls if "source_slide_ids" in q]


def test_map_records_the_slides_and_their_deck(harness):
    client, calls = harness
    ids = [COURSE_ID + "_p1", COURSE_ID + "_p2"]
    r = client.put("/draft/node/map", params={"node_id": "n1"}, json=ids)
    assert r.status_code == 200, r.text
    (q, p), = _writes(calls)
    assert "t.source_slide_ids = $slide_ids" in q and "p.source_deck_ids" in q
    assert p["slide_ids"] == ids and p["deck_ids"] == [COURSE_ID]


def test_map_with_an_unknown_slide_is_400_and_writes_nothing(harness):
    client, calls = harness
    r = client.put("/draft/node/map", params={"node_id": "n1"}, json=[COURSE_ID + "_p1", "ghost"])
    assert r.status_code == 400
    assert r.json()["detail"] == "unknown source slides: ghost"
    assert _writes(calls) == []
    assert len(calls) == 1  # the ownership check only


def test_accept_sets_the_source_slides_and_decks(harness):
    client, calls = harness
    client.post("/draft/node/accept", params={"node_id": "n1"})
    (q, p), = _writes(calls)
    assert "t.source_slide_ids = [x IN slides | x.id]" in q
    assert "(c:Course)-[:HAS_SLIDE]->(s)" in q and "p.source_deck_ids" in q
