"""Render a project to a file. The api process calls this."""
import json
import os
import re
import tempfile
from pathlib import Path

from src.publishing.course import (
    FixtureImageResolver,
    GraphLookup,
    MinioImageResolver,
    ReaderLookup,
    DeckExportError,
    build_course,
    concept_overlaps,
    skipped_sections,
    unfinished_sections,
)
from src.publishing import deck_template
from src.publishing.deck_export import export_deck, load_mapping
from src.publishing.typst_generator import generate_typst_document

FORMATS = {"pptx", "typ"}

COURSE_NODES_QUERY = """
MATCH (p:Project {id: $project_id})-[:HAS_CHILD*]->(n:TargetNode)
MATCH (parent)-[:HAS_CHILD]->(n)
RETURN n.id AS id, parent.id AS parent_id, n.title AS title, n.order AS order,
       n.content_markdown AS content_markdown, n.key_concepts AS key_concepts,
       coalesce(n.is_unassigned, false) AS is_unassigned,
       coalesce(n.source_slide_ids, []) AS source_refs,
       coalesce(n.section_type,'technical') AS section_type, n.status AS status,
       [(n)-[:SUGGESTED_SOURCE]->(s:Slide) | s.id] AS suggested_ids,
       [(n)-[:SUGGESTED_SOURCE|DERIVED_FROM]->(:Slide)<-[:HAS_SLIDE]-(c:Course) | c.id] AS slide_decks
"""

PROJECT_QUERY = """
MATCH (p:Project {id: $id})
RETURN p.title AS title, coalesce(p.source_deck_ids, []) AS deck_ids
"""

TYPST_NODES_QUERY = """
MATCH (p:Project {id: $project_id})
OPTIONAL MATCH (p)-[:HAS_CHILD*]->(n:TargetNode)
RETURN n.title as title, n.content_markdown as content_markdown, n.target_layout as target_layout, n.order as order
ORDER BY n.order
"""


def fetch_course_nodes(neo4j_client, project_id):
    return [dict(row) for row in neo4j_client.execute_query(COURSE_NODES_QUERY, {"project_id": project_id})]


def fetch_typst_nodes(neo4j_client, project_id):
    rows = neo4j_client.execute_query(TYPST_NODES_QUERY, {"project_id": project_id})
    return [
        {
            "title": row["title"],
            "content_markdown": row["content_markdown"],
            "target_layout": row.get("target_layout"),
            "order": row["order"],
        }
        for row in rows
        if row["title"]
    ]


def output_filename(title, project_id, fmt) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", title) + "_" + project_id[:8] + "." + fmt


RENDER_OVERRIDE_QUERY = """
MATCH (p:Project {id:$id}) SET p.render_overrides = coalesce(p.render_overrides, []) + $entry
"""


def _lookup_and_resolver(neo4j_client, minio_client, reader, deck_ids):
    if reader is not None:
        return ReaderLookup(reader), FixtureImageResolver(reader, deck_ids)
    return (GraphLookup(neo4j_client),
            MinioImageResolver(minio_client, os.getenv("BUCKET_NAME", "processing-artifacts"), deck_ids))


def _project(neo4j_client, project_id):
    rows = neo4j_client.execute_query(PROJECT_QUERY, {"id": project_id})
    if not rows:
        raise LookupError(f"Project {project_id} not found")
    return {"id": project_id, "title": rows[0]["title"], "deck_ids": list(rows[0].get("deck_ids") or [])}


def render_readiness(project_id, *, neo4j_client, reader):
    """What stops a pptx render, or None. Unfinished sections first, then build problems, then overlaps."""
    project = _project(neo4j_client, project_id)
    nodes = fetch_course_nodes(neo4j_client, project_id)
    unfinished, total = unfinished_sections(project, nodes)
    if unfinished:
        return {"kind": "unfinished", "message": f"{len(unfinished)} of {total} sections unfinished",
                "unfinished": len(unfinished), "total": total, "sections": unfinished}
    lookup, _ = _lookup_and_resolver(neo4j_client, None, reader, project["deck_ids"])
    try:
        course = build_course(project, nodes, lookup)
    except DeckExportError as e:
        return {"kind": "problems", "message": "The deck cannot be built", "problems": e.problems}
    overlaps = concept_overlaps(course)
    if overlaps:
        return {"kind": "concept_overlap",
                "message": f"{len(overlaps)} concept{' is' if len(overlaps) == 1 else 's are'} taught in more than one section",
                "overlaps": overlaps}
    return None


def _overlap_lines(overlaps):
    return [f"concept '{o['concept']}' is on {len(o['sections'])} sections: "
            + ", ".join(f"'{s['title']}'" for s in o["sections"]) + "; rendering needs a reason"
            for o in overlaps]


def render_project(project_id, fmt, template_name, out_path, *, neo4j_client, minio_client, reader, override=None) -> Path:
    """Write the project as `fmt` to out_path. `reader` set means fixture mode, None means the direct stores.
    `override` is {reason, by, at} for a pptx whose course repeats a concept across concept-role sections."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(sorted(FORMATS))}")
    project = _project(neo4j_client, project_id)
    title, deck_ids = project["title"], project["deck_ids"]
    out_path = Path(out_path)

    if fmt == "typ":
        out_path.write_text(generate_typst_document(title, fetch_typst_nodes(neo4j_client, project_id)), encoding="utf-8", newline="\n")
        return out_path

    with tempfile.TemporaryDirectory() as tmpdir:
        # One configured template applies; template_name is kept for the call signature.
        mapping_path = deck_template.configured_mapping()
        lookup, resolver = _lookup_and_resolver(neo4j_client, minio_client, reader, deck_ids)
        course = build_course(project, fetch_course_nodes(neo4j_client, project_id), lookup)
        overlaps = concept_overlaps(course)
        if overlaps and not override:
            raise DeckExportError(_overlap_lines(overlaps))
        anyway = bool(overlaps)
        export_deck(course, mapping_path, out_path, resolver, render_anyway=anyway)
        skipped = skipped_sections(course, load_mapping(mapping_path).section_body)
        if anyway or skipped:
            given = override or {}
            entry = json.dumps({
                "schema": "deck_export/1", "slides_sha256": course.slides_sha256,
                "reason": given.get("reason"), "by": given.get("by"), "at": given.get("at"),
                "filename": out_path.name, "overlaps": overlaps, "skipped_sections": skipped,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            neo4j_client.execute_query(RENDER_OVERRIDE_QUERY, {"id": project_id, "entry": entry})
    return out_path
