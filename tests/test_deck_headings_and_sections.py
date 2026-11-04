"""Headings never read as bullets, and a section shows its own body or is skipped and recorded (contract sections 2.3, 2.4, 3.2)."""
import json

import yaml
from pptx import Presentation

from src.publishing import deck_template
from src.publishing.course import (
    ReaderLookup, Section, build_course, deck_slides, drop_repeated_title, iter_leaves, skipped_sections,
)
from src.publishing.deck_export import (
    DEFAULT_MAPPING, check_round_trip, deck_digest, export_deck, load_mapping, mapping_warnings, write_text,
)
from tests.deck_fixtures import copy_standin, course_data, golden_course, reader, resolver
from tests.test_render_gate import OVERRIDE, Neo, render

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
LONG = "\n".join(f"- point {i}" for i in range(1, 9))


def _sections(course):
    return [c for c in course.children if isinstance(c, Section)]


def _slides_of(prs, layout):
    return [s for s in prs.slides if s.slide_layout.name == layout]


def _body(slide):
    return next(p for p in slide.placeholders if p.placeholder_format.idx == 1)


def _no_section_body(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["roles"]["section"]["placeholders"] = {"title": 0}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _blank_section(course, i=1):
    _sections(course)[i].body = ""
    return course


# ---- headings

def test_a_heading_is_a_bold_level_zero_paragraph_without_a_bullet():
    prs = Presentation(str(DEFAULT_MAPPING.parent / "standin.pptx"))
    slide = prs.slides.add_slide(next(l for l in prs.slide_layouts if l.name == "concept"))
    frame = _body(slide).text_frame
    write_text(frame, "## Head **x**\n  - nested\n- plain")
    head, nested, plain = frame.paragraphs
    pPr = head._p.pPr
    assert pPr.find(A + "buNone") is not None and pPr.get("marL") == "0" and pPr.get("indent") == "0"
    assert head.level == 0 and head.text == "Head x" and all(r.font.bold for r in head.runs)
    assert nested.level == 1
    for p in (nested, plain):
        assert p._p.pPr is None or p._p.pPr.find(A + "buNone") is None
    assert not any(r.font.bold for r in plain.runs)


def test_a_leading_heading_equal_to_the_title_is_dropped():
    assert drop_repeated_title("Pascal's Law", "#  pascal's   LAW\n- a\n- b") == "- a\n- b"
    assert drop_repeated_title("T", "\n\n## T\n- a") == "\n\n- a"


def test_a_different_heading_or_a_lone_heading_is_kept():
    body = "# Other\n- a"
    assert drop_repeated_title("T", body) == body
    assert drop_repeated_title("T", "# T") == "# T"
    assert drop_repeated_title("T", "- a\n# T") == "- a\n# T"
    assert drop_repeated_title("T", "") == ""


def test_the_heading_is_dropped_once_and_before_splitting():
    course = golden_course()
    leaf = next(iter_leaves(course))
    leaf.body = f"# {leaf.title.upper()}\n{LONG}\n# {leaf.title}"
    parts = [i for r, i in deck_slides(course, 5) if getattr(i, "id", None) == leaf.id]
    assert [p.body for p in parts] == ["\n".join(f"- point {i}" for i in range(1, 6)),
                                       "\n".join(f"- point {i}" for i in range(6, 9)) + f"\n# {leaf.title}"]
    assert [p.title for p in parts] == [leaf.title, leaf.title + " (cont.)"]


# ---- the course carries a parent's body

def test_build_course_carries_the_parents_body_and_ignores_images():
    d = course_data()
    for n in d["nodes"]:
        if n["id"] == "n-components":
            n["content_markdown"] = "- text\n![alt](gone.png)"
    course = build_course(d["project"], d["nodes"], ReaderLookup(reader()))
    assert [s.body for s in _sections(course)] == ["- Hydraulic systems transmit force through a confined fluid\n"
                                                   "- Pressure and area set the force a piston delivers", "- text"]


# ---- sections render

def test_a_section_body_renders_and_passes_the_round_trip(tmp_path):
    out = export_deck(golden_course(), DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    sections = _slides_of(prs, "section")
    assert len(sections) == 2 and len(prs.slides) == 8
    assert "confined fluid" in _body(sections[0]).text_frame.text
    assert check_round_trip(golden_course(), load_mapping(DEFAULT_MAPPING), out) == []


def test_a_long_section_body_continues_as_section_slides(tmp_path):
    course = golden_course()
    _sections(course)[0].body = LONG
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    titles = [s.shapes.title.text_frame.text for s in _slides_of(prs, "section")]
    assert titles == ["Hydraulic Principles", "Hydraulic Principles (cont.)", "System Components"]
    assert [r for r, _ in deck_slides(course)].count("section") == 3
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []


def test_a_section_without_a_body_gets_no_slide_and_its_children_still_render(tmp_path):
    course = _blank_section(golden_course(), 0)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    assert len(_slides_of(prs, "section")) == 1 and len(prs.slides) == 7
    assert "Pascal's Law" in [s.shapes.title.text_frame.text for s in prs.slides]
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []


def test_a_mapping_without_a_section_body_skips_sections_and_warns(tmp_path):
    path = _no_section_body(tmp_path)
    mapping = load_mapping(path)
    assert not mapping.section_body and load_mapping(DEFAULT_MAPPING).section_body
    assert any("section" in w and "skipped" in w and "no 'body'" in w for w in mapping_warnings(mapping))
    assert not any("skipped" in w for w in mapping_warnings(load_mapping(DEFAULT_MAPPING)))
    course = golden_course()
    assert all(s.body for s in _sections(course))
    out = export_deck(course, path, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    assert _slides_of(prs, "section") == [] and len(prs.slides) == 6
    assert check_round_trip(course, mapping, out) == []


def test_skipped_sections():
    course = golden_course()
    assert skipped_sections(course) == []
    assert skipped_sections(course, section_body=False) == [
        {"id": "n-principles", "title": "Hydraulic Principles"}, {"id": "n-components", "title": "System Components"}]
    _blank_section(course, 1)
    assert skipped_sections(course) == [{"id": "n-components", "title": "System Components"}]


def test_the_digest_differs_with_and_without_section_bodies():
    course, images = golden_course(), {}
    assert deck_digest(course, images) != deck_digest(course, images, section_body=False)
    _blank_section(_blank_section(course, 0), 1)
    assert deck_digest(course, images) == deck_digest(course, images, section_body=False)


# ---- the render record

def _records(fake):
    return [json.loads(w["entry"]) for w in fake.writes if w["id"] == "proj-hydraulics"]


def _blank_parent(fake, node_id="n-components"):
    fake.nodes = [{**n, "content_markdown": ""} if n["id"] == node_id else n for n in fake.nodes]
    return fake


def test_a_skip_writes_a_record_without_an_override(tmp_path):
    fake = _blank_parent(Neo())
    render(fake, tmp_path / "d.pptx")
    (entry,) = _records(fake)
    assert entry["skipped_sections"] == [{"id": "n-components", "title": "System Components"}]
    assert entry["reason"] is None and entry["by"] is None and entry["at"] is None
    assert entry["overlaps"] == [] and entry["filename"] == "d.pptx" and entry["slides_sha256"]
    assert "render_anyway" not in Presentation(str(tmp_path / "d.pptx")).core_properties.comments


def test_nothing_skipped_and_no_overlap_writes_nothing(tmp_path):
    fake = Neo()
    render(fake, tmp_path / "d.pptx")
    assert fake.writes == []


def test_an_override_with_skips_records_both(tmp_path):
    fake = _blank_parent(Neo())
    fake.nodes = [{**n, "key_concepts": ["Hydraulic reservoir", "Pascal's law"]} if n["id"] == "n-reservoir" else n
                  for n in fake.nodes]
    render(fake, tmp_path / "d.pptx", override=OVERRIDE)
    (entry,) = _records(fake)
    assert (entry["reason"], entry["by"], entry["at"]) == (OVERRIDE["reason"], OVERRIDE["by"], OVERRIDE["at"])
    assert entry["overlaps"] and entry["skipped_sections"] == [{"id": "n-components", "title": "System Components"}]


def test_a_mapping_without_a_section_body_records_every_section(tmp_path, monkeypatch):
    path = _no_section_body(tmp_path)
    monkeypatch.setattr(deck_template, "configured_mapping", lambda *a, **k: path)
    fake = Neo()
    render(fake, tmp_path / "d.pptx")
    (entry,) = _records(fake)
    assert [s["id"] for s in entry["skipped_sections"]] == ["n-principles", "n-components"]
