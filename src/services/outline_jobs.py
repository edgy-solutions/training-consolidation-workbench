"""Disk-backed Generate Outline jobs for the in-process runner.

Same layout as src/publishing/render_jobs.py: one record per job under export_dir(), written
atomically, found only through its own id (128 bits from the CSPRNG). The api runs one replica,
so a QUEUED or RUNNING record whose boot id is not ours belongs to a process that is gone.
"""
import json
import os
import re
import secrets
import shutil
import time
import traceback

from src.publishing.render_jobs import export_dir

JOB_ID_RE = re.compile(r"^outline-[0-9a-f]{32}$")
MAX_AGE_SECONDS = 24 * 3600
BOOT_ID = secrets.token_hex(8)
LOST_ERROR = "The api restarted while this outline was being generated; nothing was saved."

STEPS = [
    {"key": "sources", "label": "Reading the source outlines"},
    {"key": "llm", "label": "Drafting the outline with the LLM"},
    {"key": "slides", "label": "Matching slides to sections"},
    {"key": "save", "label": "Saving the draft"},
]


def _job_dir(job_id):
    return export_dir() / job_id


def _write(job_id, record):
    d = _job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    part = d / "job.json.part"
    part.write_text(json.dumps(record), encoding="utf-8", newline="\n")
    os.replace(part, d / "job.json")


def _load(job_id):
    try:
        return json.loads((_job_dir(job_id) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sweep():
    root = export_dir()
    if not root.is_dir():
        return
    for d in root.iterdir():
        if not (d.is_dir() and JOB_ID_RE.match(d.name)):
            continue
        job = _load(d.name) or {}
        if time.time() - job.get("created", 0) > MAX_AGE_SECONDS:
            shutil.rmtree(d, ignore_errors=True)


def create_job(owner) -> dict:
    _sweep()
    job_id = "outline-" + secrets.token_hex(16)
    record = {
        "job_id": job_id, "status": "QUEUED", "step": None, "owner": owner,
        "created": time.time(), "started": None, "finished": None,
        "boot": BOOT_ID, "result": None, "error": None,
    }
    _write(job_id, record)
    return record


def _update(job_id, **fields):
    job = _load(job_id)
    if job:
        _write(job_id, {**job, **fields})


def set_step(job_id, step):
    job = _load(job_id)
    if job:
        _write(job_id, {**job, "status": "RUNNING", "step": step,
                        "started": job.get("started") or time.time()})


def finish(job_id, result):
    _update(job_id, status="SUCCESS", result=result, finished=time.time())


def fail(job_id, error):
    _update(job_id, status="FAILURE", error=error, finished=time.time())


def read_job(job_id, owner):
    """None for a malformed id, a missing record, or another owner's job."""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        return None
    job = _load(job_id)
    if not job or job.get("owner") != owner:
        return None
    if job["status"] in ("QUEUED", "RUNNING") and job.get("boot") != BOOT_ID:
        job = {**job, "status": "LOST", "error": LOST_ERROR, "finished": time.time()}
        _write(job_id, job)
    return job


def run_job(job_id, *, reader, **generate_kwargs):
    """Runs as a background task: records the outcome, never raises."""
    from src.services.generator_service import GeneratorService

    service = None
    try:
        service = GeneratorService(reader=reader)
        result = service.generate_skeleton(
            **generate_kwargs, progress=lambda step: set_step(job_id, step))
        sections = result.get("sections", [])
        finish(job_id, {
            "project_id": result["project_id"],
            "section_count": sum(1 for s in sections if not s.get("is_unassigned")),
            "unassigned_count": result.get("unassigned_count", 0),
        })
    except Exception as e:
        traceback.print_exc()
        fail(job_id, str(e))
    finally:
        if service is not None:
            service.close()
