"""The api answers under /api as well as at the root; only an exact /api or /api/... segment is stripped."""
import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.auth.security import User, get_current_user
from src.workbench import main
from src.workbench.api_prefix import ApiPrefix


async def _echo(request):
    return JSONResponse({"path": request.url.path, "q": dict(request.query_params)})


def _mini():
    app = Starlette(routes=[Route("/{rest:path}", _echo)])
    app.add_middleware(ApiPrefix)
    return TestClient(app)


def test_strips_prefix_and_keeps_query():
    assert _mini().get("/api/a/b?x=1").json() == {"path": "/a/b", "q": {"x": "1"}}


def test_bare_prefix_maps_to_root():
    assert _mini().get("/api").json()["path"] == "/"


def test_other_paths_pass_through():
    c = _mini()
    assert c.get("/apifoo").json()["path"] == "/apifoo"
    assert c.get("/source/x").json()["path"] == "/source/x"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "store")
    monkeypatch.setitem(main.app.dependency_overrides, main.require_platform_reader, lambda: None)
    monkeypatch.setitem(main.app.dependency_overrides, get_current_user, lambda: User(id="u1", email="u1@example.com"))
    return TestClient(main.app)


def test_healthz_same_under_prefix(client):
    a, b = client.get("/healthz"), client.get("/api/healthz")
    assert (a.status_code, a.json()) == (b.status_code, b.json()) == (200, {"status": "ok"})


def test_review_access_same_status_under_prefix(client):
    assert client.get("/api/alignment/review-access").status_code == client.get("/alignment/review-access").status_code


def test_apifoo_is_not_stripped(client):
    assert client.get("/apifoo/healthz").status_code == 404
