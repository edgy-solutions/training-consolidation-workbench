"""ALIGNS_TO and PROPOSED_ALIGNS_TO run (c:Concept)-[...]->(cc:CanonicalConcept) in every query in src/ (contract section 4.7)."""
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
_PATTERN = re.compile(r"(?=\(([^()]*)\)\s*(<?-)\[([^\]]*)\](->?)\s*\(([^()]*)\))")  # lookahead: chains share nodes


def reversed_patterns(text):
    """Returns (matches on an ALIGNS_TO rel, [reversed pattern text])."""
    seen, bad = 0, []
    for m in _PATTERN.finditer(text):
        left_node, larrow, rel, rarrow, right_node = m.groups()
        if "ALIGNS_TO" not in rel:
            continue
        seen += 1
        if larrow == "<-" and rarrow == "-":
            start, end = right_node, left_node
        else:
            start, end = left_node, right_node
        if ":CanonicalConcept" in start or re.search(r":Concept(?!\w)", end):
            bad.append(f"({left_node}){larrow}[{rel}]{rarrow}({right_node})")
    return seen, bad


def test_no_reversed_pattern_in_src():
    total, bad = 0, []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        seen, found = reversed_patterns(path.read_text(encoding="utf-8"))
        total += seen
        bad += [f"{path.relative_to(SRC.parent).as_posix()}: {b}" for b in found]
    assert total >= 8
    assert bad == []


@pytest.mark.parametrize("text", [
    "(cc:CanonicalConcept)-[:ALIGNS_TO]->(c)",
    "(c:Concept)<-[:ALIGNS_TO]-(cc)",
    "(cc:CanonicalConcept)-[:PROPOSED_ALIGNS_TO]->(c:Concept)",
])
def test_checker_catches_reversed(text):
    assert reversed_patterns(text)[1] != []


@pytest.mark.parametrize("text", [
    "(c)-[:ALIGNS_TO]->(cc:CanonicalConcept)",
    "(cc:CanonicalConcept)<-[:ALIGNS_TO]-(syn:Concept)",
    "(c)-[:ALIGNS_TO]->(cc:CanonicalConcept)<-[:ALIGNS_TO]-(syn:Concept)",
])
def test_checker_passes_correct(text):
    seen, bad = reversed_patterns(text)
    assert seen >= 1 and bad == []
