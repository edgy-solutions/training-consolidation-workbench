import pytest

from src.publishing.course import (
    DeckExportError, FixtureImageResolver, MinioImageResolver, ReaderLookup, Section, SourceRef, build_course,
    format_citation, iter_leaves, iter_slides, split_body_and_figure,
)
from tests.deck_fixtures import COURSE_ID, reader

PROJECT = {"id": "p", "title": "P"}


class Lookup:
    def __init__(self, slides):
        self.slides = slides

    def slide(self, sid):
        return self.slides.get(sid)


SLIDES = {
    "s1": {"course_id": "c1", "filename": "a.pptx", "number": 1, "teaches": [
        {"name": "Low", "salience": 0.1}, {"name": "High", "salience": 0.9}, {"name": "None", "salience": None}]},
    "s2": {"course_id": "c1", "filename": "a.pptx", "number": 2, "teaches": [{"name": "Two", "salience": 0.5}]},
    "s3": {"course_id": "c2", "filename": "b.pptx", "number": 7, "teaches": [{"name": "Three", "salience": 0.5}]},
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


def test_duplicate_concept_names_both_leaves():
    p = problems([node("first", concepts=["dup"]), node("second", order=1, concepts=["dup"])])
    assert len(p) == 1 and "'dup'" in p[0] and "'first'" in p[0] and "'second'" in p[0]


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
    s = ReaderLookup(reader()).slide(COURSE_ID + "_p3")
    assert s["filename"] == "hydraulics_fixture.pptx" and s["number"] == 3
    assert [t["name"] for t in s["teaches"]] == ["Hydraulic pump", "Gear pump"]
    assert ReaderLookup(reader()).slide("missing") is None


def test_fixture_image_resolver_forms():
    r = FixtureImageResolver(reader())
    a = r("fixture://images/slide_4_img_0.png")
    assert a and a == r("/source/fixture-asset/slide_4_img_0.png") == r("x/y/images/slide_4_img_0.png")
    assert a == r("slide_4_img_0")
    assert r("fixture://images/unknown.png") is None


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
    r = MinioImageResolver(m, "bkt")
    key = "training/generated/abc/1.0/images/slide_4_img_0.png"
    assert r(key) == b"img"
    assert r("/" + key) == b"img"
    assert r(f"http://host:9000/bkt/{key}?X-Amz-Signature=abc&X-Amz-Expires=3600") == b"img"
    assert {k for _, k in m.asked} == {key}
    assert r("training/generated/abc/1.0/images/missing.png") is None
    assert r("slide_4_img_0") is None
