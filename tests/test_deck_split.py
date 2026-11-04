"""Long bodies and the summary continue on further slides (contract section 2.4)."""
import pytest
import yaml
from pptx import Presentation

from src.publishing.course import (
    Course, DeckExportError, SummaryPart, deck_slides, decks, iter_leaves, sources_body, split_bullets,
)
from src.publishing.deck_export import (
    DEFAULT_MAPPING, check_round_trip, deck_digest, export_deck, load_mapping, validate,
)
from tests.deck_fixtures import copy_standin, golden_course, resolver

BULLETS = "\n".join(f"- point {i}" for i in range(1, 9))
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _ph(slide, idx):
    return next(p for p in slide.placeholders if p.placeholder_format.idx == idx)


def test_split_at_the_limit_returns_the_exact_body():
    body = "- a\n- b\n\n- c  \n"
    assert split_bullets(body, 3) == [body]
    assert split_bullets("", 3) == [""]


def test_headings_are_uncounted_and_stay_with_what_follows():
    body = "# One\n- a\n- b\n# Two\n- c\n- d"
    assert split_bullets(body, 2) == ["# One\n- a\n- b", "# Two\n- c\n- d"]
    assert split_bullets("# Only\n- a\n- b", 2) == ["# Only\n- a\n- b"]
    assert split_bullets("- a\n- b\n- c\n# Tail", 2) == ["- a\n- b", "- c\n# Tail"]


def test_a_nested_bullet_stays_with_its_parent_across_a_split():
    body = "- a\n  - a1\n- b\n  - b1\n- c"
    assert split_bullets(body, 3) == ["- a\n  - a1", "- b\n  - b1\n- c"]


def test_an_oversized_block_is_cut_by_line():
    body = "- a\n  - a1\n  - a2\n  - a3\n  - a4"
    assert split_bullets(body, 2) == ["- a\n  - a1", "  - a2\n  - a3", "  - a4"]


def test_max_one():
    assert split_bullets("- a\n- b\n- c", 1) == ["- a", "- b", "- c"]


def test_a_continuation_keeps_the_leafs_identity_but_not_its_figure_or_notes():
    course = golden_course()
    leaf = next(l for l in iter_leaves(course) if l.figure)
    leaf.notes = "Say this."
    leaf.body = BULLETS
    parts = [(r, i) for r, i in deck_slides(course) if getattr(i, "id", None) == leaf.id]
    assert [r for r, _ in parts] == ["concept-with-figure", "concept"]
    first, cont = parts[0][1], parts[1][1]
    assert first.title == leaf.title and cont.title == leaf.title + " (cont.)"
    assert first.figure and first.notes == "Say this."
    assert cont.figure is None and cont.notes == ""
    assert first.concepts == cont.concepts == leaf.concepts
    assert first.sources == cont.sources == leaf.sources
    assert first.body.count("\n") == 4 and cont.body.count("\n") == 2


def test_a_figure_leafs_continuation_needs_the_concept_role():
    course = golden_course()
    leaf = next(l for l in iter_leaves(course) if l.figure)
    only = Course("t", [leaf])
    mapping = load_mapping(DEFAULT_MAPPING)
    del mapping.roles["concept"]
    assert validate(mapping, only) == []
    leaf.body = BULLETS
    assert validate(mapping, only) == ["role 'concept' is not mapped"]


def test_twelve_concepts_make_three_summary_slides_that_round_trip(tmp_path):
    course = golden_course()
    list(iter_leaves(course))[0].concepts = [f"Concept {i}" for i in range(12)]
    summaries = [i for r, i in deck_slides(course) if r == "summary"]
    assert [s.title for s in summaries] == ["Summary", "Summary (cont.)", "Summary (cont.)"]
    assert all(isinstance(s, SummaryPart) for s in summaries)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []
    assert [s.slide_layout.name for s in Presentation(str(out)).slides].count("summary") == 3


def test_a_long_body_continues_and_an_unsplit_body_is_unchanged(tmp_path):
    plain = export_deck(golden_course(), DEFAULT_MAPPING, tmp_path / "a.pptx", resolver())
    course = golden_course()
    list(iter_leaves(course))[0].body = BULLETS
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "b.pptx", resolver())
    slides = list(Presentation(str(out)).slides)
    old = list(Presentation(str(plain)).slides)
    assert len(slides) == 9 and len(old) == 8
    assert _ph(slides[3], 0).text_frame.text == "Pascal's Law (cont.)"
    assert [p.text for p in _ph(slides[3], 1).text_frame.paragraphs] == ["point 6", "point 7", "point 8"]
    assert slides[3].notes_slide.notes_text_frame.text.splitlines()[-2].startswith("Sources: ")
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []
    assert _ph(old[3], 1).text_frame.text == _ph(slides[4], 1).text_frame.text  # the second leaf, untouched


def test_the_mapping_value_is_honoured(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["max_bullets_per_slide"] = 2
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    out = export_deck(golden_course(), path, tmp_path / "o.pptx", resolver())
    layouts = [s.slide_layout.name for s in Presentation(str(out)).slides]
    assert layouts.count("summary") == 3  # five concepts, two to a slide


def test_the_face_holds_no_filename_and_the_citation_sits_before_concepts(tmp_path):
    course = golden_course()
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    slides = list(Presentation(str(out)).slides)
    names = [d["filename"] for d in decks(course)]
    for s in slides:
        face = " ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame)
        assert not any(n in face for n in names)
    assert _ph(slides[-1], 1).text_frame.text == sources_body(course)
    assert slides[-1].notes_slide.notes_text_frame.text.splitlines() == ["hydraulics_fixture.pptx: slides 1, 2, 3, 4"]
    lines = slides[2].notes_slide.notes_text_frame.text.splitlines()
    assert lines[-2].startswith("Sources: ") and lines[-1].startswith("Concepts:")


def test_a_body_placeholder_shrinks_text_on_overflow(tmp_path):
    out = export_deck(golden_course(), DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    slide = list(Presentation(str(out)).slides)[2]
    assert _ph(slide, 1).text_frame._txBody.bodyPr.find(A + "normAutofit") is not None
    assert _ph(slide, 0).text_frame._txBody.bodyPr.find(A + "normAutofit") is None


def test_the_digest_changes_when_the_limit_changes_the_split():
    course = golden_course()
    assert deck_digest(course, {}, 5) == deck_digest(course, {})
    assert deck_digest(course, {}, 2) != deck_digest(course, {}, 5)


def test_notes_on_a_placeholder_are_refused_because_they_carry_filenames(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["roles"]["concept"]["placeholders"]["notes"] = 2
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(DeckExportError) as e:
        export_deck(golden_course(), path, tmp_path / "out.pptx", resolver())
    assert any("is on the slide face" in p for p in e.value.problems)
