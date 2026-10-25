"""Disk-backed render jobs for the in-process runner.

State lives under EXPORT_DIR so any process in the pod (the server, or a script run with
kubectl exec) shares it. The api runs one replica (charts values api.replicaCount: 1), so a
job is only ever read from the pod that wrote it.
"""
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from src.publishing.course import DeckExportError
from src.publishing.render import render_project

RUN_ID_RE = re.compile(r"^local-[0-9a-f]{32}$")
MAX_AGE_SECONDS = 24 * 3600


def export_dir() -> Path:
    return Path(os.getenv("WB_EXPORT_DIR") or Path(tempfile.gettempdir()) / "wb-exports")


def new_run_id() -> str:
    return "local-" + uuid.uuid4().hex


def _job_dir(run_id) -> Path:
    return export_dir() / run_id


def _write(run_id, record):
    d = _job_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    part = d / "job.json.part"
    part.write_text(json.dumps(record), encoding="utf-8", newline="\n")
    os.replace(part, d / "job.json")


def _sweep():
    root = export_dir()
    if not root.is_dir():
        return
    cutoff = time.time() - MAX_AGE_SECONDS
    for d in root.iterdir():
        if not (d.is_dir() and RUN_ID_RE.match(d.name)):
            continue
        try:
            created = json.loads((d / "job.json").read_text(encoding="utf-8")).get("created", 0)
        except (OSError, ValueError):
            created = 0
        if created < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def create_job(project_id, filename, fmt, owner) -> dict:
    _sweep()
    run_id = new_run_id()
    record = {
        "run_id": run_id, "status": "QUEUED", "filename": filename, "format": fmt,
        "project_id": project_id, "owner": owner, "created": time.time(), "problems": [],
    }
    _write(run_id, record)
    return record


def read_job(run_id):
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
        return None
    try:
        return json.loads((_job_dir(run_id) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def job_file(run_id):
    job = read_job(run_id)
    if not job or job["status"] != "SUCCESS":
        return None
    path = _job_dir(run_id) / job["filename"]
    return path if path.is_file() else None


def run_job(run_id, template_name, *, neo4j_client, minio_client, reader):
    """Runs as a background task: records the outcome, never raises."""
    job = read_job(run_id)
    if not job:
        return
    out = _job_dir(run_id) / job["filename"]
    try:
        _write(run_id, {**job, "status": "STARTED"})
        render_project(job["project_id"], job["format"], template_name, out,
                       neo4j_client=neo4j_client, minio_client=minio_client, reader=reader)
        _write(run_id, {**job, "status": "SUCCESS"})
    except DeckExportError as e:
        _fail(run_id, job, out, e.problems)
    except Exception as e:
        _fail(run_id, job, out, [f"{type(e).__name__}: {e}"])


def _fail(run_id, job, out, problems):
    try:
        out.unlink(missing_ok=True)
        _write(run_id, {**job, "status": "FAILURE", "problems": problems})
    except Exception:
        pass
