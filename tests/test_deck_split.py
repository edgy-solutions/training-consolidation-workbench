"""Long bodies and the summary continue on further slides (contract section 2.4)."""
import pytest
import yaml
from pptx import Presentation

from src.publishing.course import (
    Course, DeckExportError, SummaryPart, course_concepts, deck_slides, decks, iter_leaves, more_in_notes,
    sources_body, split_bullets, summary_items,
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


def _course_with(n):
    """The golden course with exactly n distinct concepts, Concept 0.. in course order."""
    course = golden_course()
    leaves = list(iter_leaves(course))
    first = [f"Concept {i}" for i in range(n - len(leaves) + 1)]
    leaves[0].concepts = first
    for i, leaf in enumerate(leaves[1:], start=len(first)):
        leaf.concepts = [f"Concept {i}"]
    return course


def _summaries(course, **kw):
    return [i for r, i in deck_slides(course, **kw) if r == "summary"]


def _lines(part):
    return part.body.splitlines()


def _last_summary(prs):
    return [s for s in prs.slides if s.slide_layout.name == "summary"][-1]


def test_twelve_concepts_make_three_summary_slides_with_no_overflow_line(tmp_path):
    course = _course_with(12)
    assert len(course_concepts(course)) == 12
    summaries = _summaries(course)
    assert [s.title for s in summaries] == ["Summary", "Summary (cont.)", "Summary (cont.)"]
    assert all(isinstance(s, SummaryPart) for s in summaries)
    assert [len(_lines(s)) for s in summaries] == [5, 5, 2]
    assert not any("more in notes" in s.body for s in summaries) and all(s.notes == "" for s in summaries)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []
    slides = list(Presentation(str(out)).slides)
    assert [s.slide_layout.name for s in slides].count("summary") == 3
    assert not any(s.has_notes_slide for s in slides if s.slide_layout.name == "summary")


def test_twenty_eight_concepts_show_twelve_and_the_rest_go_in_the_last_notes(tmp_path):
    course = _course_with(28)
    summaries = _summaries(course)
    assert [len(_lines(s)) for s in summaries] == [5, 5, 3]
    assert _lines(summaries[-1])[-1] == "+16 more in notes"
    assert _lines(summaries[-1])[-2] == "- Concept 11"
    assert [s.notes for s in summaries[:-1]] == ["", ""]
    assert summaries[-1].notes.splitlines() == [f"Concept {i}" for i in range(12, 28)]
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    assert check_round_trip(course, load_mapping(DEFAULT_MAPPING), out) == []
    last = _last_summary(Presentation(str(out)))
    assert last.notes_slide.notes_text_frame.text.splitlines() == [f"Concept {i}" for i in range(12, 28)]


def test_the_overflow_line_follows_the_shown_split():
    summaries = _summaries(_course_with(10), max_summary=7)
    assert [len(_lines(s)) for s in summaries] == [5, 3]
    assert _lines(summaries[1])[-1] == "+3 more in notes"
    assert summaries[1].notes.splitlines() == ["Concept 7", "Concept 8", "Concept 9"]


def test_the_overflow_line_is_not_counted_against_max_bullets():
    summaries = _summaries(_course_with(13), max_summary=10)
    assert [len(_lines(s)) for s in summaries] == [5, 6]
    assert _lines(summaries[1])[-1] == "+3 more in notes"


def test_a_remainder_of_one_reads_plain():
    assert more_in_notes(["a"]) == "+1 more in notes"
    assert more_in_notes(["a", "b"]) == "+2 more in notes"
    assert more_in_notes([]) == ""
    summaries = _summaries(_course_with(13), max_summary=12)
    assert _lines(summaries[-1])[-1] == "+1 more in notes" and summaries[-1].notes == "Concept 12"


def test_summary_items_splits_in_course_order():
    course = _course_with(5)
    assert summary_items(course, 3) == (["Concept 0", "Concept 1", "Concept 2"], ["Concept 3", "Concept 4"])
    assert summary_items(course, 9) == (course_concepts(course), [])


def test_the_round_trip_catches_an_altered_overflow_line(tmp_path):
    course = _course_with(28)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    para = next(p for p in _ph(_last_summary(prs), 1).text_frame.paragraphs if p.text.startswith("+"))
    para.runs[0].text = "+15 more in notes"
    for r in para.runs[1:]:
        r.text = ""
    prs.save(str(tmp_path / "x.pptx"))
    problems = check_round_trip(course, load_mapping(DEFAULT_MAPPING), tmp_path / "x.pptx")
    assert any("the summary slides list" in p for p in problems)


def test_the_round_trip_catches_missing_or_altered_overflow_notes(tmp_path):
    course = _course_with(28)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    for text in ("", "Concept 12\nConcept 13"):
        prs = Presentation(str(out))
        _last_summary(prs).notes_slide.notes_text_frame.text = text
        prs.save(str(tmp_path / "x.pptx"))
        problems = check_round_trip(course, load_mapping(DEFAULT_MAPPING), tmp_path / "x.pptx")
        assert any("last summary slide's notes" in p for p in problems)


def test_notes_on_a_summary_within_the_cap_are_a_problem(tmp_path):
    course = _course_with(12)
    out = export_deck(course, DEFAULT_MAPPING, tmp_path / "o.pptx", resolver())
    prs = Presentation(str(out))
    _last_summary(prs).notes_slide.notes_text_frame.text = "stray"
    prs.save(str(tmp_path / "x.pptx"))
    problems = check_round_trip(course, load_mapping(DEFAULT_MAPPING), tmp_path / "x.pptx")
    assert any("last summary slide's notes" in p for p in problems)


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


def test_the_summary_cap_is_honoured_from_the_mapping(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["max_summary_items"] = 2
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert load_mapping(path).max_summary_items == 2
    out = export_deck(golden_course(), path, tmp_path / "o.pptx", resolver())
    last = _last_summary(Presentation(str(out)))
    assert len(last.notes_slide.notes_text_frame.text.splitlines()) == 3  # five concepts, two shown


def test_an_absent_summary_cap_means_twelve(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("max_summary_items")
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert load_mapping(path).max_summary_items == 12
    assert validate(load_mapping(path), golden_course()) == []


@pytest.mark.parametrize("value", [0, -1, "12", True])
def test_a_bad_summary_cap_is_refused(value):
    mapping = load_mapping(DEFAULT_MAPPING)
    mapping.max_summary_items = value
    assert any(f"max_summary_items must be a whole number of at least 1, got {value!r}" in p
               for p in validate(mapping, golden_course()))


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


def test_the_digest_changes_when_the_summary_cap_changes_what_shows():
    course = _course_with(14)
    assert deck_digest(course, {}, 5, 12) == deck_digest(course, {})
    assert deck_digest(course, {}, 5, 10) != deck_digest(course, {}, 5, 12)


def test_notes_on_a_placeholder_are_refused_because_they_carry_filenames(tmp_path):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["roles"]["concept"]["placeholders"]["notes"] = 2
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(DeckExportError) as e:
        export_deck(golden_course(), path, tmp_path / "out.pptx", resolver())
    assert any("is on the slide face" in p for p in e.value.problems)
