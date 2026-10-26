"""The one configured deck template: a .pptx from object storage, cached on local disk.

DECK_TEMPLATE_URI (s3://<bucket>/<key>) names the .pptx; DECK_TEMPLATE is the mapping yaml file.
With the URI unset, exports use the repo stand-in.
"""
import os
import tempfile
import threading
from pathlib import Path

import yaml

from src.publishing.course import DeckExportError

STANDIN_MAPPING = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "templates" / "standin" / "deck-template.yaml"
)
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


def configured_mapping(minio=None) -> Path:
    global _logged_standin
    uri = (os.getenv("DECK_TEMPLATE_URI") or "").strip()
    if not uri:
        if not _logged_standin:
            _logged_standin = True
            print("deck template: DECK_TEMPLATE_URI is not set; exports use the stand-in template")
        return STANDIN_MAPPING
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
    return out


def warm():
    """Fetch the template at startup and log the outcome; never raises."""
    try:
        path = configured_mapping()
        if path == STANDIN_MAPPING:
            return
        pptx = path.parent / "template.pptx"
        print(f"deck template: using {os.getenv('DECK_TEMPLATE_URI')} ({pptx.stat().st_size} bytes)")
    except Exception as e:
        print(f"deck template: {e}")


def template_label() -> str:
    return "configured" if (os.getenv("DECK_TEMPLATE_URI") or "").strip() else "standin"
