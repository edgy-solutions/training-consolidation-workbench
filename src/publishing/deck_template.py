"""The one configured deck template: a .pptx from object storage, cached on local disk.

Precedence: a template saved from the settings screen (DECK_TEMPLATE_STORE) > DECK_TEMPLATE_URI + DECK_TEMPLATE >
the repo stand-in. DECK_TEMPLATE_URI (s3://<bucket>/<key>) names the .pptx; DECK_TEMPLATE is the mapping yaml file.
With DECK_TEMPLATE_STORE unset, nothing here reads the store.
"""
import hashlib
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from src.publishing.course import DeckExportError

STANDIN_MAPPING = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "templates" / "standin" / "deck-template.yaml"
)
POINTER_NAME = "active.yaml"
DECK_TEMPLATE_VERSION = 1
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_logged_standin = False


def parse_uri(uri):
    """(bucket, key) of s3://<bucket>/<key>."""
    prefix = "s3://"
    if isinstance(uri, str) and uri.startswith(prefix):
        bucket, _, key = uri[len(prefix):].partition("/")
        if bucket and key:
            return bucket, key
    raise ValueError(f"deck template URI must be s3://<bucket>/<key>, got {uri!r}")


def cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "wb-template"


def _part(path: Path) -> Path:
    # Exports run in parallel threads; each writes its own part file, then replaces atomically.
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")


def _replace_text(path: Path, text: str):
    part = _part(path)
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


def _default_minio():
    from src.storage.minio import MinioClient
    return MinioClient(secure=os.getenv("MINIO_SECURE", "false").lower() == "true")


def ensure_cached(uri, minio=None) -> Path:
    """The cached template file for uri, fetched once."""
    try:
        bucket, key = parse_uri(uri)
        dest = cache_dir() / "template.pptx"
        marker = cache_dir() / "template.uri"
        if dest.is_file() and marker.is_file() and marker.read_text(encoding="utf-8") == uri:
            return dest
        cache_dir().mkdir(parents=True, exist_ok=True)
        obj = (minio or _default_minio()).get_object(bucket, key)
        try:
            data = obj.read()
        finally:
            obj.close()
            obj.release_conn()
        part = _part(dest)
        part.write_bytes(data)
        os.replace(part, dest)
        _replace_text(marker, uri)
        return dest
    except Exception as e:
        raise DeckExportError([f"deck template {uri} could not be fetched: {e}"])


# --- The saved template (DECK_TEMPLATE_STORE) -------------------------------------------------

def store_location():
    """(bucket, prefix) of DECK_TEMPLATE_STORE, or None when saving from the UI is off."""
    uri = (os.getenv("DECK_TEMPLATE_STORE") or "").strip()
    if not uri:
        return None
    try:
        bucket, prefix = parse_uri(uri)
    except ValueError as e:
        raise DeckExportError([f"DECK_TEMPLATE_STORE is invalid: {e}"])
    return bucket, prefix.strip("/")


def _key(prefix, name):
    return f"{prefix}/{name}" if prefix else name


def _store_error(what, e):
    return DeckExportError([f"deck template store {os.getenv('DECK_TEMPLATE_STORE')} {what}: {e}"])


def _read_object(minio, bucket, key) -> bytes:
    obj = minio.get_object(bucket, key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


def _read_pointer(minio=None):
    """(raw bytes, parsed dict) of the saved pointer, or None when none is saved or saving is off."""
    loc = store_location()
    if loc is None:
        return None
    bucket, prefix = loc
    try:
        raw = _read_object(minio or _default_minio(), bucket, _key(prefix, POINTER_NAME))
    except Exception as e:
        if getattr(e, "code", "") == "NoSuchKey":
            return None
        raise _store_error("could not be read", e)
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise _store_error(f"holds an unreadable {POINTER_NAME}", e)
    if not isinstance(parsed, dict) or not parsed.get("template") or not isinstance(parsed.get("roles"), dict):
        raise _store_error(f"holds a malformed {POINTER_NAME}", "it needs a template and roles")
    return raw, parsed


def read_saved(minio=None):
    """The saved pointer as a dict, or None. A store error raises DeckExportError: nothing falls back."""
    found = _read_pointer(minio)
    return found[1] if found else None


def _materialise_saved(raw, pointer, minio=None) -> Path:
    """The mapping path of an immutable dir for one pointer, so a new save never alters a dir an export reads."""
    root = cache_dir() / f"saved-{hashlib.sha256(raw).hexdigest()[:16]}"
    mapping = root / "deck-template.yaml"
    pptx = root / "template.pptx"
    if mapping.is_file() and pptx.is_file():
        return mapping
    try:
        bucket, key = parse_uri(pointer["template"])
        root.mkdir(parents=True, exist_ok=True)
        data = _read_object(minio or _default_minio(), bucket, key)
    except Exception as e:
        raise DeckExportError([f"saved deck template {pointer.get('template')} could not be fetched: {e}"])
    part = _part(pptx)
    part.write_bytes(data)
    os.replace(part, pptx)
    body = {"deck_template": pointer.get("deck_template", DECK_TEMPLATE_VERSION), "template": pptx.name,
            "roles": pointer["roles"]}
    _replace_text(mapping, yaml.safe_dump(body, sort_keys=False))  # lands last: it marks the dir complete
    return mapping


@dataclass
class Current:
    source: str  # "saved" | "deployment" | "standin"
    mapping_path: Path
    saved: Optional[dict] = None


def current(minio=None) -> Current:
    """The template in force: saved pointer > DECK_TEMPLATE_URI/DECK_TEMPLATE > stand-in."""
    global _logged_standin
    found = _read_pointer(minio)
    if found:
        return Current("saved", _materialise_saved(found[0], found[1], minio), found[1])
    uri = (os.getenv("DECK_TEMPLATE_URI") or "").strip()
    if not uri:
        if not _logged_standin:
            _logged_standin = True
            print("deck template: DECK_TEMPLATE_URI is not set; exports use the stand-in template")
        return Current("standin", STANDIN_MAPPING)
    mapping_file = (os.getenv("DECK_TEMPLATE") or "").strip()
    if not mapping_file:
        raise DeckExportError(["DECK_TEMPLATE_URI is set but DECK_TEMPLATE (the mapping yaml path) is not"])
    pptx = ensure_cached(uri, minio)
    try:
        raw = yaml.safe_load(Path(mapping_file).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise DeckExportError([f"mapping file {mapping_file} could not be read: {e}"])
    if not isinstance(raw, dict):
        raise DeckExportError([f"mapping file {mapping_file} is not a mapping"])
    raw["template"] = pptx.name
    out = cache_dir() / "deck-template.yaml"
    _replace_text(out, yaml.safe_dump(raw, sort_keys=False))
    return Current("deployment", out)


def configured_mapping(minio=None) -> Path:
    return current(minio).mapping_path


def saved_pptx(minio=None):
    """(.pptx bytes, pointer) of the saved template, or None when nothing is saved."""
    found = _read_pointer(minio)
    if not found:
        return None
    mapping = _materialise_saved(found[0], found[1], minio)
    return (mapping.parent / "template.pptx").read_bytes(), found[1]


def save(pptx_bytes, roles, filename, saved_by, minio=None) -> dict:
    """Upload the .pptx under its content hash, then write the pointer last, so a save is atomic."""
    loc = store_location()
    if loc is None:
        raise DeckExportError(["saving needs DECK_TEMPLATE_STORE"])
    bucket, prefix = loc
    sha = hashlib.sha256(pptx_bytes).hexdigest()
    pointer = {
        "deck_template": DECK_TEMPLATE_VERSION,
        "template": f"s3://{bucket}/{_key(prefix, sha + '.pptx')}",
        "source": {"filename": filename, "saved_by": saved_by, "saved_at": datetime.now(timezone.utc).isoformat()},
        "roles": roles,
    }
    try:
        minio = minio or _default_minio()
        minio.upload_bytes(bucket, _key(prefix, sha + ".pptx"), pptx_bytes, PPTX_TYPE)
        minio.upload_bytes(bucket, _key(prefix, POINTER_NAME),
                           yaml.safe_dump(pointer, sort_keys=False).encode("utf-8"), "application/yaml")
    except Exception as e:
        raise _store_error("could not be written", e)
    return pointer


def delete_saved(minio=None):
    """Remove the pointer only, returning to the deployment default; the .pptx objects stay."""
    loc = store_location()
    if loc is None:
        raise DeckExportError(["resetting needs DECK_TEMPLATE_STORE"])
    try:
        (minio or _default_minio()).remove_object(loc[0], _key(loc[1], POINTER_NAME))
    except Exception as e:
        raise _store_error("could not be written", e)


def warm():
    """Fetch the template at startup and log the outcome; never raises."""
    try:
        cur = current()
        if cur.source == "standin":
            return
        pptx = cur.mapping_path.parent / "template.pptx"
        what = cur.saved["template"] if cur.saved else os.getenv("DECK_TEMPLATE_URI")
        print(f"deck template: using {cur.source} template {what} ({pptx.stat().st_size} bytes)")
    except Exception as e:
        print(f"deck template: {e}")


def template_label() -> str:
    try:
        if _read_pointer() is not None:
            return "configured"
    except Exception as e:
        print(f"deck template: {e}")
        return "configured"
    return "configured" if (os.getenv("DECK_TEMPLATE_URI") or "").strip() else "standin"
