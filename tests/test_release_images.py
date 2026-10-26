import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release_images.py"
_spec = importlib.util.spec_from_file_location("release_images", _path)
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)

# The api .dockerignore as it will be after the edit; hard-coded on purpose.
API_RULES = """
.git
.github
.venv
venv
**/__pycache__
**/*.pyc
*.egg-info
.env
*.log
build/
data/
keycloak_data/
extracted_media_test/
test_docs/
frontend/
charts/
sessions/
docs/
scripts/roll.sh
**/*.md
.dockerignore
tests/*
!tests/fixtures
tests/fixtures/*
!tests/fixtures/training
!tests/fixtures/templates
"""

EXCLUDED = ["frontend/src/App.tsx", "tests/test_x.py", "tests/fixtures/export/a.json",
            "sessions/a.md", "README.md", "scripts/roll.sh", ".dockerignore",
            "charts/x/values.yaml"]
ADMITTED = ["src/workbench/main.py", "tests/fixtures/training/golden.json",
            "tests/fixtures/templates/standin/deck-template.yaml",
            "scripts/list_projects.py", "Dockerfile", "uv.lock"]


@pytest.mark.parametrize("p", EXCLUDED)
def test_excluded(p):
    assert not ri.admitted(ri.parse_rules(API_RULES), p)


@pytest.mark.parametrize("p", ADMITTED)
def test_admitted(p):
    assert ri.admitted(ri.parse_rules(API_RULES), p)


# ---- selection in a throwaway repo ----

def _git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def _commit(repo, files, n):
    for name, body in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    _git(repo, "add", "-A")
    d = f"{1700000000 + n * 100} +0000"
    env = {**os.environ, "GIT_COMMITTER_DATE": d, "GIT_AUTHOR_DATE": d}
    _git(repo, "commit", "-q", "-m", f"c{n}", env=env)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    base = {".dockerignore": API_RULES, "frontend/.dockerignore": "node_modules\n",
            "src/a.py": "1", "frontend/src/x.ts": "1"}
    c1 = _commit(r, base, 1)
    c2 = _commit(r, {"sessions/n.md": "notes"}, 2)  # ignored paths only
    return r, c1, c2


def _run(repo, sha, published, tmp_path):
    out = tmp_path / "out.json"

    def lookup(registry, comp, s):
        return f"sha256:{comp}-{s[:8]}" if (comp, s) in published else None

    rc = ri.main(["--sha", sha, "--out", str(out), "--registry", "ghcr.io/o/r"],
                 lookup=lookup, cwd=repo)
    return rc, json.loads(out.read_text())


def test_ignored_only_commit_keeps_older_build(repo, tmp_path):
    r, c1, c2 = repo
    pub = {("api", c1), ("api", c2), ("ui", c1), ("ui", c2)}
    rc, doc = _run(r, c2, pub, tmp_path)
    assert rc == 0
    assert doc["components"]["api"]["built_from"] == c1
    assert doc["components"]["api"]["image"] == "ghcr.io/o/r/api"
    assert doc["components"]["ui"]["built_from"] == c1


def test_src_change_selects_new_commit(repo, tmp_path):
    r, c1, c2 = repo
    c3 = _commit(r, {"src/a.py": "2"}, 3)
    pub = {("api", c1), ("api", c3), ("ui", c1), ("ui", c3)}
    rc, doc = _run(r, c3, pub, tmp_path)
    assert rc == 0
    assert doc["built_from"] == c3
    assert doc["components"]["api"]["built_from"] == c3
    assert doc["components"]["ui"]["built_from"] == c3  # joint rule: one commit


def test_pair_comes_from_later_commit(repo, tmp_path):
    # ui context last changed at c1, api's at c3; both published at both.
    r, c1, c2 = repo
    c3 = _commit(r, {"src/a.py": "2"}, 3)
    pub = {("api", c1), ("api", c3), ("ui", c1), ("ui", c3)}
    rc, doc = _run(r, c3, pub, tmp_path)
    assert rc == 0
    assert {v["built_from"] for v in doc["components"].values()} == {c3}


def test_pair_not_mixed_when_one_component_unpublished(repo, tmp_path):
    r, c1, c2 = repo
    pub = {("api", c1), ("api", c2), ("ui", c2)}  # ui missing at c1
    rc, doc = _run(r, c2, pub, tmp_path)
    assert rc == 0
    assert doc["built_from"] == c2


def test_unpublished_older_equal_is_skipped(repo, tmp_path):
    r, c1, c2 = repo
    pub = {("api", c2), ("ui", c2)}
    rc, doc = _run(r, c2, pub, tmp_path)
    assert rc == 0
    assert doc["components"]["api"]["built_from"] == c2


def test_none_published_exits_3(repo, tmp_path):
    r, c1, c2 = repo
    rc, doc = _run(r, c2, {("ui", c2)}, tmp_path)
    assert rc == 3
    assert doc["missing"] == ["api"]
