"""The one configured deck template: DECK_TEMPLATE_URI fetched and cached, DECK_TEMPLATE the mapping."""
import shutil

import pytest
from fastapi.testclient import TestClient

from src.publishing import deck_template
from src.publishing.course import DeckExportError
from src.publishing.deck_export import export_deck, load_mapping
from src.workbench import main
from tests.deck_fixtures import STANDIN_DIR, golden_course, resolver

URI = "s3://tpl/a/deck.pptx"


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
    def __init__(self, data=None, fail=False):
        self.data = data if data is not None else (STANDIN_DIR / "standin.pptx").read_bytes()
        self.fail = fail
        self.calls = []

    def get_object(self, bucket, key):
        self.calls.append((bucket, key))
        if self.fail:
            raise OSError("no such key")
        return FakeObj(self.data)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(deck_template, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(deck_template, "_logged_standin", False)
    monkeypatch.delenv("DECK_TEMPLATE_URI", raising=False)
    monkeypatch.delenv("DECK_TEMPLATE", raising=False)
    mapping = tmp_path / "mount" / "deck-template.yaml"
    mapping.parent.mkdir()
    shutil.copy(STANDIN_DIR / "deck-template.yaml", mapping)
    return monkeypatch, mapping


def test_parse_uri():
    assert deck_template.parse_uri("s3://b/a/k.pptx") == ("b", "a/k.pptx")
    for bad in ("b/k", "s3://b", "s3:///k", "http://x/y"):
        with pytest.raises(ValueError, match="s3://<bucket>/<key>"):
            deck_template.parse_uri(bad)


def test_unset_uses_standin_and_logs_once(env, capsys):
    assert deck_template.configured_mapping() == deck_template.STANDIN_MAPPING
    assert deck_template.configured_mapping() == deck_template.STANDIN_MAPPING
    assert capsys.readouterr().out.count("DECK_TEMPLATE_URI is not set") == 1


def test_configured_template_exports(env, tmp_path):
    monkeypatch, mapping = env
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    monkeypatch.setenv("DECK_TEMPLATE", str(mapping))
    minio = FakeMinio()
    path = deck_template.configured_mapping(minio)
    loaded = load_mapping(path)
    assert loaded.template_path == tmp_path / "cache" / "template.pptx"
    assert loaded.template_path.is_file()
    assert minio.calls == [("tpl", "a/deck.pptx")]
    out = export_deck(golden_course(), path, tmp_path / "out.pptx", resolver())
    assert out.is_file()


def test_cache_hit_and_changed_uri(env):
    monkeypatch, mapping = env
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    monkeypatch.setenv("DECK_TEMPLATE", str(mapping))
    minio = FakeMinio()
    deck_template.configured_mapping(minio)
    deck_template.configured_mapping(minio)
    assert len(minio.calls) == 1
    monkeypatch.setenv("DECK_TEMPLATE_URI", "s3://tpl/other.pptx")
    deck_template.configured_mapping(minio)
    assert minio.calls[-1] == ("tpl", "other.pptx") and len(minio.calls) == 2


def test_fetch_failure_names_the_uri(env):
    monkeypatch, mapping = env
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    monkeypatch.setenv("DECK_TEMPLATE", str(mapping))
    with pytest.raises(DeckExportError) as e:
        deck_template.configured_mapping(FakeMinio(fail=True))
    assert URI in str(e.value.args) or URI in str(e.value)


def test_uri_without_mapping_names_deck_template(env):
    monkeypatch, _ = env
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    with pytest.raises(DeckExportError) as e:
        deck_template.configured_mapping(FakeMinio())
    assert "DECK_TEMPLATE" in str(e.value.args)


def test_templates_route(env):
    monkeypatch, _ = env
    client = TestClient(main.app)
    assert client.get("/render/templates").json() == {"templates": ["standin"]}
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    assert client.get("/render/templates").json() == {"templates": ["configured"]}


def test_warm_never_raises(env, capsys):
    monkeypatch, _ = env
    monkeypatch.setenv("DECK_TEMPLATE_URI", URI)
    deck_template.warm()
    assert "DECK_TEMPLATE" in capsys.readouterr().out
