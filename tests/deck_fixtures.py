"""Shared builders for the deck export tests."""
import json
import shutil
from pathlib import Path

from src.publishing.course import FixtureImageResolver, ReaderLookup, build_course
from src.workbench.fixture_reader import FixtureReader

ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "fixtures" / "training"
COURSE_JSON = ROOT / "fixtures" / "export" / "hydraulics-course.json"
STANDIN_DIR = ROOT / "fixtures" / "templates" / "standin"
COURSE_ID = json.loads((FIXTURE_DIR / "golden.json").read_text(encoding="utf-8"))["neo4j"]["course"]["props"]["id"]


def reader():
    return FixtureReader(FIXTURE_DIR)


def course_data():
    return json.loads(COURSE_JSON.read_text(encoding="utf-8"))


def golden_course():
    d = course_data()
    return build_course(d["project"], d["nodes"], ReaderLookup(reader()))


def resolver():
    return FixtureImageResolver(reader())


def copy_standin(dest):
    """A writable copy of the stand-in template folder; returns the mapping path."""
    dest = Path(dest)
    shutil.copytree(STANDIN_DIR, dest, ignore=shutil.ignore_patterns("make_standin.py", "__pycache__"))
    return dest / "deck-template.yaml"
