import pytest
import yaml
from pptx import Presentation

from src.publishing.course import DeckExportError
from src.publishing.deck_export import export_deck, load_mapping, mapping_warnings, validate
from tests.deck_fixtures import copy_standin, golden_course, resolver


def _broken(tmp_path, edit):
    path = copy_standin(tmp_path / "tpl")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _fails(tmp_path, mapping_path):
    out = tmp_path / "out.pptx"
    with pytest.raises(DeckExportError) as e:
        export_deck(golden_course(), mapping_path, out, resolver())
    assert not out.exists()
    assert not list(tmp_path.glob("*.part"))
    return e.value.problems


def test_unmapped_role(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"].pop("concept-with-figure")))
    assert "role 'concept-with-figure' is not mapped" in problems


def test_unknown_role(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"].update(
        bogus={"layout": "title", "placeholders": {"title": 0}})))
    assert any("unknown role 'bogus'" in p for p in problems)


def test_unknown_field(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["section"]["placeholders"].update(subtitle=1)))
    assert any("role 'section'" in p and "unknown field 'subtitle'" in p for p in problems)


def test_missing_layout_lists_the_templates_layouts(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["summary"].update(layout="nope")))
    msg = next(p for p in problems if "'nope'" in p)
    for name in ("title", "section", "concept", "concept-with-figure", "summary", "sources"):
        assert name in msg


def test_a_duplicate_layout_name_with_no_index_is_a_warning_not_a_problem(tmp_path):
    path = _broken(tmp_path, lambda d: d["roles"]["section"].update(layout="title"))
    tpl = path.parent / "standin.pptx"
    prs = Presentation(str(tpl))
    prs.slide_layouts.get_by_name("section")._element.cSld.set("name", "title")
    prs.save(str(tpl))
    assert validate(load_mapping(path), golden_course()) == []
    warnings = mapping_warnings(load_mapping(path))
    assert len(warnings) == 2 and all("layout 'title' is carried by 2 layouts" in w for w in warnings)


def test_omitted_notes_go_to_the_notes_page(tmp_path):
    # Contract section 2.2: a concept role that maps no notes field still writes the notes page.
    path = _broken(tmp_path, lambda d: d["roles"]["concept"]["placeholders"].pop("notes"))
    out = tmp_path / "out.pptx"
    export_deck(golden_course(), path, out, resolver())
    slides = list(Presentation(str(out)).slides)
    assert slides[2].notes_slide.notes_text_frame.text.splitlines()[-1] == "Concepts: Pascal's law; Hydraulic pressure"


def test_bad_placeholder_idx(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["concept"]["placeholders"].update(body=9)))
    assert any("role 'concept'" in p and "placeholder 9" in p for p in problems)


def test_image_on_a_placeholder_that_cannot_take_a_picture(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["concept-with-figure"]["placeholders"].update(image=2)))
    assert any("cannot take a picture" in p for p in problems)


def test_required_field_unmapped(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["concept"]["placeholders"].pop("body")))
    assert any("role 'concept'" in p and "required field 'body'" in p for p in problems)


def test_content_with_no_field_to_go_to(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d["roles"]["title"]["placeholders"].pop("body")))
    assert any("role 'title'" in p and "subtitle" in p for p in problems)


def test_wrong_version(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d.update(deck_template=2)))
    assert any("deck_template" in p for p in problems)


def test_missing_version(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d.pop("deck_template")))
    assert any("deck_template" in p for p in problems)


def test_missing_template_file(tmp_path):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d.update(template="nope.pptx")))
    assert any("nope.pptx" in p and "missing" in p for p in problems)


def test_all_problems_are_reported_together(tmp_path):
    def edit(d):
        d["roles"].pop("summary")
        d["roles"]["concept"]["placeholders"].pop("body")
        d["roles"]["section"]["layout"] = "nope"
    problems = _fails(tmp_path, _broken(tmp_path, edit))
    assert len(problems) >= 3


def test_unresolvable_image_writes_nothing(tmp_path):
    from tests.deck_fixtures import copy_standin as cp
    out = tmp_path / "out.pptx"
    with pytest.raises(DeckExportError) as e:
        export_deck(golden_course(), cp(tmp_path / "t"), out, lambda ref: None)
    assert e.value.problems == ["image 'fixture://images/895392accf24--slide_4_img_0.png' on 'Reservoir Schematic' could not be resolved"]
    assert not out.exists()


# ---- max_bullets_per_slide and the retired citation field

@pytest.mark.parametrize("value", [0, -1, "5", True, 2.5])
def test_a_bad_max_bullets_is_refused_without_raising(tmp_path, value):
    problems = _fails(tmp_path, _broken(tmp_path, lambda d: d.update(max_bullets_per_slide=value)))
    assert any("max_bullets_per_slide must be a whole number of at least 1" in p for p in problems)


def test_an_absent_max_bullets_means_five(tmp_path):
    path = _broken(tmp_path, lambda d: d.pop("max_bullets_per_slide", None))
    assert load_mapping(path).max_bullets_per_slide == 5
    assert validate(load_mapping(path), golden_course()) == []


def test_a_mapping_that_still_names_citation_exports_warns_and_drops_the_placeholder(tmp_path):
    def edit(d):
        d["roles"]["concept"]["placeholders"]["citation"] = 2
        d["roles"]["concept-with-figure"]["placeholders"]["citation"] = 9  # the idx is not even checked
    path = _broken(tmp_path, edit)
    warnings = mapping_warnings(load_mapping(path))
    retired = [w for w in warnings if "retired" in w]
    assert len(retired) == 2
    assert ("role 'concept': field 'citation' is retired; citations now go in the speaker notes "
            "and the placeholder is removed from the slide") in retired
    out = tmp_path / "out.pptx"
    export_deck(golden_course(), path, out, resolver())
    slides = list(Presentation(str(out)).slides)
    assert 2 not in [ph.placeholder_format.idx for ph in slides[2].placeholders]
    assert slides[2].notes_slide.notes_text_frame.text.splitlines()[-2].startswith("Sources: ")


def test_the_retired_warning_survives_an_unopenable_template(tmp_path):
    path = _broken(tmp_path, lambda d: (d.update(template="nope.pptx"),
                                        d["roles"]["concept"]["placeholders"].update(citation=2)))
    assert any("'citation' is retired" in w for w in mapping_warnings(load_mapping(path)))


def test_a_different_unknown_field_still_fails_beside_citation(tmp_path):
    def edit(d):
        d["roles"]["concept"]["placeholders"].update(citation=2, footnote=2)
    problems = _fails(tmp_path, _broken(tmp_path, edit))
    assert any("unknown field 'footnote'" in p for p in problems)
    assert not any("unknown field 'citation'" in p for p in problems)


def test_a_saved_role_drops_a_retired_field():
    from src.publishing.template_config import _normalise
    roles = {"concept": {"layout": "concept", "placeholders": {"title": 0, "body": 1, "citation": 2}},
             "section": {"layout": "section", "placeholders": {"title": 0}}}
    out = _normalise(roles)
    assert out["concept"]["placeholders"] == {"title": 0, "body": 1}
    assert out["section"]["placeholders"] == {"title": 0}
