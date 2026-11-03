"""The settings screen's backend: a template saved to DECK_TEMPLATE_STORE, its validation and its routes."""
import io
import json
import shutil

import pytest
import requests
import yaml
from fastapi.testclient import TestClient
from pptx import Presentation

from src.auth.security import User, get_current_user
from src.publishing import deck_template, template_config
from src.publishing.course import DeckExportError
from src.publishing.deck_export import export_deck, load_mapping, mapping_warnings
from src.workbench import main
from tests.deck_fixtures import STANDIN_DIR, golden_course, resolver

STORE = "s3://tpl/cfg"
URI = "s3://tpl/a/deck.pptx"
STANDIN_PPTX = (STANDIN_DIR / "standin.pptx").read_bytes()
STANDIN_ROLES = yaml.safe_load((STANDIN_DIR / "deck-template.yaml").read_text(encoding="utf-8"))["roles"]


class NoSuchKey(Exception):
    code = "NoSuchKey"


class FakeObj:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def close(self):
        pass

    def release_conn(self):
        pass


class FakeMinio:
    """put/get/remove over a dict, recording the order of puts."""

    def __init__(self, fail=None):
        self.objects, self.puts, self.gets, self.removed, self.fail = {}, [], [], [], fail

    def upload_bytes(self, bucket, key, data, content_type=None):
        if self.fail == "put":
            raise OSError("store is down")
        self.puts.append(key)
        self.objects[(bucket, key)] = data

    def get_object(self, bucket, key):
        self.gets.append((bucket, key))
        if self.fail == "get":
            raise OSError("store is down")
        if (bucket, key) not in self.objects:
            raise NoSuchKey(key)
        return FakeObj(self.objects[(bucket, key)])

    def remove_object(self, bucket, key):
        self.removed.append(key)
        self.objects.pop((bucket, key), None)


def variant(mutate):
    prs = Presentation(io.BytesIO(STANDIN_PPTX))
    mutate(prs)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def roles_with(**changes):
    roles = json.loads(json.dumps(STANDIN_ROLES))
    roles.update(changes)
    return roles


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(deck_template, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(deck_template, "_logged_standin", False)
    for name in ("DECK_TEMPLATE_URI", "DECK_TEMPLATE", "DECK_TEMPLATE_STORE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DECK_TEMPLATE_STORE", STORE)
    mapping = tmp_path / "mount" / "deck-template.yaml"
    mapping.parent.mkdir()
    shutil.copy(STANDIN_DIR / "deck-template.yaml", mapping)
    shutil.copy(STANDIN_DIR / "standin.pptx", mapping.parent / "standin.pptx")
    return monkeypatch, mapping


def save(minio, data=STANDIN_PPTX, roles=None, filename="mine.pptx"):
    return template_config.check_and_save(data, roles or STANDIN_ROLES, filename, "u1", minio)


# --- storage ---

def test_store_unset_reads_nothing_and_uses_the_standin(env):
    monkeypatch, _ = env
    monkeypatch.delenv("DECK_TEMPLATE_STORE")
    minio = FakeMinio(fail="get")
    assert deck_template.configured_mapping(minio) == deck_template.STANDIN_MAPPING
    assert deck_template.read_saved(minio) is None
    assert deck_template.template_label() == "standin"
    assert minio.gets == []


def test_saved_over_uri_over_standin(env, tmp_path):
    monkeypatch, mapping = env
    minio = FakeMinio()
    minio.objects[("tpl", "a/deck.pptx")] = STANDIN_PPTX
    assert deck_template.configured_mapping(minio) == deck_template.STANDIN_MAPPING
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    monkeypatch.setenv("DECK_TEMPLATE", str(mapping))
    cur = deck_template.current(minio)
    assert cur.source == "deployment" and cur.mapping_path == tmp_path / "cache" / "deck-template.yaml"
    save(minio)
    cur = deck_template.current(minio)
    assert cur.source == "saved" and cur.mapping_path.parent.name.startswith("saved-")


def test_label_with_a_saved_pointer(env, monkeypatch):
    minio = FakeMinio()
    monkeypatch.setattr(deck_template, "_default_minio", lambda: minio)
    assert deck_template.template_label() == "standin"
    save(minio)
    assert deck_template.template_label() == "configured"


def test_store_error_raises_and_does_not_fall_back(env, monkeypatch):
    with pytest.raises(DeckExportError) as e:
        deck_template.configured_mapping(FakeMinio(fail="get"))
    assert STORE in str(e.value)
    monkeypatch.setattr(deck_template, "_default_minio", lambda: FakeMinio(fail="get"))
    assert deck_template.template_label() == "configured"  # logged, never raised
    deck_template.warm()  # never raises


def test_save_writes_pptx_before_pointer(env):
    minio = FakeMinio()
    pointer = save(minio)
    assert len(minio.puts) == 2
    assert minio.puts[0].endswith(".pptx") and minio.puts[0].startswith("cfg/")
    assert minio.puts[1] == "cfg/active.yaml"
    assert "mine" not in minio.puts[0]  # never the uploaded name
    assert pointer["source"]["filename"] == "mine.pptx" and pointer["source"]["saved_by"] == "u1"
    assert pointer["template"] == f"s3://tpl/{minio.puts[0]}"
    assert deck_template.read_saved(minio)["roles"] == STANDIN_ROLES


def test_failed_validation_writes_nothing(env):
    minio = FakeMinio()
    bad = roles_with(summary={"layout": "no-such-layout", "placeholders": {"title": 0, "body": 1}})
    with pytest.raises(template_config.TemplateRejected):
        save(minio, roles=bad)
    assert minio.puts == [] and minio.objects == {}


def test_a_failed_put_names_the_store(env):
    with pytest.raises(DeckExportError) as e:
        save(FakeMinio(fail="put"))
    assert not isinstance(e.value, template_config.TemplateRejected) and STORE in str(e.value)


# --- validation ---

def test_missing_role_and_non_mappable_reported_together(env):
    def mutate(prs):
        names = {lo.name: lo for lo in prs.slide_layouts}
        for ph in names["summary"].placeholders:
            if ph.placeholder_format.idx == 1:
                ph._element.nvSpPr.nvPr.ph.set("type", "ftr")  # a footer placeholder

    data = variant(mutate)
    roles = roles_with()
    del roles["sources"]
    with pytest.raises(template_config.TemplateRejected) as e:
        save(FakeMinio(), data=data, roles=roles)
    text = "\n".join(e.value.problems)
    assert "role 'sources' is not mapped" in text
    assert "role 'summary': field 'body' is mapped to placeholder 1 (FOOTER)" in text


def test_the_trial_export_catches_what_static_validation_passes(env, monkeypatch):
    calls = []

    def fails(*a, **k):
        calls.append(a)
        raise template_config.DeckExportError(["slide 2 did not round-trip"])

    monkeypatch.setattr(template_config, "export_deck", fails)
    minio = FakeMinio()
    with pytest.raises(template_config.TemplateRejected) as e:
        save(minio)
    assert len(calls) == 1
    assert e.value.problems == ["trial export: slide 2 did not round-trip"]
    assert minio.puts == []


def test_an_object_placeholder_takes_the_figure(env, tmp_path):
    # Contract section 2.2 allows it, and real templates often have no picture placeholder at all.
    roles = roles_with(**{"concept-with-figure": {"layout": "concept-with-figure",
                                                  "placeholders": {"title": 0, "image": 1, "body": 2, "citation": 3}}})
    minio = FakeMinio()
    save(minio, roles=roles)
    assert len(minio.puts) == 2
    out = tmp_path / "out.pptx"
    export_deck(golden_course(), deck_template.configured_mapping(minio), out, resolver())
    figure = next(s for s in Presentation(str(out)).slides if s.slide_layout.name == "concept-with-figure")
    pics = [sh for sh in figure.placeholders if sh.placeholder_format.idx == 1]
    assert len(pics) == 1 and pics[0]._element.tag.endswith("}pic")


@pytest.mark.parametrize("roles", [{"title": "nope"}, {"title": {"layout": "title", "placeholders": 5}},
                                   {"title": {"layout": "title", "placeholders": {"title": [1]}}}])
def test_malformed_roles_are_refused_not_a_crash(env, roles):
    minio = FakeMinio()
    with pytest.raises(template_config.TemplateRejected):
        save(minio, roles=roles)
    assert minio.puts == []


def test_a_good_mapping_runs_the_trial_export(env, monkeypatch):
    calls = []
    real_export = template_config.export_deck
    monkeypatch.setattr(template_config, "export_deck", lambda *a, **k: calls.append(a) or real_export(*a, **k))
    save(FakeMinio())
    assert len(calls) == 1


def test_inspect_reports_the_real_size_and_flags(env):
    info = template_config.inspect_template(STANDIN_PPTX)
    assert (info["slide_width"], info["slide_height"]) == (9144000, 6858000)
    figure = next(lo for lo in info["layouts"] if lo["name"] == "concept-with-figure")
    by_idx = {p["idx"]: p for p in figure["placeholders"]}
    assert by_idx[3]["accepts_image"] and by_idx[3]["type"] == "PICTURE" and by_idx[0]["mappable"]
    assert all(lo["name_count"] == 1 for lo in info["layouts"])
    assert [lo["index"] for lo in info["layouts"]] == list(range(len(info["layouts"])))
    with pytest.raises(template_config.TemplateRejected):
        template_config.inspect_template(b"not a pptx")


# --- duplicate layout names ---
# The stand-in with its 'sources' layout (position 5) renamed 'concept', so two layouts are called 'concept': position 1
# (placeholders 0, 1, 2) and position 5, whose body placeholder is idx 7.

def dup_template():
    def mutate(prs):
        sources = next(lo for lo in prs.slide_layouts if lo.name == "sources")
        sources._element.cSld.set("name", "concept")
        for ph in sources.placeholders:
            if ph.placeholder_format.idx == 1:
                ph._element.nvSpPr.nvPr.ph.set("idx", "7")
    return variant(mutate)


def dup_roles(index=None, body=7):
    sources = {"layout": "concept", "placeholders": {"title": 0, "body": body}}
    if index is not None:
        sources["layout_index"] = index
    return roles_with(sources=sources)


def exported_layout_positions(minio, tmp_path):
    """The position in the template of the layout each exported slide uses, by the layout's part, not its name."""
    out = tmp_path / "out.pptx"
    export_deck(golden_course(), deck_template.configured_mapping(minio), out, resolver())
    prs = Presentation(str(out))
    positions = {lo.part.partname: i for i, lo in enumerate(prs.slide_layouts)}
    return [positions[s.slide_layout.part.partname] for s in prs.slides]


def test_inspect_reports_positions_and_duplicate_counts(env):
    info = template_config.inspect_template(dup_template())
    assert [lo["index"] for lo in info["layouts"]] == [0, 1, 2, 3, 4, 5]
    assert [lo["name_count"] for lo in info["layouts"] if lo["name"] == "concept"] == [2, 2]


def test_layout_index_chooses_the_second_duplicate(env, tmp_path):
    minio = FakeMinio()
    save(minio, data=dup_template(), roles=dup_roles(5, body=7))
    used = exported_layout_positions(minio, tmp_path)
    assert used.count(5) == 1  # the one sources slide


def test_layout_index_chooses_the_first_duplicate(env, tmp_path):
    minio = FakeMinio()
    save(minio, data=dup_template(), roles=dup_roles(1, body=1))
    used = exported_layout_positions(minio, tmp_path)
    assert 5 not in used and used.count(1) >= 2  # the concept slides and the sources slide


def test_a_duplicate_with_no_index_saves_uses_the_first_and_warns(env, tmp_path):
    minio = FakeMinio()
    save(minio, data=dup_template(), roles=dup_roles(None, body=1))
    used = exported_layout_positions(minio, tmp_path)
    assert 5 not in used
    warnings = mapping_warnings(load_mapping(deck_template.configured_mapping(minio)))
    assert len(warnings) == 2  # concept and sources both name 'concept'
    assert all("'concept'" in w and "using the first, at position 1" in w for w in warnings)
    assert any("role 'sources'" in w for w in warnings)


@pytest.mark.parametrize("index,fragment", [
    (99, "out of range"), (-1, "out of range"), ("5", "must be an integer"), (5.0, "must be an integer"),
    (True, "must be an integer"), (3, "is layout 'section'"),
])
def test_a_bad_layout_index_is_refused_naming_the_role(env, index, fragment):
    minio = FakeMinio()
    with pytest.raises(template_config.TemplateRejected) as e:
        save(minio, data=dup_template(), roles=dup_roles(index))
    msgs = [p for p in e.value.problems if "layout_index" in p]
    assert msgs and all("role 'sources'" in p for p in msgs) and fragment in msgs[0]
    assert minio.puts == []


def test_placeholders_are_checked_against_the_resolved_layout(env):
    save(FakeMinio(), data=dup_template(), roles=dup_roles(5, body=7))  # idx 7 is only on position 5
    with pytest.raises(template_config.TemplateRejected) as e:
        save(FakeMinio(), data=dup_template(), roles=dup_roles(1, body=7))
    assert any("role 'sources'" in p and "placeholder 7" in p for p in e.value.problems)


def test_layout_index_survives_save_and_read_back(env):
    minio = FakeMinio()
    save(minio, data=dup_template(), roles=dup_roles(5))
    roles = load_mapping(deck_template.configured_mapping(minio)).roles
    assert roles["sources"]["layout_index"] == 5


def test_a_unique_layout_with_no_index_has_no_warning_and_no_key(env):
    minio = FakeMinio()
    save(minio)
    mapping = load_mapping(deck_template.configured_mapping(minio))
    assert mapping_warnings(mapping) == []
    assert all("layout_index" not in spec for spec in mapping.roles.values())


# --- exports ---

def test_a_saved_template_exports_the_golden_course(env, tmp_path):
    minio = FakeMinio()
    save(minio)
    path = deck_template.configured_mapping(minio)
    assert load_mapping(path).template_path.is_file()
    assert export_deck(golden_course(), path, tmp_path / "out.pptx", resolver()).is_file()


def test_a_new_save_leaves_the_previous_dir_alone(env):
    minio = FakeMinio()
    save(minio)
    first = deck_template.configured_mapping(minio)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in first.parent.iterdir()}
    other = variant(lambda prs: setattr(prs.core_properties, "title", "second"))
    save(minio, data=other, filename="two.pptx")
    second = deck_template.configured_mapping(minio)
    assert second.parent != first.parent
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in first.parent.iterdir()} == before
    assert not list(first.parent.glob("*.part"))


# --- routes ---

class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.fixture
def client(env, monkeypatch):
    minio = FakeMinio()
    monkeypatch.setattr(deck_template, "_default_minio", lambda: minio)
    monkeypatch.setenv("TOPAZ_DIRECTORY_URL", "http://topaz.test:9393")
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    monkeypatch.setenv("SOURCE_READER", "store")
    state = {"result": Resp(200, {"check": True}), "calls": []}

    def post(url, **kw):
        state["calls"].append(kw["json"])
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr("src.auth.security.requests.post", post)
    user = User(id="u1", email="u1@example.com")
    monkeypatch.setitem(main.app.dependency_overrides, main.require_platform_reader, lambda: user)
    monkeypatch.setitem(main.app.dependency_overrides, get_current_user, lambda: user)
    c = TestClient(main.app)
    c.minio, c.decider = minio, state
    return c


def put(client, roles=None, file=STANDIN_PPTX, name="mine.pptx"):
    files = {"file": (name, file, "application/octet-stream")} if file is not None else None
    return client.put("/settings/deck-template", data={"roles": json.dumps(roles or STANDIN_ROLES)}, files=files)


def test_get_reports_the_standin_with_the_capability(client):
    r = client.get("/settings/deck-template")
    body = r.json()
    assert r.status_code == 200 and body["source"] == "standin"
    assert body["store_enabled"] and body["can_configure"]
    assert body["role_spec"]["title"] == {"required": ["title", "body"], "optional": []}
    assert body["role_spec"]["concept"]["optional"] == ["notes"]
    assert set(body["roles"]) == set(body["role_spec"]) and body["template"]["layouts"]
    assert client.decider["calls"][-1]["object_id"] == "can_configure:deck_template"


def test_get_without_a_user_or_with_the_decider_down_cannot_configure(client, monkeypatch):
    client.decider["result"] = requests.ConnectionError("down")
    assert client.get("/settings/deck-template").json()["can_configure"] is False
    monkeypatch.setitem(main.app.dependency_overrides, main.require_platform_reader, lambda: None)
    assert client.get("/settings/deck-template").json()["can_configure"] is False


def test_get_with_the_store_unset(client, monkeypatch):
    monkeypatch.delenv("DECK_TEMPLATE_STORE")
    body = client.get("/settings/deck-template").json()
    assert body["store_enabled"] is False and body["source"] == "standin"
    assert client.minio.gets == []


def test_get_with_a_store_error_is_503(client):
    client.minio.fail = "get"
    r = client.get("/settings/deck-template")
    assert r.status_code == 503 and STORE in r.json()["detail"]


def test_put_saves_then_get_reports_saved(client):
    r = put(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "saved" and body["filename"] == "mine.pptx" and body["saved_by"] == "u1@example.com"
    assert client.get("/settings/deck-template").json()["source"] == "saved"
    assert main.deck_template.template_label() == "configured"


def test_state_carries_warnings_for_a_duplicate_layout_only(client):
    assert client.get("/settings/deck-template").json()["warnings"] == []
    r = put(client, roles=dup_roles(None, body=1), file=dup_template())
    assert r.status_code == 200, r.text
    assert r.json()["warnings"]
    assert client.get("/settings/deck-template").json()["warnings"] == r.json()["warnings"]
    assert put(client).json()["warnings"] == []


def test_put_without_a_file_reuses_the_saved_pptx(client):
    assert put(client).status_code == 200
    pptx_keys = [k for k in client.minio.puts if k.endswith(".pptx")]
    r = put(client, file=None)
    assert r.status_code == 200 and r.json()["filename"] == "mine.pptx"
    assert [k for k in client.minio.puts if k.endswith(".pptx")] == pptx_keys * 2  # same content-addressed key


def test_put_without_a_file_and_nothing_saved_says_to_upload(client):
    r = put(client, file=None)
    assert r.status_code == 422 and "upload" in r.json()["detail"]["problems"][0]


def test_put_failures_list_problems(client):
    bad = roles_with()
    del bad["summary"]
    r = put(client, roles=bad)
    assert r.status_code == 422 and any("'summary' is not mapped" in p for p in r.json()["detail"]["problems"])
    assert client.minio.puts == []


def test_put_and_delete_without_a_store_are_409(client, monkeypatch):
    monkeypatch.delenv("DECK_TEMPLATE_STORE")
    assert put(client).status_code == 409
    assert client.delete("/settings/deck-template").status_code == 409


def test_delete_returns_to_the_deployment_default(client, env, tmp_path):
    monkeypatch, mapping = env
    client.minio.objects[("tpl", "a/deck.pptx")] = STANDIN_PPTX
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    monkeypatch.setenv("DECK_TEMPLATE", str(mapping))
    assert client.get("/settings/deck-template").json()["source"] == "deployment"
    assert put(client).json()["source"] == "saved"
    r = client.delete("/settings/deck-template")
    assert r.status_code == 200 and r.json()["source"] == "deployment"
    assert client.minio.removed == ["cfg/active.yaml"]
    assert any(k.endswith(".pptx") for _, k in client.minio.objects)  # the pptx stays


def test_without_the_capability_403_and_decider_down_503(client):
    client.decider["result"] = Resp(200, {"check": False})
    assert put(client).status_code == 403
    assert client.delete("/settings/deck-template").status_code == 403
    files = {"file": ("a.pptx", STANDIN_PPTX)}
    assert client.post("/settings/deck-template/inspect", files=files).status_code == 403
    client.decider["result"] = requests.ConnectionError("down")
    assert put(client).status_code == 503
    assert client.post("/settings/deck-template/inspect", files=files).status_code == 503
    assert client.minio.puts == []


def test_no_topaz_url_is_a_deny(client, monkeypatch):
    monkeypatch.delenv("TOPAZ_DIRECTORY_URL")
    assert put(client).status_code == 403


def test_inspect_ok_oversize_and_not_a_pptx(client, monkeypatch):
    r = client.post("/settings/deck-template/inspect", files={"file": ("a.pptx", STANDIN_PPTX)})
    assert r.status_code == 200 and r.json()["layouts"]
    assert client.minio.puts == []
    r = client.post("/settings/deck-template/inspect", files={"file": ("a.pptx", b"not a pptx")})
    assert r.status_code == 422
    monkeypatch.setattr(main, "MAX_TEMPLATE_BYTES", 100)
    r = client.post("/settings/deck-template/inspect", files={"file": ("a.pptx", STANDIN_PPTX)})
    assert r.status_code == 413
    assert put(client).status_code == 413
