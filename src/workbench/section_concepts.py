"""The concepts each section carries, where they come from, and where else they are taught."""
from typing import Dict, List

from src.publishing.concept_terms import concept_terms, covered
from src.publishing.course import (
    REVISITING_ROLES, GraphLookup, ReaderLookup, effective_concepts, outline,
)
from src.publishing.render import PROJECT_QUERY, fetch_course_nodes

MAX_FALLBACK_SOURCES = 3

PROJECT_OF_NODE = """
MATCH (p:Project)-[:HAS_CHILD*]->(n:TargetNode {id: $id})
RETURN p.id AS id LIMIT 1
"""

REMOVE_CONCEPT = "MATCH (t:TargetNode {id:$id}) SET t.key_concepts = $remaining"


def _teaches(slide, concept):
    return any(concept in (t.get("name"), t.get("canonical")) for t in slide.get("teaches") or [])


def _source(slide, in_section):
    return {"slide_id": slide["id"], "filename": slide.get("filename"), "number": slide.get("number"),
            "in_section": in_section}


def _sources(concept, own_slides, slide_index):
    here = [_source(s, True) for s in own_slides if _teaches(s, concept)]
    if here:
        return here
    elsewhere = sorted((s for s in slide_index.values() if _teaches(s, concept)),
                       key=lambda s: (s.get("filename") or "", s.get("number") or 0))
    return [_source(s, False) for s in elsewhere[:MAX_FALLBACK_SOURCES]]


class _SynonymsOnce:
    """One synonyms lookup per concept name per view: sections share concepts, and each lookup may be a query."""

    def __init__(self, store):
        self.store, self.seen = store, {}

    def synonyms(self, names):
        key = tuple(names)
        if key not in self.seen:
            self.seen[key] = self.store.synonyms(list(names))
        return self.seen[key]


def section_concepts(project, nodes, slide_index, alignment=None) -> Dict[str, dict]:
    alignment = _SynonymsOnce(alignment) if alignment is not None else None
    children_of = outline(project, nodes)
    reached: List[tuple] = []  # (node, role, is_leaf) in outline order

    def walk(pid, role):
        for n in children_of(pid):
            r = role or n.get("section_type") or "technical"
            leaf = not children_of(n["id"])
            reached.append((n, r, leaf))
            if not leaf:
                walk(n["id"], r)

    walk(None, None)

    info = {}
    named_by: Dict[str, List[dict]] = {}
    for n, role, leaf in reached:
        ids = (n.get("suggested_ids") or []) if n.get("status") == "suggestion" else (n.get("source_refs") or [])
        slides = [slide_index[i] for i in ids if i in slide_index]
        if leaf:
            concepts, inherited = effective_concepts(n, slides)
            for c in concepts:
                named_by.setdefault(c, []).append({"id": n["id"], "title": n.get("title") or "", "role": role})
        else:
            concepts, inherited = list(dict.fromkeys(c for c in (n.get("key_concepts") or []) if c)), False
        info[n["id"]] = (leaf, role, concepts, inherited, slides)

    out = {}
    for n, _, _ in reached:
        leaf, role, concepts, inherited, slides = info[n["id"]]
        body = (n.get("content_markdown") or "").strip()
        rows = []
        for c in concepts:
            repeated = [r for r in named_by.get(c, []) if r["id"] != n["id"]] if leaf else []
            overlap = leaf and role not in REVISITING_ROLES and any(r["role"] not in REVISITING_ROLES for r in repeated)
            rows.append({"concept": c, "sources": _sources(c, slides, slide_index),
                         "repeated_in": repeated, "overlap": overlap,
                         "covered": covered(body, concept_terms([c], slides, alignment)[c]) if leaf and body else None})
        out[n["id"]] = {"exported": leaf, "inherited": inherited, "concepts": rows}
    return out


def build_view(project_id, *, neo4j_client, reader, alignment=None):
    """The concepts view for a project, read only. Returns {node_id: view}."""
    rows = neo4j_client.execute_query(PROJECT_QUERY, {"id": project_id})
    if not rows:
        raise LookupError(f"Project {project_id} not found")
    nodes = fetch_course_nodes(neo4j_client, project_id)
    deck_ids = list(rows[0].get("deck_ids") or [])
    for n in nodes:
        deck_ids.extend(n.get("slide_decks") or [])
    deck_ids = list(dict.fromkeys(deck_ids))
    if not deck_ids and reader is not None:
        deck_ids = [c["id"] for c in reader.list_courses(None)]
    lookup = ReaderLookup(reader) if reader is not None else GraphLookup(neo4j_client)
    slide_index: Dict[str, dict] = {}
    for deck_id in deck_ids:
        for sl in lookup.deck_slides(deck_id) or []:
            slide_index.setdefault(sl["id"], sl)
    project = {"id": project_id, "title": rows[0].get("title") or "", "deck_ids": deck_ids}
    return section_concepts(project, nodes, slide_index, alignment)
