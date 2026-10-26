"""StoreReader against a fake store built from the vendored goldens (root deck + 20 case decks).

The fake Neo4j answers each query constant from the golden's `neo4j` section; an unknown query fails.
The reader's output must equal MultiFixtureReader's on the same goldens.
"""
import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

from src.publishing.image_ids import deck_prefix
from src.workbench import store_reader as sr
from src.workbench import asset_links
from src.workbench.fixture_reader import ASSET_URL, REF_PREFIX, load_fixture_reader
from src.workbench.source_reader import get_source_reader, reset_source_reader_cache
from src.workbench.store_reader import StoreReader

SRC = Path(__file__).resolve().parent / "fixtures" / "training"
BUCKET = "processing-artifacts"
PAGE = b"\x89PNG-page-"


def q(s):
    return quote(s, safe="")


def _goldens():
    """One golden per course id, root first then subfolders by name (as load_fixture_reader)."""
    paths = [SRC / "golden.json"] + sorted(SRC.glob("*/golden.json"), key=lambda p: p.parent.name)
    out = {}
    for p in paths:
        g = json.loads(p.read_text(encoding="utf-8"))
        out.setdefault(g["neo4j"]["course"]["props"]["id"], g)
    return out


GOLDENS = _goldens()
FIXTURE = load_fixture_reader(SRC)
COURSE_IDS = sorted(GOLDENS)
WRITE_WORDS = re.compile(r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP)\b", re.I)


def test_all_twenty_one_goldens_are_there():
    assert len(list(SRC.glob("**/golden.json"))) == 21
    assert len(GOLDENS) == len(FIXTURE.readers)


# ------------------------------------------------------------------------------------------ fakes

class FakeNeo4j:
    def __init__(self):
        self.calls = []
        self.handlers = {
            sr.COURSES_QUERY: self.courses,
            sr.SLIDE_FACETS_QUERY: self.slide_facets,
            sr.COURSE_SUBGRAPH_QUERY: self.subgraph,
            sr.COURSE_ID_BY_PREFIX_QUERY: self.by_prefix,
            sr.CONCEPT_NAMES_QUERY: self.concept_names,
            sr.SLIDES_TEACHING_QUERY: self.slides_teaching,
        }

    def execute_query(self, query, parameters=None, db=None):
        assert not WRITE_WORDS.search(query), "a write keyword in a read query"
        h = self.handlers.get(query)
        assert h is not None, f"unknown query: {query[:80]!r}"
        self.calls.append(query)
        return h(parameters or {})

    def courses(self, p):
        return [{"props": dict(GOLDENS[i]["neo4j"]["course"]["props"])} for i in COURSE_IDS]

    def slide_facets(self, p):
        slides = [s for g in GOLDENS.values() for s in g["neo4j"]["slides"]["nodes"]]
        return [{"pedagogical_intent": list({s["pedagogical_intent"] for s in slides if s.get("pedagogical_intent")}),
                 "asset_type": list({s["asset_type"] for s in slides if s.get("asset_type")})}]

    def subgraph(self, p):
        g = GOLDENS.get(p["course_id"])
        if not g:
            return []
        neo = g["neo4j"]
        nd = neo["nondeterministic"]
        e = nd["edges"]
        return [{
            "course": dict(neo["course"]["props"]),
            "slides": [dict(s) for s in neo["slides"]["nodes"]],
            "sections": [dict(s) for s in (nd.get("sections") or {}).get("nodes") or []],
            "has_section": [dict(x) for x in e.get("HAS_SECTION") or []],
            "section_slide": [dict(x) for x in e.get("section_slide") or []],
            "covers": [dict(x) for x in e.get("COVERS") or []],
            "teaches": [dict(x) for x in e.get("TEACHES") or []],
        }]

    def by_prefix(self, p):
        return [{"id": i} for i in COURSE_IDS if i.startswith(p["id_start"])]

    def concept_names(self, p):
        names = {c["name"] for g in GOLDENS.values()
                 for c in ((g["neo4j"]["nondeterministic"].get("concepts") or {}).get("nodes") or [])}
        return [{"name": n} for n in sorted(names)]

    def slides_teaching(self, p):
        rows = []
        for cid in COURSE_IDS:
            g = GOLDENS[cid]
            num = {s["id"]: s["number"] for s in g["neo4j"]["slides"]["nodes"]}
            for t in g["neo4j"]["nondeterministic"]["edges"].get("TEACHES") or []:
                if t["to"] in p["names"]:
                    rows.append((cid, num[t["from"]], t["to"], t["from"], t.get("salience")))
        return [{"course_id": c, "slide_id": s, "concept": k, "salience": sal}
                for c, _, k, s, sal in sorted(rows, key=lambda r: r[:3])]


class FakeS3Error(Exception):
    code = "NoSuchKey"


class _Obj:
    def __init__(self, name, is_dir=False):
        self.object_name, self.is_dir = name, is_dir


class _Body:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeMinio:
    """current.json per course with a version folder that cannot be guessed from the course id."""

    def __init__(self):
        self.objects = {}
        self.calls = []
        self.prefixes = set()
        for cid, g in GOLDENS.items():
            m = next(r for r in FIXTURE.readers if r.course_id == cid)
            hexid = cid.split(":", 1)[1]
            prefix = f"training/generated/{hexid}/pv-{hexid[::-1][:9]}/"
            self.prefixes.add(prefix)
            self.objects[m.course["current_key"]] = json.dumps(
                {"pipeline_version": "pv", "manifest_key": prefix + "manifest.json", "prefix": prefix,
                 "updated_at": "now"}).encode()
            for name in m._images.names():
                b = m._images.load(name)
                if b is not None:
                    self.objects[prefix + "images/" + name] = b
            for s in m._slides.values():
                self.objects[f"{prefix}pages/page_{s['number']}.png"] = PAGE + str(s["number"]).encode()

    def list_objects(self, bucket_name, prefix=None, recursive=False):
        self.calls.append(("list", bucket_name, prefix))
        assert not recursive
        seen = set()
        for k in sorted(self.objects):
            if k.startswith(prefix):
                rest = k[len(prefix):]
                if "/" in rest:
                    d = prefix + rest.split("/", 1)[0] + "/"
                    if d not in seen:
                        seen.add(d)
                        yield _Obj(d, True)
                else:
                    yield _Obj(k)

    def get_object(self, bucket_name, object_name):
        self.calls.append(("get", bucket_name, object_name))
        if object_name not in self.objects:
            raise FakeS3Error()
        return _Body(self.objects[object_name])


class FakeWeaviate:
    def __init__(self, hits=None):
        self.hits = hits or []
        self.calls = []
        self.client = self

    @property
    def query(self):
        return self

    def get(self, collection, props):
        self.calls.append({"collection": collection, "props": props})
        return self

    def with_bm25(self, query, properties=None):
        self.calls[-1].update(query=query, properties=properties)
        return self

    def with_where(self, where):
        self.calls[-1]["where"] = where
        return self

    def with_limit(self, n):
        self.calls[-1]["limit"] = n
        return self

    def do(self):
        return {"data": {"Get": {"DocumentChunk": self.hits}}}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def stores():
    return FakeNeo4j(), FakeMinio(), FakeWeaviate()


@pytest.fixture
def reader(stores):
    n, m, w = stores
    return StoreReader(n, m, w, BUCKET)


# ------------------------------------------------------------------- port methods == fixture reader

def test_list_courses_and_facets(reader):
    assert reader.list_courses() == FIXTURE.list_courses()
    for d in ("hydraulic", "ZZZ", "mech"):
        assert reader.list_courses(d) == FIXTURE.list_courses(d)
    assert reader.facets() == FIXTURE.facets()


@pytest.mark.parametrize("cid", COURSE_IDS)
def test_course_methods(reader, cid):
    assert reader.course_slides(cid) == FIXTURE.course_slides(cid)
    assert reader.course_sections(cid) == FIXTURE.course_sections(cid)
    ids = [s["id"] for s in FIXTURE.course_slides(cid)]
    for i in ids:
        assert reader.slide(i) == FIXTURE.slide(i)
    assert reader.slides(ids + ["nope"]) == FIXTURE.slides(ids)
    assert reader.slides(list(reversed(ids))) == FIXTURE.slides(list(reversed(ids)))


@pytest.mark.parametrize("cid", COURSE_IDS)
def test_images_and_assets(reader, cid):
    want = {i["name"]: i for i in FIXTURE.embedded_images(cid)
            if FIXTURE.asset(f"{deck_prefix(cid)}--{i['name']}")}
    got = {i["name"]: i for i in reader.embedded_images(cid)}
    assert got == want
    for name, im in got.items():
        asset = f"{deck_prefix(cid)}--{name}"
        assert unsigned(reader.resolve_ref(im["ref"])) == FIXTURE.resolve_ref(im["ref"]) == ASSET_URL + asset
        assert reader.asset(asset) == FIXTURE.asset(asset)


@pytest.mark.parametrize("cid", COURSE_IDS)
def test_pages(reader, cid):
    for s in FIXTURE.course_slides(cid):
        url = unsigned(reader.page_preview_url(s["id"]))
        assert url == f"{ASSET_URL}{deck_prefix(cid)}--page_{s['number']}.png"
        data, mime = reader.asset(url[len(ASSET_URL):])
        assert data == PAGE + str(s["number"]).encode() and mime == "image/png"


def test_asset_misses(reader):
    cid = COURSE_IDS[0]
    k = deck_prefix(cid)
    assert reader.asset(f"{k}--nothing.png") is None
    assert reader.asset(f"{k}--page_9999.png") is None
    assert reader.asset("ffffffffffff--slide_4_img_0.png") is None
    assert reader.asset("plain.png") is None
    assert reader.asset(f"{k}--../x.png") is None
    assert reader.resolve_ref(f"{REF_PREFIX}{k}--nothing.png") is None
    assert reader.resolve_ref("http://x/y.png") is None
    assert reader.page_preview_url("nope_p1") is None
    assert reader.slide("sha256:00_p1") is None
    assert reader.course_slides("nope") == [] and reader.course_sections("nope") == []
    assert reader.embedded_images("nope") == []


def test_concepts_and_teaching(reader):
    assert sorted(reader.concept_names()) == sorted(FIXTURE.concept_names())
    names = FIXTURE.concept_names()
    key = lambda r: (r["course_id"], r["slide_id"], r["concept"])
    assert sorted(reader.slides_teaching(names), key=key) == sorted(FIXTURE.slides_teaching(names), key=key)
    one = names[:1]
    assert sorted(reader.slides_teaching(one), key=key) == sorted(FIXTURE.slides_teaching(one), key=key)
    assert reader.slides_teaching([]) == []


def test_model_concepts_match_goldens(reader):
    for cid in COURSE_IDS:
        m = reader._model(cid)
        fx = next(r for r in FIXTURE.readers if r.course_id == cid)
        assert sorted(m._concepts) == sorted(fx._concepts)


# ------------------------------------------------------------------------------------------ search

def test_search_bm25(stores):
    n, m, w = stores
    w.hits = [{"chunk_id": "a_p1", "doc_id": "a"}, {"chunk_id": "a_p2", "doc_id": "a"},
              {"chunk_id": "a_p1", "doc_id": "a"}, {"chunk_id": "b_p3", "doc_id": "b"}]
    r = StoreReader(n, m, w, BUCKET)
    assert r.search("pressure", None, 2) == ["a_p1", "a_p2"]
    c = w.calls[-1]
    assert c["collection"] == "DocumentChunk" and c["limit"] == 2
    assert c["query"] == "pressure" and c["properties"] == ["text"] and "chunk_id" in c["props"]
    assert c["where"] == {"path": ["domain"], "operator": "Equal", "valueText": "TRAINING"}
    assert r.search("pressure", ["a", "b"], 10) == ["a_p1", "a_p2", "b_p3"]
    assert w.calls[-1]["where"] == {"operator": "And", "operands": [
        {"path": ["domain"], "operator": "Equal", "valueText": "TRAINING"},
        {"path": ["doc_id"], "operator": "ContainsAny", "valueText": ["a", "b"]}]}
    n_calls = len(w.calls)
    assert r.search("", None, 5) == [] and r.search("x", [], 5) == [] and r.search("x", None, 0) == []
    assert len(w.calls) == n_calls


# ------------------------------------------------------------------------- MinIO and cache rules

def test_minio_stays_under_training_and_goes_through_current_json(stores):
    n, m, w = stores
    r = StoreReader(n, m, w, BUCKET)
    for cid in COURSE_IDS:
        r.embedded_images(cid)
        for s in r.course_slides(cid):
            r.asset(f"{deck_prefix(cid)}--page_{s['number']}.png")
    assert m.calls
    currents = {c["props"]["current_key"] for c in n.courses({})}
    for kind, bucket, key in m.calls:
        assert bucket == BUCKET and key.startswith("training/")
        if key not in currents:
            assert any(key.startswith(p) for p in m.prefixes), key
    # the first call for a course is its current.json
    assert m.calls[0][0] == "get" and m.calls[0][2] in currents


def test_refuses_a_key_outside_training(stores):
    n, m, w = stores
    n.subgraph_orig = n.subgraph

    def bad(p):
        row = n.subgraph_orig(p)
        row[0]["course"]["current_key"] = "other/generated/x/current.json"
        return row
    n.handlers[sr.COURSE_SUBGRAPH_QUERY] = bad
    r = StoreReader(n, m, w, BUCKET)
    with pytest.raises(ValueError):
        r.embedded_images(COURSE_IDS[0])
    assert not m.calls


def test_model_cache_ttl(stores):
    n, m, w = stores
    clock = Clock()
    r = StoreReader(n, m, w, BUCKET, cache_seconds=300, clock=clock)
    cid = COURSE_IDS[0]

    def subgraph_calls():
        return sum(1 for c in n.calls if c is sr.COURSE_SUBGRAPH_QUERY)
    r.course_slides(cid)
    r.course_sections(cid)
    r.slide(r.course_slides(cid)[0]["id"])
    assert subgraph_calls() == 1
    clock.t = 299
    r.course_slides(cid)
    assert subgraph_calls() == 1
    clock.t = 301
    r.course_slides(cid)
    assert subgraph_calls() == 2


def test_every_query_constant_is_read_only_and_listed():
    assert set(sr.NEO4J_QUERIES) == {n for n in dir(sr) if n.endswith("_QUERY")}
    for name, text in sr.NEO4J_QUERIES.items():
        assert not WRITE_WORDS.search(text), name
        assert re.match(r"\s*(MATCH|OPTIONAL MATCH)\b", text), name


# ------------------------------------------------------------------------------------------ routes

class AlignNeo4j:
    """main.neo4j_client for the alignment reads: nothing is aligned."""

    def execute_query(self, query, parameters=None, db=None):
        assert "ALIGNS_TO" in query and "MERGE" not in query and "SET" not in query
        if "coalesce(cc.name" in query:
            return [{"name": n, "display": n} for n in parameters["names"]]
        return [{"syns": []}]


def _client(monkeypatch, env):
    monkeypatch.setenv("SOURCE_READER", env)
    if env == "fixture":
        monkeypatch.setenv("SOURCE_FIXTURE_DIR", str(SRC))
    reset_source_reader_cache()
    from fastapi.testclient import TestClient
    from src.workbench.main import app
    return TestClient(app)


@pytest.fixture
def clients(monkeypatch, stores):
    n, m, w = stores
    import src.workbench.main as main
    monkeypatch.setattr(sr, "build_store_reader", lambda: StoreReader(n, m, w, BUCKET))
    monkeypatch.setattr(main, "neo4j_client", AlignNeo4j())
    # store reads need a signed-in user; the sign-in is not under test here
    gate = getattr(main, "require_platform_reader", None)
    if gate is not None:
        main.app.dependency_overrides[gate] = lambda: None
    store = _client(monkeypatch, "store")
    assert isinstance(get_source_reader(), StoreReader)
    fixture = _client(monkeypatch, "fixture")
    # both readers are cached side by side
    monkeypatch.setenv("SOURCE_READER", "store")
    yield store, fixture, monkeypatch
    if gate is not None:
        main.app.dependency_overrides.pop(gate, None)
    reset_source_reader_cache()


def _both(clients, path, **kw):
    store, fixture, mp = clients
    mp.setenv("SOURCE_READER", "store")
    a = store.get(path, **kw)
    mp.setenv("SOURCE_READER", "fixture")
    b = fixture.get(path, **kw)
    mp.setenv("SOURCE_READER", "store")
    return a, b


def unsigned(url):
    """A store asset URL without its signature, which must verify (b4: <img> sends no bearer)."""
    path, sep, qs = url.partition("?")
    params = dict(p.split("=", 1) for p in qs.split("&")) if sep else {}
    assert asset_links.valid(path[len(ASSET_URL):], params.get("exp"), params.get("sig")), url
    return path


def signed(path):
    name = path[len("/source/fixture-asset/"):]
    return f"{path}?{asset_links.signed_query(name)}"


def _strip_s3(x):
    if isinstance(x, list):
        return [_strip_s3(i) for i in x]
    if isinstance(x, dict):
        return {k: _strip_s3(v) for k, v in x.items() if k != "s3_url"}
    return x


def test_source_tree_filters(clients):
    a, b = _both(clients, "/source/tree")
    assert a.status_code == 200 and a.json() == b.json() and a.json()
    a, b = _both(clients, "/source/filters")
    assert a.status_code == 200 and a.json() == b.json()


CID = next(i for i in COURSE_IDS if i == next(iter(GOLDENS)))


def test_course_routes(clients):
    for cid in COURSE_IDS:
        a, b = _both(clients, f"/source/course/{q(cid)}/slides")
        assert a.status_code == 200 and _strip_s3(a.json()) == _strip_s3(b.json())
        for s in a.json():
            assert unsigned(s["s3_url"]) == f"{ASSET_URL}{deck_prefix(cid)}--page_{s['number']}.png"
        a, b = _both(clients, f"/source/course/{q(cid)}/sections")
        assert a.status_code == 200 and a.json() == b.json()
        a, b = _both(clients, f"/source/embedded-images/{q(cid)}")
        # the fixture also lists golden names that have no bytes (url null); a store lists what exists
        have = sorted({i["filename"]: i for i in b.json()["images"] if i["url"]}.values(), key=lambda i: i["filename"])
        assert a.status_code == 200 and a.json()["course_id"] == cid
        got = [{**i, "url": unsigned(i["url"])} for i in a.json()["images"]]
        assert sorted(got, key=lambda i: i["filename"]) == have


def test_slide_route(clients):
    for cid in COURSE_IDS[:6]:
        for s in FIXTURE.course_slides(cid)[:3]:
            a, b = _both(clients, f"/source/slide/{q(s['id'])}")
            assert a.status_code == 200 and _strip_s3(a.json()) == _strip_s3(b.json())
            assert unsigned(a.json()["s3_url"]).endswith(f"--page_{s['number']}.png")
    a, _ = _both(clients, "/source/slide/nope_p1")
    assert a.status_code == 404


def test_asset_route(clients):
    cid = next(c for c in COURSE_IDS if FIXTURE.embedded_images(c))
    im = next(i for i in FIXTURE.embedded_images(cid) if FIXTURE.asset(f"{deck_prefix(cid)}--{i['name']}"))
    name = f"{deck_prefix(cid)}--{im['name']}"
    path = f"/source/fixture-asset/{name}"
    a, b = _both(clients, signed(path))
    assert a.status_code == 200 and a.content == b.content and a.headers["content-type"] == b.headers["content-type"]
    page = FIXTURE.course_slides(cid)[0]
    page_path = f"/source/fixture-asset/{deck_prefix(cid)}--page_{page['number']}.png"
    a, _ = _both(clients, signed(page_path))
    assert a.status_code == 200 and a.content == PAGE + str(page["number"]).encode()
    assert a.headers["content-type"] == "image/png"
    a, _ = _both(clients, signed(f"/source/fixture-asset/{deck_prefix(cid)}--missing.png"))
    assert a.status_code == 404


def test_live_assets_need_a_valid_signed_link(clients):
    cid = next(c for c in COURSE_IDS if FIXTURE.embedded_images(c))
    im = next(i for i in FIXTURE.embedded_images(cid) if FIXTURE.asset(f"{deck_prefix(cid)}--{i['name']}"))
    path = f"/source/fixture-asset/{deck_prefix(cid)}--{im['name']}"
    good = asset_links.signed_query(path.rsplit("/", 1)[1])
    exp = good.split("&")[0]
    other = asset_links.signed_query(f"{deck_prefix(cid)}--page_999.png").split("&")[1]
    stale = asset_links.signed_query(path.rsplit("/", 1)[1], now=0)
    for bad in ("", f"?{exp}", f"?{exp}&{other}", f"?{stale}", f"?{exp}&sig=" + "0" * 64):
        a, b = _both(clients, path + bad)
        assert a.status_code == 404, bad
        assert b.status_code == 200  # fixture assets stay open
    a, _ = _both(clients, f"{path}?{good}")
    assert a.status_code == 200 and a.headers["cache-control"] == "private, max-age=300"


def test_other_reader_routes(clients):
    for path in ("/source/graph/concept/Pascal's%20law", "/source/heatmap/pressure"):
        a, b = _both(clients, path)
        assert a.status_code == 200 and a.json() == b.json(), path


def test_slide_decks_helper(clients):
    from src.workbench.main import slide_decks
    cid = COURSE_IDS[0]
    ids = [s["id"] for s in FIXTURE.course_slides(cid)]
    assert slide_decks(ids + ["nope"]) == {i: cid for i in ids}


def test_search_route_uses_bm25(clients, stores):
    n, m, w = stores
    w.hits = [{"chunk_id": FIXTURE.course_slides(COURSE_IDS[0])[0]["id"], "doc_id": COURSE_IDS[0]}]
    store, _, _ = clients
    r = store.get("/search/concepts", params={"q": "pump"})
    assert r.status_code == 200 and r.json() == [w.hits[0]["chunk_id"]]
    assert w.calls[-1]["collection"] == "DocumentChunk" and w.calls[-1]["limit"] == 10
