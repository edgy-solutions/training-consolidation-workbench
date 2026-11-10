"""The words a concept goes by: its name, the slides' related terms, its canonical name, aligned synonyms."""
import re
from typing import Dict, List, Optional

_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def _norm(text) -> str:
    return _NON_ALNUM.sub(" ", (text or "").lower()).strip()


def concept_terms(concepts, slides, alignment=None) -> Dict[str, List[str]]:
    """{concept: [concept, related terms, canonical name, synonyms]}, deduped case-insensitively, in that order.

    slides are slide dicts with teaches entries {name, salience, canonical?, related_terms?}."""
    teaches = [t for s in slides for t in (s.get("teaches") or [])]
    out: Dict[str, List[str]] = {}
    for c in concepts:
        raw = [c]
        for t in teaches:
            if t.get("name") == c or t.get("canonical") == c:
                raw.extend(t.get("related_terms") or [])
                if t.get("canonical"):
                    raw.append(t["canonical"])
        if alignment is not None:
            raw.extend(alignment.synonyms([c]))
        seen, terms = set(), []
        for term in raw:
            term = (term or "").strip()
            if term and term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append(term)
        out[c] = terms
    return out


def covered(body: Optional[str], terms) -> bool:
    """True when any term appears in body as whole words (a trailing s or es on the term still counts)."""
    text = _norm(body)
    if not text:
        return False
    padded = f" {text} "
    for term in terms:
        t = _norm(term)
        if t and re.search(rf" {re.escape(t)}(?:e?s)? ", padded):
            return True
    return False
