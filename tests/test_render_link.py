"""The tokenless /render/file link is a presigned-style capability (architect ruling):
128 CSPRNG bits in the run id, a 15-minute expiry, and the file bound to its own run."""
import json
import time

from src.publishing import render_jobs
from src.publishing.render_jobs import LINK_TTL_SECONDS, RUN_ID_RE, create_job
from tests.test_render_local import events, harness, trigger  # noqa: F401 (harness is a fixture)


def finished_ago(run_id, seconds):
    path = render_jobs.export_dir() / run_id / "job.json"
    rec = json.loads(path.read_text())
    rec["finished"] = time.time() - seconds
    path.write_text(json.dumps(rec))


def export(client):
    run_id = trigger(client).json()["run_id"]
    evs = events(client.get(f"/render/events/{run_id}").text)
    assert [e for e, _ in evs][-1] == "complete", evs
    return run_id


def test_run_id_is_128_bits_from_the_csprng(monkeypatch):
    asked = []
    real = render_jobs.secrets.token_hex

    def spy(n):
        asked.append(n)
        return real(n)

    monkeypatch.setattr(render_jobs.secrets, "token_hex", spy)
    run_id = render_jobs.new_run_id()
    assert asked == [16]
    assert RUN_ID_RE.match(run_id)
    assert len({render_jobs.new_run_id() for _ in range(1000)}) == 1000


def test_link_works_inside_the_ttl(harness):
    client, _, _ = harness
    run_id = export(client)
    finished_ago(run_id, LINK_TTL_SECONDS - 60)
    r = client.get(f"/render/file/{run_id}")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


def test_link_is_404_after_15_minutes_and_the_run_is_gone(harness):
    client, _, _ = harness
    assert LINK_TTL_SECONDS == 15 * 60
    run_id = export(client)
    finished_ago(run_id, LINK_TTL_SECONDS + 1)
    assert client.get(f"/render/file/{run_id}").status_code == 404
    assert client.get(f"/render/events/{run_id}").status_code == 404
    assert not (render_jobs.export_dir() / run_id).exists()


def test_expired_successes_are_swept(harness):
    client, _, _ = harness
    old = export(client)
    finished_ago(old, LINK_TTL_SECONDS + 1)
    fresh = create_job("p", "b.pptx", "pptx", "u1")["run_id"]
    assert not (render_jobs.export_dir() / old).exists()
    assert (render_jobs.export_dir() / fresh).exists()


def test_file_is_bound_to_its_own_run(harness):
    client, _, _ = harness
    a = export(client)
    b = create_job("proj-hydraulics", "other.pptx", "pptx", "u1")["run_id"]
    # b's record exists but its export never ran: a's file is not reachable through b
    assert client.get(f"/render/file/{b}").status_code == 404
    for path in ("/render/file/", f"/render/file/{a}/..", f"/render/file/{a[:-1]}",
                 "/render/download/Hydraulic_Systems.pptx"):
        assert client.get(path).status_code in (404, 405), path
