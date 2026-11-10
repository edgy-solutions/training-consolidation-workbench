import pytest

from src.publishing.image_ids import ImageRefError

from src.publishing.course import (
    DeckExportError, FixtureImageResolver, MinioImageResolver, ReaderLookup, Section, SourceRef, build_course,
    course_concepts, format_citation, iter_leaves, iter_slides, split_body_and_figure,
)
from tests.deck_fixtures import COURSE_ID, image_id, reader

PROJECT = {"id": "p", "title": "P", "deck_ids": ["c1", "c2"]}


class Lookup:
    def __init__(self, slides):
        self.slides = slides

    def deck_slides(self, deck_id):
        found = [s for s in self.slides.values() if s["course_id"] == deck_id]
        return found or None


SLIDES = {
    "s1": {"id": "s1", "course_id": "c1", "filename": "a.pptx", "number": 1, "teaches": [
        {"name": "Low", "salience": 0.1}, {"name": "High", "salience": 0.9}, {"name": "None", "salience": None}]},
    "s2": {"id": "s2", "course_id": "c1", "filename": "a.pptx", "number": 2, "teaches": [{"name": "Two", "salience": 0.5}]},
    "s3": {"id": "s3", "course_id": "c2", "filename": "b.pptx", "number": 7, "teaches": [{"name": "Three", "salience": 0.5}]},
}


def node(id, parent="p", order=0, title=None, body="text", concepts=None, sources=("s1",), unassigned=False):
    return {"id": id, "parent_id": parent, "title": title or id, "order": order, "content_markdown": body,
            "key_concepts": [f"c-{id}"] if concepts is None else list(concepts), "source_refs": list(sources), "is_unassigned": unassigned}


def build(nodes):
    return build_course(PROJECT, nodes, Lookup(SLIDES))


def problems(nodes):
    with pytest.raises(DeckExportError) as e:
        build(nodes)
    return e.value.problems


def titles(course):
    return [(r, getattr(i, "title", None)) for r, i in iter_slides(course)][1:-2]


def test_order_none_after_ordered_and_id_tiebreak():
    c = build([
        node("z", order=None, concepts=["cz"]), node("a", order=None, concepts=["ca"]),
        node("m", order=5, concepts=["cm"]), node("n", order=1, concepts=["cn"])])
    assert [l.id for l in iter_leaves(c)] == ["n", "m", "a", "z"]


def test_section_comes_before_descendants_and_nesting():
    c = build([
        node("sec", order=0), node("leaf1", parent="sec", order=1, concepts=["c1"]),
        node("sub", parent="sec", order=2), node("leaf2", parent="sub", order=1, concepts=["c2"]),
        node("top", order=1, concepts=["c3"])])
    assert titles(c) == [("section", "sec"), ("concept", "leaf1"), ("section", "sub"), ("concept", "leaf2"),
                         ("concept", "top")]
    assert isinstance(c.children[0], Section) and isinstance(c.children[0].children[1], Section)


def test_unassigned_subtree_is_dropped_without_failing():
    c = build([
        node("keep", concepts=["k"]),
        node("un", order=1, unassigned=True, sources=[], concepts=[]),
        node("stray", parent="un", sources=[], concepts=["s"], body="")])
    assert [l.id for l in iter_leaves(c)] == ["keep"]


def test_concepts_fall_back_to_teaches_by_salience():
    c = build([node("a", concepts=[])])
    assert next(iter_leaves(c)).concepts == ["High", "Low", "None"]


def test_a_repeated_concept_does_not_stop_the_build():
    c = build([node("first", concepts=["dup"]), node("second", order=1, concepts=["dup"])])
    assert [l.concepts for l in iter_leaves(c)] == [["dup"], ["dup"]]
    assert course_concepts(c) == ["dup"]


def test_empty_body():
    assert any("body is empty" in p for p in problems([node("a", body="  \n ")]))
    assert any("body is empty" in p for p in problems([node("a", body="![x](fixture://images/i.png)")]))


def test_no_sources_and_no_concepts():
    p = problems([node("a", sources=[], concepts=[])])
    assert any("no source slides" in x for x in p) and any("no concepts" in x for x in p)


def test_unknown_source_slide():
    assert any("'nope'" in p for p in problems([node("a", sources=["nope"])]))


def test_two_image_references_fail():
    p = problems([node("a", body="t ![a](x/images/1.png) and {{slide_1_img_0}}")])
    assert any("2 image references" in x for x in p)


def test_all_problems_collected():
    assert len(problems([node("a", body=""), node("b", order=1, sources=["nope"], concepts=["q"])])) == 2


def test_image_markup_forms_are_recognised_and_stripped():
    body, refs = split_body_and_figure("Intro\n\n![alt text](fixture://images/a.png)")
    assert (body, refs) == ("Intro", ["fixture://images/a.png"])
    body, refs = split_body_and_figure("{{slide_4_img_0}}\nAfter")
    assert (body, refs) == ("After", ["slide_4_img_0"])
    c = build([node("a", body="Words\n![x](fixture://images/a.png)")])
    leaf = next(iter_leaves(c))
    assert leaf.body == "Words" and leaf.figure.ref == "fixture://images/a.png"
    assert [r for r, _ in iter_slides(c)][1] == "concept-with-figure"


def test_citation_one_slide():
    assert format_citation([SourceRef("c1", "a.pptx", 3, "x")]) == "Source: a.pptx, slide 3"


def test_citation_two_decks_orders_by_first_citation_and_ascending_slides():
    srcs = [SourceRef("c2", "b.pptx", 7, "s3"), SourceRef("c1", "a.pptx", 2, "s2"), SourceRef("c1", "a.pptx", 1, "s1")]
    assert format_citation(srcs) == "Sources: b.pptx, slide 7; a.pptx, slides 1, 2"


def test_citation_one_deck_several_slides():
    srcs = [SourceRef("c1", "a.pptx", 4, "x"), SourceRef("c1", "a.pptx", 2, "y")]
    assert format_citation(srcs) == "Sources: a.pptx, slides 2, 4"


def test_reader_lookup_shape():
    slides = {s["id"]: s for s in ReaderLookup(reader()).deck_slides(COURSE_ID)}
    s = slides[COURSE_ID + "_p3"]
    assert s["filename"] == "hydraulics_fixture.pptx" and s["number"] == 3
    assert [t["name"] for t in s["teaches"]] == ["Hydraulic pump", "Gear pump"]
    assert ReaderLookup(reader()).deck_slides("missing") is None


def test_reader_lookup_carries_related_terms_and_defaults_to_none_listed():
    slides = {s["id"]: s for s in ReaderLookup(reader()).deck_slides(COURSE_ID)}
    assert all(isinstance(t["related_terms"], list) for s in slides.values() for t in s["teaches"])


def test_fixture_image_resolver_forms():
    r = FixtureImageResolver(reader(), [COURSE_ID])
    n = image_id("slide_4_img_0")
    a = r("fixture://images/" + n + ".png")
    assert a and a == r("/source/fixture-asset/" + n + ".png") == r("x/y/images/" + n + ".png")
    assert a == r(n)
    assert r("fixture://images/" + image_id("unknown") + ".png") is None


class _Obj:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def close(self):
        pass

    release_conn = close


class _Minio:
    def __init__(self):
        self.asked = []

    def get_object(self, bucket, key):
        self.asked.append((bucket, key))
        if "missing" in key:
            raise KeyError(key)
        return _Obj(b"img")


def test_minio_resolver_forms():
    m = _Minio()
    r = MinioImageResolver(m, "bkt", [COURSE_ID])
    key = "training/generated/abc/1.0/images/slide_4_img_0.png"
    assert r(key) == b"img"
    assert r("/" + key) == b"img"
    assert r(f"http://host:9000/bkt/{key}?X-Amz-Signature=abc&X-Amz-Expires=3600") == b"img"
    assert {k for _, k in m.asked} == {key}
    assert r("training/generated/abc/1.0/images/missing.png") is None
    with pytest.raises(ImageRefError, match="carries no deck prefix"):
        r("slide_4_img_0")


# ---- roles, overlaps, unfinished sections, summary

from src.publishing.course import concept_overlaps, effective_concepts, unfinished_sections  # noqa: E402


def top(id, role=None, order=0):
    n = node(id, order=order, concepts=[])
    if role:
        n["section_type"] = role
    return n


def leaf_under(id, parent, concepts, order=0, role=None):
    n = node(id, parent=parent, order=order, concepts=concepts)
    if role:
        n["section_type"] = role
    return n


def overlaps(nodes):
    return {o["concept"]: [s["id"] for s in o["sections"]] for o in concept_overlaps(build(nodes))}


def test_role_comes_from_the_top_level_ancestor():
    c = build([top("t", "mandatory_safety"), leaf_under("a", "t", ["x"]),
               leaf_under("b", "a2", ["y"], order=1), top("a2", "introduction", order=1)])
    # a2 has a child, so it is a section; b inherits introduction; a inherits mandatory_safety
    roles = {l.id: l.role for l in iter_leaves(c)}
    assert roles == {"a": "mandatory_safety", "b": "introduction"}


def test_a_child_does_not_use_its_own_section_type():
    c = build([top("t", "introduction"), leaf_under("a", "t", ["x"], role="technical")])
    assert next(iter_leaves(c)).role == "introduction"


def test_missing_role_is_technical():
    assert next(iter_leaves(build([node("a")]))).role == "technical"


@pytest.mark.parametrize("role", ["introduction", "mandatory_safety", "mandatory_assessment"])
def test_repeat_with_a_revisiting_section_is_silent(role):
    assert overlaps([node("a", concepts=["x"]), node("b", order=1, concepts=["x"]) | {"section_type": role}]) == {}


@pytest.mark.parametrize("role", [None, "technical", "something_new"])
def test_two_concept_role_leaves_overlap(role):
    b = node("b", order=1, concepts=["x"])
    if role:
        b["section_type"] = role
    assert overlaps([node("a", concepts=["x"]), b]) == {"x": ["a", "b"]}


def test_introduction_plus_two_technical_lists_only_the_technical_ones():
    got = overlaps([node("i", concepts=["x"]) | {"section_type": "introduction"},
                    node("a", order=1, concepts=["x"]), node("b", order=2, concepts=["x"])])
    assert got == {"x": ["a", "b"]}


def test_a_repeat_on_a_parent_does_not_count():
    nodes = [node("par", concepts=["x"]), leaf_under("a", "par", ["x"]), node("b", order=1, concepts=["y"])]
    assert overlaps(nodes) == {}


def test_unassigned_is_skipped_by_overlaps_and_unfinished():
    nodes = [node("a", concepts=["x"]), node("u", order=1, concepts=["x"], unassigned=True, sources=[], body="")]
    assert overlaps(nodes) == {}
    assert unfinished_sections(PROJECT, nodes) == ([], 1)


def test_build_still_raises_on_an_empty_body_but_not_on_a_repeat():
    nodes = [node("a", concepts=["x"]), node("b", order=1, concepts=["x"], body="")]
    p = problems(nodes)
    assert len(p) == 1 and "body is empty" in p[0]


def test_summary_lists_a_repeated_concept_once_in_first_order():
    c = build([node("a", concepts=["x", "y"]), node("b", order=1, concepts=["z", "x"])])
    assert course_concepts(c) == ["x", "y", "z"]


def test_unfinished_counts_missing_sources_and_empty_bodies():
    nodes = [node("sec"), leaf_under("ok", "sec", ["x"]), leaf_under("nosrc", "sec", ["y"], order=1) | {"source_refs": []},
             leaf_under("nobody", "sec", ["z"], order=2) | {"content_markdown": "![i](a/images/1.png)"}]
    unfinished, total = unfinished_sections(PROJECT, nodes)
    assert total == 3 and [u["id"] for u in unfinished] == ["nosrc", "nobody"]
    assert unfinished[0] == {"id": "nosrc", "title": "nosrc"}


def test_effective_concepts_reports_where_they_came_from():
    assert effective_concepts({"key_concepts": ["a", "a", "b"]}, []) == (["a", "b"], False)
    assert effective_concepts({"key_concepts": []}, [SLIDES["s1"], SLIDES["s2"]]) == (["High", "Two", "Low", "None"], True)
