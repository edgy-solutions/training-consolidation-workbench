"""The vendored training-workbench contract and fixture match doc-tools' pins.

doc-tools/lane/tr owns these files; this repo carries byte-identical copies.
A drifted copy fails here instead of silently testing against the wrong golden.
"""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "training"
VENDORED = json.loads((FIXTURE_DIR / "VENDORED.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((FIXTURE_DIR / "golden.json").read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("rel_path", sorted(VENDORED["files"]))
def test_vendored_file_matches_pin(rel_path):
    assert sha256_of(ROOT / rel_path) == VENDORED["files"][rel_path]


def test_golden_pins_the_vendored_deck_and_sidecar():
    fixture = GOLDEN["fixture"]
    assert sha256_of(FIXTURE_DIR / fixture["deck"]) == fixture["deck_sha256"]
    assert sha256_of(FIXTURE_DIR / fixture["metadata"]) == fixture["metadata_sha256"]


def test_contract_version_matches_golden():
    assert GOLDEN["contract_version"] == VENDORED["contract_version"]


def test_course_id_is_the_deck_ingest_id():
    assert GOLDEN["ingest_id"] == "sha256:" + GOLDEN["fixture"]["deck_sha256"]


CASE_DIRS = sorted(p for p in FIXTURE_DIR.iterdir() if (p / "golden.json").is_file())


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=lambda p: p.name)
def test_case_golden_pins_its_deck_and_sidecar(case_dir):
    golden = json.loads((case_dir / "golden.json").read_text(encoding="utf-8"))
    fixture = golden["fixture"]
    assert golden["contract_version"] == VENDORED["contract_version"]
    assert golden["ingest_id"] == "sha256:" + fixture["deck_sha256"]
    assert sha256_of(case_dir / fixture["deck"]) == fixture["deck_sha256"]
    # empty-no-metadata ships no sidecar: both fields are null.
    if fixture["metadata"] is None:
        assert fixture["metadata_sha256"] is None
    else:
        assert sha256_of(case_dir / fixture["metadata"]) == fixture["metadata_sha256"]
