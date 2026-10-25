"""Render a project to a file. No Dagster: the api process and the Dagster asset both call this."""
import os
import re
import tempfile
from pathlib import Path

from src.publishing.course import (
    FixtureImageResolver,
    GraphLookup,
    MinioImageResolver,
    ReaderLookup,
    build_course,
)
from src.publishing.deck_export import DEFAULT_MAPPING, export_deck, load_mapping
from src.publishing.typst_generator import generate_typst_document

FORMATS = {"pptx", "typ"}

TEMPLATE_BUCKET = "cib-sources"

COURSE_NODES_QUERY = """
MATCH (p:Project {id: $project_id})-[:HAS_CHILD*]->(n:TargetNode)
MATCH (parent)-[:HAS_CHILD]->(n)
OPTIONAL MATCH (n)-[:DERIVED_FROM]->(s:Slide)
RETURN n.id AS id, parent.id AS parent_id, n.title AS title, n.order AS order,
       n.content_markdown AS content_markdown, n.key_concepts AS key_concepts,
       coalesce(n.is_unassigned, false) AS is_unassigned,
       collect(DISTINCT s.id) AS source_refs
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


def _download(minio_client, key, dest):
    obj = minio_client.get_object(TEMPLATE_BUCKET, key)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(obj.read())
    finally:
        obj.close()
        obj.release_conn()


def load_template_mapping(minio_client, name, temp_dir):
    """The mapping file for a template name: the stand-in from the repo, any other from cib-sources."""
    if name == "standin":
        return DEFAULT_MAPPING
    base = f"templates/{name}/"
    local = Path(temp_dir) / "template" / name
    _download(minio_client, base + "deck-template.yaml", local / "deck-template.yaml")
    mapping = load_mapping(local / "deck-template.yaml")
    if mapping.template:
        _download(minio_client, base + mapping.template, local / mapping.template)
    return local / "deck-template.yaml"


def output_filename(title, project_id, fmt) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", title) + "_" + project_id[:8] + "." + fmt


def render_project(project_id, fmt, template_name, out_path, *, neo4j_client, minio_client, reader) -> Path:
    """Write the project as `fmt` to out_path. `reader` set means fixture mode, None means the direct stores."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(sorted(FORMATS))}")
    rows = neo4j_client.execute_query("MATCH (p:Project {id: $id}) RETURN p.title AS title", {"id": project_id})
    if not rows:
        raise LookupError(f"Project {project_id} not found")
    title = rows[0]["title"]
    out_path = Path(out_path)

    if fmt == "typ":
        out_path.write_text(generate_typst_document(title, fetch_typst_nodes(neo4j_client, project_id)), encoding="utf-8", newline="\n")
        return out_path

    with tempfile.TemporaryDirectory() as tmpdir:
        mapping_path = load_template_mapping(minio_client, template_name or "standin", tmpdir)
        if reader is not None:
            lookup, resolver = ReaderLookup(reader), FixtureImageResolver(reader)
        else:
            lookup = GraphLookup(neo4j_client)
            resolver = MinioImageResolver(minio_client, os.getenv("BUCKET_NAME", "processing-artifacts"))
        course = build_course({"id": project_id, "title": title}, fetch_course_nodes(neo4j_client, project_id), lookup)
        export_deck(course, mapping_path, out_path, resolver)
    return out_path
