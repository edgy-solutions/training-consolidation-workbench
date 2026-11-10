"""The vocabulary a concept goes by, and whether a text mentions it."""
from src.publishing.concept_terms import concept_terms, covered
from src.workbench.alignment import InMemoryAlignmentStore


def slide(*teaches):
    return {"teaches": list(teaches)}


def test_terms_are_the_name_related_terms_and_canonical_in_order():
    s = slide({"name": "Raw A", "salience": 0.5, "canonical": "Canon A", "related_terms": ["alpha", " beta "]})
    assert concept_terms(["Raw A"], [s])["Raw A"] == ["Raw A", "alpha", "beta", "Canon A"]


def test_an_entry_matches_by_canonical_name_too():
    s = slide({"name": "Raw A", "canonical": "Canon A", "related_terms": ["alpha"]})
    assert concept_terms(["Canon A"], [s])["Canon A"] == ["Canon A", "alpha"]


def test_missing_or_null_related_terms_are_empty_and_other_concepts_are_ignored():
    s = slide({"name": "A", "related_terms": None}, {"name": "B", "related_terms": ["b1"]}, {"name": "C"})
    assert concept_terms(["A", "C"], [s]) == {"A": ["A"], "C": ["C"]}


def test_alignment_synonyms_are_added_and_duplicates_dropped_case_insensitively():
    s = slide({"name": "Pump", "canonical": "Canon", "related_terms": ["PUMP", "", None, "impeller"]})
    store = InMemoryAlignmentStore({"Pump": "Canon", "Pumping unit": "Canon", "canon": "Canon"})
    assert concept_terms(["Pump"], [s], store)["Pump"] == ["Pump", "impeller", "Canon", "Pumping unit"]


def test_covered_ignores_case_and_punctuation():
    assert covered("The **Gear-Pump**, again.", ["gear pump"])
    assert not covered("The gear box", ["gear pump"])


def test_covered_allows_a_plural_on_the_last_word_only():
    assert covered("Two pumps and a valve", ["pump"])
    assert covered("Many gearboxes", ["gearbox"])
    assert not covered("Gears pump", ["gear pump x"])


def test_covered_matches_whole_words():
    assert not covered("A pumpkin", ["pump"])
    assert not covered("Subpump", ["pump"])


def test_covered_is_false_for_an_empty_body_and_true_on_any_term():
    assert not covered("", ["pump"]) and not covered(None, ["pump"]) and not covered("  ", ["pump"])
    assert covered("uses an impeller", ["pump", "impeller"])
    assert not covered("text", [])
