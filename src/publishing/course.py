"""The consolidated course the deck exporter takes as input (docs/contracts/deck-template.md section 3)."""
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from src.publishing.image_ids import ImageRefError, deck_prefix, image_objects, list_generated_objects, split


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
    role: str = "technical"


@dataclass
class Section:
    id: str
    title: str
    children: list = field(default_factory=list)


@dataclass
class Course:
    title: str
    children: list = field(default_factory=list)
    slides_sha256: Optional[str] = None


REVISITING_ROLES = {"introduction", "mandatory_safety", "mandatory_assessment"}

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
    """Each concept once, in order of first appearance."""
    return list(dict.fromkeys(c for leaf in iter_leaves(course) for c in leaf.concepts))


def concept_overlaps(course) -> List[Dict]:
    """Concepts named by two or more concept-role leaves (leaves of a revisiting role are not counted)."""
    where: Dict[str, List[dict]] = {}
    for leaf in iter_leaves(course):
        if leaf.role in REVISITING_ROLES:
            continue
        for c in leaf.concepts:
            where.setdefault(c, []).append({"id": leaf.id, "title": leaf.title})
    return [{"concept": c, "sections": secs} for c, secs in where.items() if len(secs) > 1]


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
    """Leaf notes, then the citation line, then the Concepts line, which is always last."""
    lines = [leaf.notes] if leaf.notes else []
    if leaf.sources:
        lines.append(format_citation(leaf.sources))
    lines.append("Concepts: " + "; ".join(leaf.concepts))
    return "\n".join(lines)


def sources_body(course) -> str:
    """The sources slide's face: counts only, never a filename (the filename lines go in its notes)."""
    ds = decks(course)
    n, m = len(ds), sum(len(d["numbers"]) for d in ds)
    return f"{n} source deck{'' if n == 1 else 's'}, {m} cited slide{'' if m == 1 else 's'}"


DEFAULT_MAX_BULLETS = 5
CONT_SUFFIX = " (cont.)"
_HEADING = re.compile(r"^#+\s+")


def _is_heading(line) -> bool:
    return bool(_HEADING.match(line.strip()))


def _indent(line) -> int:
    expanded = line.replace("\t", "    ")
    return len(expanded) - len(expanded.lstrip())


def split_bullets(body, max_bullets) -> List[str]:
    """Chunks of a body holding at most max_bullets lines each. A heading counts 0 and stays with what follows it;
    a bullet and its indented lines stay together unless that block alone is over the limit, which is cut by line."""
    lines = [ln for ln in (body or "").splitlines() if ln.strip()]
    if sum(1 for ln in lines if not _is_heading(ln)) <= max_bullets:
        return [body]
    blocks: List[List[str]] = []
    pending: List[str] = []
    for ln in lines:
        if _is_heading(ln):
            pending.append(ln)
        elif _indent(ln) == 0 or not blocks:
            blocks.append(pending + [ln])
            pending = []
        else:
            blocks[-1] += pending + [ln]
            pending = []
    if pending:
        if blocks:
            blocks[-1] += pending
        else:
            blocks.append(pending)

    chunks: List[List[str]] = []
    cur: List[str] = []
    count = 0

    def flush():
        nonlocal cur, count
        tail = []
        while cur and _is_heading(cur[-1]):
            tail.insert(0, cur.pop())  # a heading never ends a chunk
        if cur:
            chunks.append(cur)
        cur, count = tail, 0

    for block in blocks:
        size = sum(1 for ln in block if not _is_heading(ln))
        if count + size <= max_bullets:
            cur += block
            count += size
            continue
        flush()
        if size <= max_bullets:
            cur, count = cur + block, size
            continue
        for ln in block:  # an oversized block is cut by line
            if not _is_heading(ln):
                if count == max_bullets:
                    flush()
                count += 1
            cur.append(ln)
    if cur:
        chunks.append(cur)
    return ["\n".join(c) for c in chunks]


@dataclass
class SummaryPart:
    title: str
    body: str


def deck_slides(course, max_bullets=DEFAULT_MAX_BULLETS):
    """(role, item) in export order: iter_slides, with a long body or the summary split over continuation slides."""
    for role, item in iter_slides(course):
        if role in ("concept", "concept-with-figure"):
            for i, chunk in enumerate(split_bullets(item.body, max_bullets)):
                if i == 0:
                    yield role, replace(item, body=chunk)
                else:
                    yield "concept", replace(item, title=item.title + CONT_SUFFIX, body=chunk, figure=None, notes="")
        elif role == "summary":
            body = "\n".join("- " + c for c in course_concepts(course))
            for i, chunk in enumerate(split_bullets(body, max_bullets)):
                yield "summary", SummaryPart("Summary" + (CONT_SUFFIX if i else ""), chunk)
        else:
            yield role, item


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


def outline(project, nodes):
    """children_of(parent_id) for the outline: ordered, unassigned nodes dropped. None is the top level."""
    by_parent: Dict[Optional[str], List[dict]] = {}
    ids = {n["id"] for n in nodes}
    for n in nodes:
        p = n.get("parent_id")
        if p == project["id"] or p not in ids:
            p = None
        by_parent.setdefault(p, []).append(n)

    def children_of(pid):
        return [n for n in sorted(by_parent.get(pid, []), key=_order_key) if not n.get("is_unassigned")]

    return children_of


def iter_leaf_nodes(project, nodes):
    """(node, role) for each leaf in outline order. The role is the top-level ancestor's section_type."""
    children_of = outline(project, nodes)

    def walk(pid, role):
        for n in children_of(pid):
            r = role or n.get("section_type") or "technical"
            if children_of(n["id"]):
                yield from walk(n["id"], r)
            else:
                yield n, r

    yield from walk(None, None)


def unfinished_sections(project, nodes):
    """([{id, title}] of leaves with no source slides or an empty body, number of leaves)."""
    leaves = list(iter_leaf_nodes(project, nodes))
    out = [{"id": n["id"], "title": n.get("title") or ""} for n, _ in leaves
           if not n.get("source_refs") or not split_body_and_figure(n.get("content_markdown"))[0]]
    return out, len(leaves)


def effective_concepts(node, slides):
    """(concepts, inherited): key_concepts, else the slides' teaches by descending salience."""
    concepts = list(dict.fromkeys(c for c in (node.get("key_concepts") or []) if c))
    if concepts:
        return concepts, False
    teaches = [t for s in slides for t in (s.get("teaches") or [])]
    ranked = sorted(teaches, key=lambda t: -(t["salience"] if t.get("salience") is not None else float("-inf")))
    return list(dict.fromkeys(t["name"] for t in ranked if t.get("name"))), True


def build_course(project, nodes, lookup) -> Course:
    problems: List[str] = []
    children_of = outline(project, nodes)

    deck_ids = list(project.get("deck_ids") or [])
    slide_index: Dict[str, dict] = {}
    if not deck_ids:
        problems.append("the course records no source decks")
    for deck_id in deck_ids:
        found = lookup.deck_slides(deck_id)
        if found is None:
            problems.append(f"source deck '{deck_id}' was not found")
            continue
        for sl in found:
            slide_index.setdefault(sl["id"], sl)

    def convert(n, role):
        kids = children_of(n["id"])
        if kids:
            return Section(n["id"], n.get("title") or "", [convert(k, role) for k in kids])
        return make_leaf(n, role)

    def make_leaf(n, role):
        title = n.get("title") or ""
        where = f"'{title}'"
        sources, slides = [], []
        for sid in n.get("source_refs") or []:
            s = slide_index.get(sid)
            if s is None:
                problems.append(f"leaf {where}: source slide '{sid}' is not in any deck this course was built from")
                continue
            sources.append(SourceRef(s["course_id"], s["filename"], s["number"], sid))
            slides.append(s)
        if not n.get("source_refs"):
            problems.append(f"leaf {where}: has no source slides")
        concepts, _ = effective_concepts(n, slides)
        if not concepts:
            problems.append(f"leaf {where}: has no concepts")
        body, refs = split_body_and_figure(n.get("content_markdown"))
        if not body:
            problems.append(f"leaf {where}: the body is empty")
        if len(refs) > 1:
            problems.append(f"leaf {where}: has {len(refs)} image references and a slide holds one")
        return Leaf(n["id"], title, concepts, body, n.get("notes") or "", Figure(refs[0]) if refs else None, sources, role)

    course = Course(project.get("title") or "",
                    [convert(n, n.get("section_type") or "technical") for n in children_of(None)])
    if problems:
        raise DeckExportError(problems)
    return course


class ReaderLookup:
    """Deck lookup over a SourceReader (fixture or multi-fixture)."""

    def __init__(self, reader):
        self.reader = reader
        self._filenames = None

    def _filename(self, course_id):
        if self._filenames is None:
            self._filenames = {c["id"]: c.get("filename") for c in self.reader.list_courses(None)}
        return self._filenames.get(course_id)

    def deck_slides(self, deck_id):
        """The deck's slides, or None when the reader does not know the deck."""
        if deck_id not in {c["id"] for c in self.reader.list_courses(None)}:
            return None
        filename = self._filename(deck_id) or deck_id
        out = []
        for row in self.reader.course_slides(deck_id):
            s = self.reader.slide(row["id"]) or {}
            out.append({
                "id": row["id"],
                "course_id": deck_id,
                "filename": filename,
                "number": row["number"],
                "teaches": [{"name": t["concept"], "salience": t.get("salience")} for t in s.get("teaches") or []],
            })
        return out


class GraphLookup:
    """Deck lookup over Neo4j, read-only. `client.execute_query(query, params)` returns row dicts."""

    DECK = """
    MATCH (c:Course {id: $deck})-[:HAS_SLIDE]->(s:Slide)
    OPTIONAL MATCH (s)-[t:TEACHES]->(k:Concept)
    OPTIONAL MATCH (k)-[:ALIGNS_TO]->(cc:CanonicalConcept)
    RETURN c.id AS course_id, c.filename AS filename, s.id AS id, s.number AS number,
           collect(CASE WHEN k IS NULL THEN NULL ELSE {name: k.name, salience: t.salience, canonical: cc.name} END) AS teaches
    """

    def __init__(self, client):
        self.client = client

    def deck_slides(self, deck_id):
        rows = self.client.execute_query(self.DECK, {"deck": deck_id})
        if not rows:
            return None
        return [{"id": r["id"], "course_id": r["course_id"], "filename": r["filename"] or r["course_id"],
                 "number": r["number"], "teaches": [t for t in r["teaches"] or [] if t]} for r in rows]


def _read_all(obj) -> bytes:
    try:
        return obj.read()
    finally:
        for name in ("close", "release_conn"):
            fn = getattr(obj, name, None)
            if fn:
                fn()


def _checked_name(name, prefixes):
    """The prefixed image name if it is '<deck>--<name>' of a recorded deck; otherwise ImageRefError."""
    parts = split(name)
    if parts is None:
        raise ImageRefError(f"image '{name}' carries no deck prefix; image ids are '<deck>--<name>'")
    if parts[0] not in prefixes:
        raise ImageRefError(
            f"image '{name}' names deck prefix '{parts[0]}', which is not a deck this course was built from")
    return parts


class FixtureImageResolver:
    """Resolves fixture image references through reader.asset(name); None when unknown.
    Image ids are '<deck>--<name>' of a deck the course records; anything else is refused."""

    EXTENSIONS = ("", ".png", ".jpg", ".jpeg")

    def __init__(self, reader, deck_ids):
        self.reader = reader
        self.prefixes = {deck_prefix(d) for d in deck_ids or []}

    def __call__(self, ref):
        ref = unquote((ref or "").strip())
        name = ref.rsplit("images/", 1)[-1] if "images/" in ref else ref.rsplit("/", 1)[-1]
        _checked_name(name, self.prefixes)
        # an asset_id has no extension: try the usual image ones
        for ext in self.EXTENSIONS if re.fullmatch(r"[\w\-]+", name) else ("",):
            got = self.reader.asset(name + ext)
            if got:
                return got[0]
        return None


class MinioImageResolver:
    """Resolves a source-contract image key, a presigned URL (key read from the path) or a /.../images/... key;
    a deck-prefixed image id resolves to the object of that deck whose key ends with /images/<name>."""

    def __init__(self, minio_client, bucket, deck_ids):
        self.client = minio_client
        self.bucket = bucket
        self.deck_ids = list(deck_ids or [])
        self.prefixes = {deck_prefix(d) for d in self.deck_ids}

    def _key(self, ref):
        ref = (ref or "").strip()
        if re.match(r"^https?://", ref):
            ref = unquote(urlparse(ref).path)
        ref = ref.lstrip("/")
        if ref.startswith(self.bucket + "/"):
            ref = ref[len(self.bucket) + 1:]
        return ref if "images/" in ref else None

    def _by_id(self, name):
        prefix, bare = _checked_name(name, self.prefixes)
        for deck in self.deck_ids:
            if deck_prefix(deck) != prefix:
                continue
            for obj in image_objects(list_generated_objects(self.client, self.bucket, deck)):
                if obj.object_name.endswith("/images/" + bare):
                    return obj.object_name
        return None

    def __call__(self, ref):
        ref = unquote((ref or "").strip())
        key = self._key(ref)
        if key is None:
            # a bare id: {{name}} or a markdown target without a path
            key = self._by_id(ref.rsplit("/", 1)[-1])
        if not key:
            return None
        try:
            return _read_all(self.client.get_object(self.bucket, key))
        except Exception:
            return None
