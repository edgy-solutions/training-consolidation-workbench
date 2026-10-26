"""Signed asset links. <img> tags send no bearer token, so in live mode an asset URL carries an
expiry and an HMAC over the asset name. Only routes that already checked the user hand them out
(architect, b4), and the asset route serves nothing without a valid pair."""
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

# One api replica (render jobs are in-process too), so a per-process key suffices; restarting
# the api voids open links and the UI fetches new ones. WB_ASSET_LINK_KEY shares one across replicas.
_KEY = (os.getenv("WB_ASSET_LINK_KEY") or "").encode() or secrets.token_bytes(32)


def ttl_seconds() -> int:
    return int(os.getenv("WB_ASSET_LINK_SECONDS", "3600"))


def _mac(name: str, exp: int) -> str:
    return hmac.new(_KEY, f"{exp}\n{name}".encode(), hashlib.sha256).hexdigest()


def signed_query(name: str, now: Optional[float] = None) -> str:
    """The query string that makes `name` fetchable until the TTL runs out."""
    exp = int(now if now is not None else time.time()) + ttl_seconds()
    return f"exp={exp}&sig={_mac(name, exp)}"


def valid(name: str, exp: Optional[str], sig: Optional[str], now: Optional[float] = None) -> bool:
    if not exp or not sig or not exp.isdigit():
        return False
    if int(exp) < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(_mac(name, int(exp)), sig)
