"""Users, and so draft ownership, are keyed on the token's authz_id claim, never on sub."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.auth import security
from src.auth.security import user_from_claims

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISS = "https://sso.example/realms/fleet"
AUD = "training-workbench"


@pytest.fixture
def verify(monkeypatch):
    """get_current_user against a stub JWKS that serves KEY's public half; Neo4j sync recorded, not run."""
    class StubJwks:
        def __init__(self, url):
            pass

        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": KEY.public_key()})()

    synced = []
    monkeypatch.setattr(security, "PyJWKClient", StubJwks)
    monkeypatch.setattr(security, "sync_user_to_neo4j", synced.append)
    monkeypatch.setenv("WB_STORE_WRITES", "on")
    monkeypatch.setenv("KEYCLOAK_AUDIENCE", AUD)
    monkeypatch.setenv("KEYCLOAK_ISSUER", ISS)

    def run(**claims):
        """A token from the right client and realm unless a claim overrides it; None drops a claim."""
        body = {"exp": int(time.time()) + 60, "iss": ISS, "aud": AUD, **claims}
        token = jwt.encode({k: v for k, v in body.items() if v is not None}, KEY, algorithm="RS256")
        return security.get_current_user(token)
    return run, synced


def test_id_is_authz_id_not_sub():
    user = user_from_claims({"sub": "kc-uuid-1", "authz_id": "ada@example.com", "email": "ada@example.com"})
    assert user.id == "ada@example.com"


def test_two_logins_of_one_person_are_one_user():
    local = user_from_claims({"sub": "kc-uuid-local", "authz_id": "person-7"})
    brokered = user_from_claims({"sub": "kc-uuid-brokered", "authz_id": "person-7"})
    assert local.id == brokered.id == "person-7"


def test_no_authz_id_is_401_even_with_sub():
    with pytest.raises(HTTPException) as e:
        user_from_claims({"sub": "kc-uuid-1", "email": "ada@example.com"})
    assert e.value.status_code == 401
    assert "authz_id" in e.value.detail


def test_email_is_optional():
    user = user_from_claims({"authz_id": "person-7"})
    assert user.email is None


def test_roles_from_realm_access():
    assert user_from_claims({"authz_id": "p", "realm_access": {"roles": ["a", "b"]}}).roles == ["a", "b"]


def test_signed_token_keys_user_and_sync_on_authz_id(verify):
    run, synced = verify
    user = run(sub="kc-uuid-1", authz_id="person-7", email="p7@example.com")
    assert user.id == "person-7"
    assert [u.id for u in synced] == ["person-7"]


def test_signed_token_without_authz_id_is_rejected_unsynced(verify):
    run, synced = verify
    with pytest.raises(HTTPException) as e:
        run(sub="kc-uuid-1", email="p7@example.com")
    assert e.value.status_code == 401
    assert "authz_id" in e.value.detail
    assert synced == []
