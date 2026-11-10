"""The concepts view of a section, and removing one concept from one section."""
import pytest

from src.publishing.render import COURSE_NODES_QUERY, PROJECT_QUERY
from src.workbench import section_concepts as sc
from src.workbench.alignment import InMemoryAlignmentStore
from tests.test_render_local import FakeNeo4j, harness  # noqa: F401  (harness is a fixture)

PROJECT = {"id": "proj", "title": "P", "deck_ids": ["d1"]}


def slide(id, number, teaches, filename="a.pptx", deck="d1"):
    return {"id": id, "course_id": deck, "filename": filename, "number": number,
            "teaches": [{"name": n, "salience": 0.5, **({"canonical": c} if c else {})} for n, c in teaches]}


SLIDES = {s["id"]: s for s in [
    slide("s1", 1, [("Raw A", "Canon A"), ("B", None)]),
    slide("s2", 2, [("C", None)]),
    slide("s3", 3, [("Z", None)], filename="b.pptx", deck="d2"),
    slide("s4", 4, [("Z", None)], filename="a.pptx"),
    slide("s5", 5, [("Z", None)], filename="a.pptx"),
    slide("s6", 6, [("Z", None)], filename="a.pptx"),
    slide("s7", 7, [("Z", None)], filename="a.pptx"),
]}


def n(id, parent="proj", order=0, concepts=(), refs=("s1",), role=None, **kw):
    out = {"id": id, "parent_id": parent, "title": id.upper(), "order": order, "content_markdown": "t",
           "key_concepts": list(concepts), "source_refs": list(refs), "is_unassigned": False}
    if role:
        out["section_type"] = role
    return {**out, **kw}


def view(nodes):
    return sc.section_concepts(PROJECT, nodes, SLIDES)


def row(v, node, concept):
    return next(r for r in v[node]["concepts"] if r["concept"] == concept)


def test_a_source_in_the_section_matches_by_name_or_canonical_name():
    v = view([n("a", concepts=["Raw A", "Canon A"])])
    for c in ("Raw A", "Canon A"):
        assert row(v, "a", c)["sources"] == [{"slide_id": "s1", "filename": "a.pptx", "number": 1, "in_section": True}]
    assert v["a"] == {"exported": True, "inherited": False, "concepts": v["a"]["concepts"]}


def test_a_concept_on_none_of_the_sections_slides_points_at_up_to_three_others_in_order():
    r = row(view([n("a", concepts=["Z"])]), "a", "Z")
    assert [(s["filename"], s["number"], s["in_section"]) for s in r["sources"]] == [
        ("a.pptx", 4, False), ("a.pptx", 5, False), ("a.pptx", 6, False)]


def test_a_concept_no_slide_teaches_has_no_sources():
    assert row(view([n("a", concepts=["Nobody teaches this"])]), "a", "Nobody teaches this")["sources"] == []


def test_inherited_concepts_come_from_the_slides_teaches():
    v = view([n("a", concepts=[], refs=["s1", "s2"])])
    assert v["a"]["inherited"] is True
    assert {r["concept"] for r in v["a"]["concepts"]} == {"Raw A", "B", "C"}


def test_a_suggestion_uses_suggested_ids_and_anything_else_source_refs():
    sug = n("a", concepts=["C"], refs=["s1"], status="suggestion", suggested_ids=["s2"])
    assert row(view([sug]), "a", "C")["sources"][0]["in_section"] is True
    plain = n("a", concepts=["C"], refs=["s1"], status="draft", suggested_ids=["s2"])
    assert row(view([plain]), "a", "C")["sources"][0]["in_section"] is False


def test_repeats_overlap_and_revisits():
    v = view([n("a", concepts=["B"]), n("b", order=1, concepts=["B"]),
              n("i", order=2, concepts=["B"], role="introduction"),
              n("q", order=3, concepts=["B"], role="mandatory_assessment")])
    a = row(v, "a", "B")
    assert [r["id"] for r in a["repeated_in"]] == ["b", "i", "q"] and a["overlap"] is True
    assert a["repeated_in"][1] == {"id": "i", "title": "I", "role": "introduction"}
    i = row(v, "i", "B")
    assert [r["id"] for r in i["repeated_in"]] == ["a", "b", "q"] and i["overlap"] is False
    assert row(v, "q", "B")["overlap"] is False


def test_a_repeat_with_only_a_revisiting_section_is_not_an_overlap():
    v = view([n("a", concepts=["B"]), n("i", order=1, concepts=["B"], role="introduction")])
    assert row(v, "a", "B")["repeated_in"][0]["id"] == "i" and row(v, "a", "B")["overlap"] is False


def test_a_parent_is_not_exported_has_no_repeats_and_is_not_counted_by_its_children():
    v = view([n("par", concepts=["B"], refs=[]), n("kid", parent="par", concepts=["B"])])
    assert v["par"]["exported"] is False
    assert row(v, "par", "B")["repeated_in"] == [] and row(v, "par", "B")["overlap"] is False
    assert row(v, "kid", "B")["repeated_in"] == []


def test_unassigned_nodes_are_left_out():
    v = view([n("a", concepts=["B"]), n("u", order=1, concepts=["B"], is_unassigned=True)])
    assert list(v) == ["a"]


# ---- build_view: which decks, which lookup

class StubReader:
    def __init__(self, decks):
        self.decks = decks

    def list_courses(self, _):
        return [{"id": d, "filename": d + ".pptx"} for d in self.decks]

    def course_slides(self, deck):
        return [{"id": s["id"], "number": s["number"]} for s in SLIDES.values() if s["course_id"] == deck]

    def slide(self, sid):
        return {"teaches": [{"concept": t["name"], "salience": 0.5} for t in SLIDES[sid]["teaches"]]}


class Graph:
    def __init__(self, nodes, deck_ids=()):
        self.nodes, self.deck_ids, self.asked, self.writes = nodes, list(deck_ids), [], []

    def execute_query(self, query, params=None):
        if query == PROJECT_QUERY:
            return [{"title": "P", "deck_ids": self.deck_ids}]
        if query == COURSE_NODES_QUERY:
            return self.nodes
        self.asked.append(params["deck"])
        return None


def test_deck_ids_are_the_projects_plus_every_nodes_slide_decks():
    g = Graph([n("a", concepts=["B"], slide_decks=["d1", "dX"])], deck_ids=["d0"])
    sc.build_view("proj", neo4j_client=g, reader=None)
    assert g.asked == ["d0", "d1", "dX"]  # a deck that returns nothing is skipped, not an error


def test_reader_mode_with_no_deck_ids_uses_every_course():
    v = sc.build_view("proj", neo4j_client=Graph([n("a", concepts=["B"])]), reader=StubReader(["d1", "d2"]))
    assert row(v, "a", "B")["sources"][0]["slide_id"] == "s1"
    v = sc.build_view("proj", neo4j_client=Graph([n("a", concepts=["Z"], refs=["s3"])]), reader=StubReader(["d1", "d2"]))
    assert row(v, "a", "Z")["sources"] == [{"slide_id": "s3", "filename": "d2.pptx", "number": 3, "in_section": True}]


def test_reader_mode_uses_the_union_when_it_is_not_empty():
    g = Graph([n("a", concepts=["Z"], refs=["s3"], slide_decks=["d1"])])
    v = sc.build_view("proj", neo4j_client=g, reader=StubReader(["d1", "d2"]))
    assert row(v, "a", "Z")["sources"][0]["in_section"] is False  # d2 was not asked for


# ---- the routes

class Fake(FakeNeo4j):
    def __init__(self):
        super().__init__()
        self.writes = []
        self.owner = True

    def execute_query(self, query, params=None):
        if sc.REMOVE_CONCEPT in query:
            self.writes.append((query, params))
            return []
        if query == sc.PROJECT_OF_NODE:
            return [{"id": self.project["id"]}] if any(x["id"] == params["id"] for x in self.nodes) else []
        if "-[:HAS_CHILD*0..]->(n)" in query and not self.owner:
            return []
        return super().execute_query(query, params)


@pytest.fixture
def api(harness, monkeypatch):  # noqa: F811
    client, _, main = harness
    fake = Fake()
    monkeypatch.setattr(main.neo4j_client, "execute_query", fake.execute_query, raising=False)
    return client, fake


def remove(client, node, concept):
    return client.post("/draft/node/concept/remove", json={"node_id": node, "concept": concept})


def test_get_returns_the_view_and_performs_no_write(api):
    client, fake = api
    r = client.get("/draft/concepts/proj-hydraulics")
    assert r.status_code == 200
    sections = r.json()["sections"]
    assert sections["n-principles"]["exported"] is False and sections["n-pascal"]["exported"] is True
    assert [c["concept"] for c in sections["n-pascal"]["concepts"]] == ["Pascal's law", "Hydraulic pressure"]
    assert sections["n-pumps"]["inherited"] is True
    assert fake.writes == []


def test_remove_writes_the_remainder_to_that_node_only(api):
    client, fake = api
    r = remove(client, "n-pascal", "Pascal's law")
    assert r.status_code == 200 and r.json() == {"node_id": "n-pascal", "concepts": ["Hydraulic pressure"]}
    assert fake.writes == [(sc.REMOVE_CONCEPT, {"id": "n-pascal", "remaining": ["Hydraulic pressure"]})]


def test_remove_makes_an_inherited_list_explicit(api):
    client, fake = api
    listed = [c["concept"] for c in client.get("/draft/concepts/proj-hydraulics").json()["sections"]["n-pumps"]["concepts"]]
    assert len(listed) > 1
    r = remove(client, "n-pumps", listed[0])
    assert r.status_code == 200 and fake.writes[0][1] == {"id": "n-pumps", "remaining": listed[1:]}


def test_remove_unknown_concept_or_node_is_404(api):
    client, fake = api
    assert remove(client, "n-pascal", "Not there").status_code == 404
    assert remove(client, "n-nope", "x").status_code == 404
    assert fake.writes == []


def test_remove_the_last_concept_of_a_leaf_is_409(api):
    client, fake = api
    r = remove(client, "n-reservoir", "Hydraulic reservoir")
    assert r.status_code == 409 and r.json()["detail"] == "A section keeps at least one concept"
    assert fake.writes == []


def test_remove_the_last_concept_of_a_parent_is_allowed(api):
    client, fake = api
    fake.nodes = [{**x, "key_concepts": ["Only"]} if x["id"] == "n-principles" else x for x in fake.nodes]
    r = remove(client, "n-principles", "Only")
    assert r.status_code == 200 and fake.writes[0][1] == {"id": "n-principles", "remaining": []}


def test_remove_by_a_non_owner_is_refused(api):
    # _require_owned answers 404 for "not found" and "not yours" alike
    client, fake = api
    fake.owner = False
    assert remove(client, "n-pascal", "Pascal's law").status_code == 404
    assert fake.writes == []


def test_remove_is_403_while_writes_are_off(api, monkeypatch):
    client, fake = api
    monkeypatch.delenv("WB_STORE_WRITES", raising=False)
    assert remove(client, "n-pascal", "Pascal's law").status_code == 403
    assert fake.writes == []


def test_covered_is_none_without_a_body_or_when_not_exported():
    v = view([n("a", concepts=["B"], content_markdown=" \n"), n("b", order=1, concepts=["B"], content_markdown=None),
              n("p", order=2, concepts=["B"], content_markdown="B here"), n("k", parent="p", concepts=["B"])])
    assert row(v, "a", "B")["covered"] is None and row(v, "b", "B")["covered"] is None
    assert row(v, "p", "B")["covered"] is None


def test_covered_by_name_and_false_when_listed_but_absent():
    v = view([n("a", concepts=["B", "Raw A"], content_markdown="All about b today.")])
    assert row(v, "a", "B")["covered"] is True
    assert row(v, "a", "Raw A")["covered"] is False


def test_covered_through_a_related_term_only():
    s = {**SLIDES["s1"], "teaches": [{"name": "B", "salience": 0.5, "related_terms": ["spur gear"]}]}
    v = sc.section_concepts(PROJECT, [n("a", concepts=["B"], content_markdown="The spur gears mesh.")], {"s1": s})
    assert row(v, "a", "B")["covered"] is True


def test_covered_through_an_alignment_synonym():
    nodes = [n("a", concepts=["B"], content_markdown="The sibling term appears.")]
    assert row(view(nodes), "a", "B")["covered"] is False
    store = InMemoryAlignmentStore({"B": "Canon", "Sibling term": "Canon"})
    v = sc.section_concepts(PROJECT, nodes, SLIDES, store)
    assert row(v, "a", "B")["covered"] is True


def test_alignment_is_asked_once_per_concept_name():
    asked = []

    class Counting(InMemoryAlignmentStore):
        def synonyms(self, names):
            asked.append(tuple(names))
            return super().synonyms(names)

    nodes = [n("a", concepts=["B"], content_markdown="text"), n("b", concepts=["B"], content_markdown="text")]
    sc.section_concepts(PROJECT, nodes, SLIDES, Counting({}))
    assert asked == [("B",)]
