"""The consolidated course the deck exporter takes as input (docs/contracts/deck-template.md section 3)."""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse


class DeckExportError(Exception):
    """Every export failure: one exception listing all the problems found."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("deck export failed:\n- " + "\n- ".join(self.problems))


@dataclass
class SourceRef:
    course_id: str
    filename: str
    number: int
    slide_id: str


@dataclass
class Figure:
    ref: str


@dataclass
class Leaf:
    id: str
    title: str
    concepts: List[str]
    body: str
    notes: str
    figure: Optional[Figure]
    sources: List[SourceRef]


@dataclass
class Section:
    id: str
    title: str
    children: list = field(default_factory=list)


@dataclass
class Course:
    title: str
    children: list = field(default_factory=list)


MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
ASSET_REF = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


def iter_leaves(course):
    def walk(children):
        for c in children:
            if isinstance(c, Section):
                yield from walk(c.children)
            else:
                yield c
    yield from walk(course.children)


def iter_slides(course):
    """(role, item) in export order, including the generated title, summary and sources slides."""
    def walk(children):
        for c in children:
            if isinstance(c, Section):
                yield "section", c
                yield from walk(c.children)
            else:
                yield ("concept-with-figure" if c.figure else "concept"), c

    yield "title", course
    yield from walk(course.children)
    yield "summary", course
    yield "sources", course


def course_concepts(course) -> List[str]:
    return [c for leaf in iter_leaves(course) for c in leaf.concepts]


def _decks_of(sources):
    out: Dict[str, Dict] = {}
    for s in sources:
        e = out.setdefault(s.course_id, {"course_id": s.course_id, "filename": s.filename, "numbers": set()})
        e["numbers"].add(s.number)
    return [{**e, "numbers": sorted(e["numbers"])} for e in out.values()]


def decks(course) -> List[Dict]:
    """Source decks in order of first citation, each with its cited slide numbers ascending."""
    out: Dict[str, Dict] = {}
    for leaf in iter_leaves(course):
        for d in _decks_of(leaf.sources):
            e = out.setdefault(d["course_id"], {"course_id": d["course_id"], "filename": d["filename"], "numbers": set()})
            e["numbers"].update(d["numbers"])
    return [{**e, "numbers": sorted(e["numbers"])} for e in out.values()]


def _slides_text(numbers):
    return ("slide " if len(numbers) == 1 else "slides ") + ", ".join(str(n) for n in numbers)


def format_citation(sources) -> str:
    """Contract section 4."""
    ds = _decks_of(sources)
    if len(ds) == 1 and len(ds[0]["numbers"]) == 1:
        return f"Source: {ds[0]['filename']}, {_slides_text(ds[0]['numbers'])}"
    return "Sources: " + "; ".join(f"{d['filename']}, {_slides_text(d['numbers'])}" for d in ds)


def format_deck_line(deck) -> str:
    return f"{deck['filename']}: {_slides_text(deck['numbers'])}"


def title_body(course) -> str:
    n = len(decks(course))
    return f"Consolidated from {n} source deck" + ("" if n == 1 else "s")


def notes_text(leaf) -> str:
    line = "Concepts: " + "; ".join(leaf.concepts)
    return f"{leaf.notes}\n{line}" if leaf.notes else line


def split_body_and_figure(markdown):
    """(body without image markup, image refs in the order they appear)."""
    text = markdown or ""
    found = sorted(
        [(m.start(), m.group(1)) for m in MARKDOWN_IMAGE.finditer(text)]
        + [(m.start(), m.group(1)) for m in ASSET_REF.finditer(text)]
    )
    body = ASSET_REF.sub("", MARKDOWN_IMAGE.sub("", text)).strip()
    return body, [r for _, r in found]


def _order_key(n):
    o = n.get("order")
    return (o is None, o if o is not None else 0, n["id"])


def build_course(project, nodes, lookup) -> Course:
    problems: List[str] = []
    by_parent: Dict[Optional[str], List[dict]] = {}
    ids = {n["id"] for n in nodes}
    for n in nodes:
        p = n.get("parent_id")
        if p == project["id"] or p not in ids:
            p = None
        by_parent.setdefault(p, []).append(n)

    seen_concepts: Dict[str, str] = {}

    def children_of(pid):
        return [n for n in sorted(by_parent.get(pid, []), key=_order_key) if not n.get("is_unassigned")]

    def convert(n):
        kids = children_of(n["id"])
        if kids:
            return Section(n["id"], n.get("title") or "", [convert(k) for k in kids])
        return make_leaf(n)

    def make_leaf(n):
        title = n.get("title") or ""
        where = f"'{title}'"
        sources, teaches = [], []
        for sid in n.get("source_refs") or []:
            s = lookup.slide(sid)
            if s is None:
                problems.append(f"leaf {where}: source slide '{sid}' was not found")
                continue
            sources.append(SourceRef(s["course_id"], s["filename"], s["number"], sid))
            teaches.extend(s.get("teaches") or [])
        if not n.get("source_refs"):
            problems.append(f"leaf {where}: has no source slides")
        concepts = list(dict.fromkeys(c for c in (n.get("key_concepts") or []) if c))
        if not concepts:
            ranked = sorted(teaches, key=lambda t: -(t["salience"] if t.get("salience") is not None else float("-inf")))
            concepts = list(dict.fromkeys(t["name"] for t in ranked if t.get("name")))
        if not concepts:
            problems.append(f"leaf {where}: has no concepts")
        body, refs = split_body_and_figure(n.get("content_markdown"))
        if not body:
            problems.append(f"leaf {where}: the body is empty")
        if len(refs) > 1:
            problems.append(f"leaf {where}: has {len(refs)} image references and a slide holds one")
        for c in concepts:
            if c in seen_concepts:
                problems.append(f"concept '{c}' is on two leaves: '{seen_concepts[c]}' and {where}")
            else:
                seen_concepts[c] = title
        return Leaf(n["id"], title, concepts, body, n.get("notes") or "", Figure(refs[0]) if refs else None, sources)

    course = Course(project.get("title") or "", [convert(n) for n in children_of(None)])
    if problems:
        raise DeckExportError(problems)
    return course


class ReaderLookup:
    """Slide lookup over a SourceReader (fixture or multi-fixture)."""

    def __init__(self, reader):
        self.reader = reader
        self._filenames = None

    def _filename(self, course_id):
        if self._filenames is None:
            self._filenames = {c["id"]: c.get("filename") for c in self.reader.list_courses(None)}
        return self._filenames.get(course_id)

    def slide(self, slide_id):
        s = self.reader.slide(slide_id)
        if not s:
            return None
        return {
            "course_id": s["course_id"],
            "filename": self._filename(s["course_id"]) or s["course_id"],
            "number": s["number"],
            "teaches": [{"name": t["concept"], "salience": t.get("salience")} for t in s.get("teaches") or []],
        }


class GraphLookup:
    """Slide lookup over Neo4j, read-only. `client.execute_query(query, params)` returns row dicts."""

    SLIDE = """
    MATCH (c:Course)-[:HAS_SLIDE]->(s:Slide {id: $id})
    OPTIONAL MATCH (s)-[t:TEACHES]->(k:Concept)
    RETURN c.id AS course_id, c.filename AS filename, s.number AS number,
           collect(CASE WHEN k IS NULL THEN NULL ELSE {name: k.name, salience: t.salience} END) AS teaches
    """

    def __init__(self, client):
        self.client = client

    def slide(self, slide_id):
        rows = self.client.execute_query(self.SLIDE, {"id": slide_id})
        if not rows:
            return None
        r = rows[0]
        return {"course_id": r["course_id"], "filename": r["filename"] or r["course_id"], "number": r["number"],
                "teaches": [t for t in r["teaches"] or [] if t]}


def _read_all(obj) -> bytes:
    try:
        return obj.read()
    finally:
        for name in ("close", "release_conn"):
            fn = getattr(obj, name, None)
            if fn:
                fn()


class FixtureImageResolver:
    """Resolves fixture image references through reader.asset(name); None when unknown."""

    EXTENSIONS = ("", ".png", ".jpg", ".jpeg")

    def __init__(self, reader):
        self.reader = reader

    def __call__(self, ref):
        ref = unquote((ref or "").strip())
        name = ref.rsplit("images/", 1)[-1] if "images/" in ref else ref.rsplit("/", 1)[-1]
        # an asset_id has no extension: try the usual image ones
        for ext in self.EXTENSIONS if re.fullmatch(r"[\w\-]+", name) else ("",):
            got = self.reader.asset(name + ext)
            if got:
                return got[0]
        return None


class MinioImageResolver:
    """Resolves a source-contract image key, a presigned URL (key read from the path) or a /.../images/... key."""

    def __init__(self, minio_client, bucket):
        self.client = minio_client
        self.bucket = bucket

    def _key(self, ref):
        ref = (ref or "").strip()
        if re.match(r"^https?://", ref):
            ref = unquote(urlparse(ref).path)
        ref = ref.lstrip("/")
        if ref.startswith(self.bucket + "/"):
            ref = ref[len(self.bucket) + 1:]
        return ref if "images/" in ref else None

    def __call__(self, ref):
        key = self._key(ref)
        if not key:
            return None
        try:
            return _read_all(self.client.get_object(self.bucket, key))
        except Exception:
            return None
