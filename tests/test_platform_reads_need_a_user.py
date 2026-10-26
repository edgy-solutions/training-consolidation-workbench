"""Live reads of platform data (decks, slides, concepts, pages) need a signed-in user of the realm
(architect, b4). Fixture reads serve committed test data and stay open."""
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.auth.security import User
from src.workbench import main

# Served to <img> tags, which send no bearer; the asset route carries its own check.
TOKENLESS = {"/source/fixture-asset/{name}"}


def platform_routes():
    for r in main.app.routes:
        if isinstance(r, APIRoute) and r.path.startswith(("/source/", "/search/")) and r.path not in TOKENLESS:
            for m in sorted(r.methods):
                yield m, r


def concrete(path):
    return path.replace("{course_id}", "c1").replace("{slide_id}", "s1").replace("{name}", "n").replace("{term}", "t")


ROUTES = [(m, r.path) for m, r in platform_routes()]


def test_every_platform_route_is_guarded():
    assert len(ROUTES) >= 13
    for m, r in platform_routes():
        deps = {d.call for d in r.dependant.dependencies}
        assert main.require_platform_reader in deps, f"{m} {r.path} reads platform data without the guard"


@pytest.mark.parametrize("mode", ["store", "direct", ""])
@pytest.mark.parametrize("method,path", ROUTES)
def test_live_reads_without_a_token_are_401(monkeypatch, mode, method, path):
    monkeypatch.setenv("SOURCE_READER", mode)
    r = TestClient(main.app, raise_server_exceptions=False).request(method, concrete(path), json=[])
    assert r.status_code == 401


def test_a_bad_token_is_401(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "store")
    r = TestClient(main.app).get("/source/tree", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_a_realm_user_passes_the_guard(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "store")
    seen = []
    monkeypatch.setattr(main, "get_current_user", lambda token: seen.append(token) or User(id="person-7"))
    assert main.require_platform_reader("tok").id == "person-7"
    assert seen == ["tok"]
    with pytest.raises(HTTPException) as e:
        main.require_platform_reader(None)
    assert e.value.status_code == 401


def test_fixture_reads_stay_open(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "fixture")
    assert main.require_platform_reader(None) is None
    assert TestClient(main.app).get("/source/tree").status_code == 200


def test_synthesis_status_needs_a_token():
    assert TestClient(main.app).get("/synthesis/status/r1").status_code == 401
