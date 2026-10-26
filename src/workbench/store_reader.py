"""SourceReader over the live stores (SOURCE_READER=store): Neo4j for structure, MinIO for images and
page rasters, Weaviate for search. Contract: docs/contracts/training-workbench.md.

Each course is read as a subgraph in the shape of the golden's `neo4j` section and handed to the same
CourseModel the fixture reader uses, so the assembly (sections, covers, teaches, images) is shared.
Every Neo4j query here is a read. MinIO is touched only under `training/`, and only through the
`prefix` that a course's current.json names; no key is built from a course id.
"""
import json
import mimetypes
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

from src.publishing.image_ids import deck_prefix, split
from src.workbench import asset_links
from src.workbench.fixture_reader import ASSET_URL, REF_PREFIX, CourseModel

MINIO_ROOT = "training/"
WEAVIATE_COLLECTION = "DocumentChunk"
DOMAIN = "TRAINING"
DEFAULT_CACHE_SECONDS = 300
_PAGE_NAME = re.compile(r"^page_\d+\.png$")

# --- Neo4j: reads only ---------------------------------------------------------------------------

COURSES_QUERY = """
MATCH (c:Course:TRAINING)
RETURN properties(c) AS props
ORDER BY c.id
"""

SLIDE_FACETS_QUERY = """
MATCH (s:Slide:TRAINING)
RETURN collect(DISTINCT s.pedagogical_intent) AS pedagogical_intent,
       collect(DISTINCT s.asset_type) AS asset_type
"""

COURSE_SUBGRAPH_QUERY = """
MATCH (c:Course:TRAINING {id: $course_id})
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:HAS_SLIDE]->(s:Slide:TRAINING)
  RETURN collect(DISTINCT properties(s)) AS slides
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:HAS_SECTION*0..]->(p)-[:HAS_SECTION]->(sec:Section:TRAINING)
  RETURN collect(DISTINCT {from: p.id, to: sec.id}) AS has_section,
         collect(DISTINCT properties(sec)) AS sections
}
CALL {
  WITH c
  // Contract §4: HAS_CHILD is the generic Section -> Slide edge, HAS_SLIDE the training overlay.
  // The sandbox graph carries only HAS_CHILD (2026-10-25), so either one counts.
  OPTIONAL MATCH (c)-[:HAS_SECTION*1..]->(sec:Section:TRAINING)-[:HAS_SLIDE|HAS_CHILD]->(sl:Slide:TRAINING)
  WITH sec, sl ORDER BY sec.id, sl.number
  RETURN collect(DISTINCT {from: sec.id, to: sl.id}) AS section_slide
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:HAS_SECTION*1..]->(sec:Section:TRAINING)-[r:COVERS]->(k:Concept:TRAINING)
  RETURN collect(DISTINCT {from: sec.id, to: k.name, score: r.score, frequency: r.frequency}) AS covers
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:HAS_SLIDE]->(sl:Slide:TRAINING)-[t:TEACHES]->(k:Concept:TRAINING)
  WITH sl, t, k ORDER BY sl.number, k.name
  RETURN collect({from: sl.id, to: k.name, salience: t.salience}) AS teaches
}
RETURN properties(c) AS course, slides, sections, has_section, section_slide, covers, teaches
"""

COURSE_ID_BY_PREFIX_QUERY = """
MATCH (c:Course:TRAINING)
WHERE c.id STARTS WITH $id_start
RETURN c.id AS id
ORDER BY c.id
"""

CONCEPT_NAMES_QUERY = """
MATCH (k:Concept:TRAINING)
RETURN k.name AS name
ORDER BY k.name
"""

SLIDES_TEACHING_QUERY = """
MATCH (c:Course:TRAINING)-[:HAS_SLIDE]->(s:Slide:TRAINING)-[t:TEACHES]->(k:Concept:TRAINING)
WHERE k.name IN $names
RETURN c.id AS course_id, s.id AS slide_id, k.name AS concept, t.salience AS salience
ORDER BY c.id, s.number, k.name
"""

NEO4J_QUERIES = {
    "COURSES_QUERY": COURSES_QUERY,
    "SLIDE_FACETS_QUERY": SLIDE_FACETS_QUERY,
    "COURSE_SUBGRAPH_QUERY": COURSE_SUBGRAPH_QUERY,
    "COURSE_ID_BY_PREFIX_QUERY": COURSE_ID_BY_PREFIX_QUERY,
    "CONCEPT_NAMES_QUERY": CONCEPT_NAMES_QUERY,
    "SLIDES_TEACHING_QUERY": SLIDES_TEACHING_QUERY,
}


def _is_missing(exc) -> bool:
    return getattr(exc, "code", None) in ("NoSuchKey", "NoSuchBucket", "NoSuchObject")


def _distinct(vals):
    return sorted({v for v in vals if v})


def _golden_from_subgraph(row: dict) -> dict:
    """A subgraph row in the shape CourseModel reads (the golden's `neo4j` section)."""
    teaches = [t for t in row.get("teaches") or [] if t.get("from")]
    covers = [c for c in row.get("covers") or [] if c.get("from")]
    names = list(dict.fromkeys([t["to"] for t in teaches] + [c["to"] for c in covers]))
    return {"neo4j": {
        "course": {"props": row["course"]},
        "slides": {"nodes": list(row.get("slides") or [])},
        "nondeterministic": {
            "sections": {"nodes": list(row.get("sections") or [])},
            "concepts": {"nodes": [{"name": n} for n in names]},
            "edges": {
                "HAS_SECTION": [e for e in row.get("has_section") or [] if e.get("to")],
                "section_slide": [e for e in row.get("section_slide") or [] if e.get("to")],
                "COVERS": covers,
                "TEACHES": teaches,
            },
        },
    }}


class _StoreImages:
    """A course's images in MinIO, found through its current.json. Resolved on first use."""

    def __init__(self, reader, current_key):
        self._reader = reader
        self._current_key = current_key
        self._prefix = None
        self._resolved = False
        self._names = None

    def prefix(self) -> Optional[str]:
        if not self._resolved:
            self._prefix = self._reader._version_prefix(self._current_key)
            self._resolved = True
        return self._prefix

    def names(self) -> List[str]:
        if self._names is None:
            self._names = []
            prefix = self.prefix()
            if prefix:
                self._names = self._reader._list_names(prefix + "images/")
        return list(self._names)

    def load(self, name) -> Optional[bytes]:
        return self.fetch("images/", name)

    def fetch(self, sub, base) -> Optional[bytes]:
        prefix = self.prefix()
        if not prefix or not base or "/" in base or base in (".", ".."):
            return None
        return self._reader._get(prefix + sub + base)


class StoreReader:
    def __init__(self, neo4j, minio, weaviate, bucket, cache_seconds=None, clock=time.monotonic):
        self.neo4j = neo4j
        self.minio = minio
        self.weaviate = weaviate
        self.bucket = bucket
        if cache_seconds is None:
            cache_seconds = float(os.getenv("WB_STORE_CACHE_SECONDS", DEFAULT_CACHE_SECONDS))
        self.cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._models: Dict[str, Tuple[float, CourseModel]] = {}
        self._ids_by_prefix: Dict[str, str] = {}

    # ---- stores ----

    def _read(self, query, params=None):
        return self.neo4j.execute_query(query, params or {})

    def _check_key(self, key):
        if not key.startswith(MINIO_ROOT):
            raise ValueError(f"refusing MinIO key outside {MINIO_ROOT}: {key!r}")

    def _get(self, key) -> Optional[bytes]:
        self._check_key(key)
        try:
            obj = self.minio.get_object(self.bucket, key)
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise
        try:
            return obj.read()
        finally:
            obj.close()
            release = getattr(obj, "release_conn", None)
            if release:
                release()

    def _version_prefix(self, current_key) -> Optional[str]:
        """The live version folder named by current.json, or None."""
        if not current_key:
            return None
        raw = self._get(current_key)
        if raw is None:
            return None
        prefix = (json.loads(raw) or {}).get("prefix")
        if not isinstance(prefix, str) or not prefix.startswith(MINIO_ROOT) or not prefix.endswith("/"):
            return None
        return prefix

    def _list_names(self, prefix) -> List[str]:
        self._check_key(prefix)
        out = []
        for o in self.minio.list_objects(self.bucket, prefix=prefix, recursive=False):
            if getattr(o, "is_dir", False) or not o.object_name.startswith(prefix):
                continue
            base = o.object_name[len(prefix):]
            if base and "/" not in base:
                out.append(base)
        return out

    def _asset_url(self, prefix12, name) -> str:
        """The one place an asset URL is made. Signed: <img> sends no bearer (asset_links)."""
        asset = f"{prefix12}--{name}"
        return f"{ASSET_URL}{asset}?{asset_links.signed_query(asset)}"

    # ---- course models ----

    def _course_rows(self) -> List[dict]:
        return [dict(r["props"]) for r in self._read(COURSES_QUERY)]

    def _model(self, course_id) -> Optional[CourseModel]:
        if not course_id:
            return None
        with self._lock:
            hit = self._models.get(course_id)
            if hit and self._clock() - hit[0] < self.cache_seconds:
                return hit[1]
            rows = self._read(COURSE_SUBGRAPH_QUERY, {"course_id": course_id})
            if not rows or not rows[0].get("course"):
                self._models.pop(course_id, None)
                return None
            course = rows[0]["course"]
            model = CourseModel(_golden_from_subgraph(rows[0]),
                                _StoreImages(self, course.get("current_key")))
            self._models[course_id] = (self._clock(), model)
            return model

    def _owner_of_slide(self, slide_id) -> Optional[CourseModel]:
        cid, sep, _ = (slide_id or "").rpartition("_p")
        m = self._model(cid) if sep else None
        return m if m and slide_id in m._slides else None

    def _model_by_prefix(self, prefix12) -> Optional[CourseModel]:
        cid = self._ids_by_prefix.get(prefix12)
        if cid is None:
            rows = self._read(COURSE_ID_BY_PREFIX_QUERY, {"id_start": "sha256:" + prefix12})
            ids = [r["id"] for r in rows if deck_prefix(r["id"]) == prefix12]
            if not ids:
                return None
            cid = self._ids_by_prefix[prefix12] = ids[0]
        return self._model(cid)

    # ---- SourceReader ----

    def list_courses(self, discipline=None):
        rows = [{"id": c["id"], "title": c.get("title"), "business_unit": c.get("business_unit"),
                 "discipline": c.get("discipline"), "filename": c.get("filename"),
                 "version": c.get("version")} for c in self._course_rows()]
        if discipline:
            rows = [r for r in rows if r["discipline"] and discipline.lower() in r["discipline"].lower()]
        return sorted(rows, key=lambda r: (r["business_unit"] or "", r["title"] or "", r["id"]))

    def facets(self):
        courses = self._course_rows()
        row = (self._read(SLIDE_FACETS_QUERY) or [{}])[0]
        return {
            "business_unit": _distinct(c.get("business_unit") for c in courses),
            "discipline": _distinct(c.get("discipline") for c in courses),
            "pedagogical_intent": _distinct(row.get("pedagogical_intent") or []),
            "asset_type": _distinct(row.get("asset_type") or []),
        }

    def course_slides(self, course_id):
        m = self._model(course_id)
        return m.course_slides(course_id) if m else []

    def course_sections(self, course_id):
        m = self._model(course_id)
        return m.course_sections(course_id) if m else []

    def slide(self, slide_id):
        m = self._owner_of_slide(slide_id)
        return m.slide(slide_id) if m else None

    def slides(self, slide_ids):
        out = []
        for i in slide_ids:
            m = self._owner_of_slide(i)
            if m:
                out.append(m.slide(i))
        return out

    def page_preview_url(self, slide_id):
        m = self._owner_of_slide(slide_id)
        if not m:
            return None
        return self._asset_url(deck_prefix(m.course_id), f"page_{m._slides[slide_id]['number']}.png")

    def embedded_images(self, course_id):
        m = self._model(course_id)
        if not m:
            return []
        k = deck_prefix(course_id)
        out = []
        for im in m.embedded_images(course_id):
            im = dict(im)
            im["ref"] = f"{REF_PREFIX}{k}--{im['name']}"
            out.append(im)
        return out

    def resolve_ref(self, ref):
        if not ref.startswith(REF_PREFIX):
            return None
        parts = split(ref[len(REF_PREFIX):])
        if not parts:
            return None
        m = self._model_by_prefix(parts[0])
        if not m or not m.has_image(parts[1]):
            return None
        return self._asset_url(parts[0], parts[1])

    def asset(self, name: str) -> Optional[Tuple[bytes, str]]:
        parts = split(name)
        if not parts:
            return None
        prefix12, base = parts
        m = self._model_by_prefix(prefix12)
        if not m:
            return None
        sub = "pages/" if _PAGE_NAME.match(base) else "images/"
        data = m._images.fetch(sub, base)
        if data is None:
            return None
        return data, mimetypes.guess_type(base)[0] or "application/octet-stream"

    def concept_names(self):
        return [r["name"] for r in self._read(CONCEPT_NAMES_QUERY)]

    def slides_teaching(self, names):
        names = list(names)
        if not names:
            return []
        return [{"course_id": r["course_id"], "slide_id": r["slide_id"], "concept": r["concept"],
                 "salience": r["salience"]} for r in self._read(SLIDES_TEACHING_QUERY, {"names": names})]

    def search(self, query, course_ids, limit):
        """BM25 over DocumentChunk.text, training domain, optionally within course_ids. Ranked slide ids."""
        if not (query or "").strip() or limit <= 0 or (course_ids is not None and not list(course_ids)):
            return []
        where = {"path": ["domain"], "operator": "Equal", "valueText": DOMAIN}
        if course_ids is not None:
            where = {"operator": "And", "operands": [
                where, {"path": ["doc_id"], "operator": "ContainsAny", "valueText": list(course_ids)}]}
        response = (self.weaviate.client.query
                    .get(WEAVIATE_COLLECTION, ["chunk_id", "doc_id"])
                    .with_bm25(query=query, properties=["text"])
                    .with_where(where)
                    .with_limit(limit)
                    .do())
        hits = ((response.get("data") or {}).get("Get") or {}).get(WEAVIATE_COLLECTION) or []
        return list(dict.fromkeys(h["chunk_id"] for h in hits if h.get("chunk_id")))[:limit]


def build_store_reader() -> StoreReader:
    """A StoreReader on the clients the api already uses. Weaviate (v3) connects when built, so the
    clients are lazy."""
    from src.storage.minio import MinioClient
    from src.workbench.main import BUCKET_NAME, neo4j_client, weaviate_client

    class _Lazy:
        def __init__(self, factory):
            self._factory, self._inst = factory, None

        def __getattr__(self, name):
            if self._inst is None:
                self._inst = self._factory()
            return getattr(self._inst, name)

    minio = _Lazy(lambda: MinioClient(secure=os.getenv("MINIO_SECURE", "false").lower() == "true"))
    return StoreReader(neo4j_client, minio, weaviate_client, BUCKET_NAME)
