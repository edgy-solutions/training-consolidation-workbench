"""Safety-gate coverage review of the workbench's own writes to the shared stores (2026-10-25).
Written by lane/saf; both arms were red on wb 18b1710 and are green since the fix that placed this file.

b1  `get_current_user` runs `sync_user_to_neo4j` (a MERGE/SET on the shared graph) on EVERY
    authenticated request, so the flag WB_STORE_WRITES=off does not hold the workbench's writes:
    a read-only GET still writes. Control: the same call with the flag on is expected to write
    (that is the writer being exercised, so the arm cannot pass by never calling it).
b2  The guard is attached per route. Derive the population from the app (every POST/PUT/PATCH/DELETE)
    and require each to carry `require_store_writes` or be in the declared READ-ONLY set. A route
    in neither is UNDECIDED and fails: `/render/trigger` is one (it uploads to the shared
    `published` bucket when the runner is dagster, and creates a job record when local).
"""
import pytest
from fastapi.routing import APIRoute

from src.auth import security
from src.workbench import main


class _Rec:
    def __init__(self):
        self.runs = []

    def session(self):
        rec = self

        class S:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def run(s, q, **kw):
                rec.runs.append(q)

        return S()

    def close(self):
        pass


def _auth(monkeypatch, flag):
    rec = _Rec()
    class K:
        def __init__(s, url): pass
        def get_signing_key_from_jwt(s, t):
            class Key: key = "k"
            return Key
    monkeypatch.setattr(security, "PyJWKClient", K)
    monkeypatch.setattr(security.jwt, "get_unverified_header", lambda t: {})
    monkeypatch.setattr(security.jwt, "decode", lambda *a, **k: {security.AUTHZ_CLAIM: "u1", "email": "u@x"})
    monkeypatch.setattr(security, "get_db_driver", lambda: rec)
    if flag is None:
        monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    else:
        monkeypatch.setenv("WB_STORE_WRITES", flag)
    return rec


def test_CONTROL_with_the_flag_on_the_sync_writes(monkeypatch):
    rec = _auth(monkeypatch, "on")
    security.get_current_user("tok")
    assert any("MERGE (u:User" in q for q in rec.runs)


def test_b1_an_authenticated_request_writes_nothing_while_the_flag_is_off(monkeypatch):
    rec = _auth(monkeypatch, None)
    security.get_current_user("tok")
    assert rec.runs == [], f"flag off, yet {len(rec.runs)} statement(s) reached the graph"


#: mutating routes that write nothing to a shared store: decided in main, each with its reason.
READ_ONLY_POSTS = main.READ_ONLY_POSTS


def test_b2_every_mutating_route_is_guarded_or_decided_read_only():
    undecided = []
    for r in main.app.routes:
        if not isinstance(r, APIRoute) or not (r.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        guarded = any(d.call is main.require_store_writes for d in r.dependant.dependencies)
        if not guarded and r.path not in READ_ONLY_POSTS:
            undecided.append(r.path)
    assert undecided == [], f"neither guarded nor decided read-only: {undecided}"


def test_CONTROL_the_population_walk_finds_the_guarded_routes():
    guarded = [r.path for r in main.app.routes if isinstance(r, APIRoute) and
               any(d.call is main.require_store_writes for d in r.dependant.dependencies)]
    assert "/draft/create" in guarded and len(guarded) >= 10
