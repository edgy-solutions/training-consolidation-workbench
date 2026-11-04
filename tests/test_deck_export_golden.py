from pptx import Presentation

from src.publishing.deck_export import DEFAULT_MAPPING, check_round_trip, export_deck, load_mapping
from tests.deck_fixtures import golden_course, resolver


def _ph(slide, idx):
    return next(p for p in slide.placeholders if p.placeholder_format.idx == idx)


def _export(tmp_path):
    course = golden_course()
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "out.pptx", resolver())
    return course, Presentation(str(out)), out


def test_golden_export_has_the_eight_slides(tmp_path):
    course, prs, out = _export(tmp_path)
    slides = list(prs.slides)
    assert [s.slide_layout.name for s in slides] == [
        "title", "section", "concept", "concept", "section", "concept-with-figure", "summary", "sources"]
    assert _ph(slides[0], 0).text_frame.text == "Hydraulic Systems (consolidated)"
    assert _ph(slides[0], 1).text_frame.text == "Consolidated from 1 source deck"
    assert _ph(slides[1], 0).text_frame.text == "Hydraulic Principles"
    assert _ph(slides[2], 0).text_frame.text == "Pascal's Law"
    assert _ph(slides[4], 0).text_frame.text == "System Components"
    assert _ph(slides[5], 0).text_frame.text == "Reservoir Schematic"
    assert _ph(slides[5], 1).text_frame.text == "Figure 1: reservoir, filter and pump in series"
    assert [p.text for p in _ph(slides[6], 1).text_frame.paragraphs] == [
        "Pascal's law", "Hydraulic pressure", "Hydraulic pump", "Gear pump", "Hydraulic reservoir"]
    assert _ph(slides[7], 1).text_frame.text == "1 source deck, 4 cited slides"
    assert [ph.placeholder_format.idx for ph in slides[2].placeholders] == [0, 1]  # the citation placeholder is gone
    assert "Stray" not in "".join(p.text_frame.text for s in slides for p in s.placeholders if p.has_text_frame)


def test_golden_pictures_notes_and_round_trip(tmp_path):
    course, prs, out = _export(tmp_path)
    slides = list(prs.slides)
    has_pic = [any(sp.tag.endswith("}pic") for sp in s.shapes._spTree) for s in slides]
    assert has_pic == [False] * 5 + [True] + [False] * 2
    assert slides[2].notes_slide.notes_text_frame.text.splitlines()[-2:] == [
        "Sources: hydraulics_fixture.pptx, slides 1, 2", "Concepts: Pascal's law; Hydraulic pressure"]
    assert slides[3].notes_slide.notes_text_frame.text.splitlines()[-2] == "Source: hydraulics_fixture.pptx, slide 3"
    assert slides[5].notes_slide.notes_text_frame.text.splitlines()[-2] == "Source: hydraulics_fixture.pptx, slide 4"
    assert slides[7].notes_slide.notes_text_frame.text == "hydraulics_fixture.pptx: slides 1, 2, 3, 4"
    assert slides[3].notes_slide.notes_text_frame.text.splitlines()[-1] == "Concepts: Hydraulic pump; Gear pump"
    assert slides[5].notes_slide.notes_text_frame.text.splitlines()[-1] == "Concepts: Hydraulic reservoir"
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []


def test_no_part_file_left_behind(tmp_path):
    _export(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.pptx"]


# ---- repeated concepts, the digest and the deck's recorded properties

import pytest  # noqa: E402

from src.publishing.course import course_concepts, iter_leaves  # noqa: E402
from src.publishing.deck_export import deck_digest  # noqa: E402


def _out(tmp_path, name, course, **kw):
    return export_deck(course, DEFAULT_MAPPING, tmp_path / name, resolver(), **kw)


def _repeating():
    course = golden_course()
    a, b = list(iter_leaves(course))[:2]
    b.concepts = list(b.concepts) + [a.concepts[0]]
    return course


def test_a_repeated_concept_exports_and_round_trips(tmp_path):
    course = _repeating()
    out = _out(tmp_path, "r.pptx", course)
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []
    summary = list(Presentation(str(out)).slides)[-2]
    body = [p.text for ph in summary.placeholders if ph.has_text_frame for p in ph.text_frame.paragraphs if p.text.strip()]
    assert [t for t in body if t in course_concepts(course)] == course_concepts(course)


def test_a_slide_missing_a_concept_still_fails(tmp_path):
    course = _repeating()
    out = _out(tmp_path, "m.pptx", course)
    list(iter_leaves(course))[1].concepts[0] = "Never written"
    assert any("'Never written'" in p for p in check_round_trip(course, load_mapping(DEFAULT_MAPPING), out))


def test_digest_is_stable_changes_with_a_body_and_sits_on_the_deck(tmp_path):
    c1, c2 = golden_course(), golden_course()
    o1, o2 = _out(tmp_path, "1.pptx", c1), _out(tmp_path, "2.pptx", c2)
    assert c1.slides_sha256 == c2.slides_sha256 and len(c1.slides_sha256) == 64
    assert Presentation(str(o1)).core_properties.comments == f"deck_export/1 slides_sha256={c1.slides_sha256}"
    c3 = golden_course()
    list(iter_leaves(c3))[0].body += " changed"
    _out(tmp_path, "3.pptx", c3)
    assert c3.slides_sha256 != c1.slides_sha256


def test_digest_covers_the_picture_bytes():
    course = golden_course()
    fig = next(l for l in iter_leaves(course) if l.figure)
    assert deck_digest(course, {fig.id: b"a"}) != deck_digest(course, {fig.id: b"b"})


def test_render_anyway_is_marked_only_when_set(tmp_path):
    c = golden_course()
    plain = Presentation(str(_out(tmp_path, "p.pptx", c))).core_properties.comments
    marked = Presentation(str(_out(tmp_path, "q.pptx", golden_course(), render_anyway=True))).core_properties.comments
    assert "render_anyway" not in plain
    assert marked == plain + " render_anyway=yes" and len(marked) < 255
