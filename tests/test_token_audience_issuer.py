"""Every token must be minted for the workbench by the realm (architect, b5): aud names the
workbench's client and iss is the realm's issuer; anything else is a 401."""
import pytest
from fastapi import HTTPException

from tests.test_authz_identity import AUD, ISS, verify  # noqa: F401 (verify is a fixture)


def refused(run, **claims):
    with pytest.raises(HTTPException) as e:
        run(authz_id="person-7", **claims)
    assert e.value.status_code == 401
    return e.value.detail


def test_the_workbench_token_is_accepted(verify):
    run, _ = verify
    assert run(authz_id="person-7").id == "person-7"


def test_aud_may_list_other_clients_too(verify):
    run, _ = verify
    assert run(authz_id="person-7", aud=["account", AUD]).id == "person-7"


def test_another_clients_token_is_refused(verify):
    run, synced = verify
    refused(run, aud="cortex-ui")
    refused(run, aud=["account"])
    assert synced == []


def test_a_token_without_aud_is_refused(verify):
    run, _ = verify
    assert "aud" in refused(run, aud=None)


def test_another_realms_token_is_refused(verify):
    run, synced = verify
    refused(run, iss="https://sso.example/realms/other")
    refused(run, iss=ISS + "/")
    assert synced == []


def test_a_token_without_iss_is_refused(verify):
    run, _ = verify
    assert "iss" in refused(run, iss=None)


def test_the_issuer_defaults_to_the_realm_url(monkeypatch):
    from src.auth import security
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    monkeypatch.delenv("KEYCLOAK_AUDIENCE", raising=False)
    assert security.token_issuer() == security.KEYCLOAK_URL
    assert security.token_audience() == "training-workbench"
