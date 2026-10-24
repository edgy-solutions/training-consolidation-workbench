"""Port-backed bodies for the /source/* and /search/* display routes.

Each _port_<route> returns exactly the shape the legacy (direct-store) body in
main.py returns. Legacy bodies stay in main.py and remain the default.
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from src.workbench.alignment import AlignmentStore, InMemoryAlignmentStore, Neo4jAlignmentStore
from src.workbench.models import ConceptNode, SourceSlide

SALIENCE_CUT = 0.5


def get_alignment_store(reader) -> AlignmentStore:
    from src.workbench.fixture_reader import is_fixture_reader
    if is_fixture_reader(reader):
        return InMemoryAlignmentStore({})
    from src.workbench.main import neo4j_client
    return Neo4jAlignmentStore(neo4j_client)


def _distinct(seq):
    return list(dict.fromkeys(seq))


def _max_salience(prev, cur):
    """max() that treats None as unknown: pre-step-d goldens carry salience null on every edge."""
    if prev is None:
        return cur
    return prev if cur is None else max(prev, cur)


def _course_tree(courses: List[dict], extra=None) -> List[Dict[str, Any]]:
    tree: Dict[str, Any] = {}
    for c in courses:
        bu = c.get("business_unit") or "Uncategorized"
        if bu not in tree:
            tree[bu] = {"name": bu, "type": "BusinessUnit", "children": []}
        entry = {
            "id": c["id"],
            "name": c["title"],
            "type": "Course",
            "engineering_discipline": c.get("discipline"),
            "filename": c.get("filename"),
            "version": c.get("version"),
        }
        entry.update(extra(c) if extra else {"has_children": True})
        tree[bu]["children"].append(entry)
    return list(tree.values())


def _port_source_tree(reader, discipline: Optional[str]):
    return _course_tree(reader.list_courses(discipline))


def _port_source_filters(reader):
    f = reader.facets()
    return {
        "origins": f.get("business_unit", []),
        "domains": f.get("discipline", []),
        "intents": f.get("pedagogical_intent", []),
        "types": f.get("asset_type", []),
    }


def _course_title(reader, course_id) -> Optional[str]:
    return next((c["title"] for c in reader.list_courses(None) if c["id"] == course_id), None)


def _port_course_slides(reader, alignment, course_id: str):
    """One call, row-ready: the SourceSlide fields plus legacy `text`."""
    out = []
    title = _course_title(reader, course_id)
    for s in reader.slides([r["id"] for r in reader.course_slides(course_id)]):
        d = _slide_model(reader, alignment, s, title).model_dump()
        d["text"] = s["text"]
        out.append(d)
    return out


def _course_concepts(reader, alignment, course_id):
    slides = reader.slides([s["id"] for s in reader.course_slides(course_id)])
    raw = [t["concept"] for s in slides for t in s["teaches"]
           if (t["salience"] if t["salience"] is not None else 0) >= SALIENCE_CUT]
    disp = alignment.display_names(_distinct(raw))
    return _distinct(disp[n] for n in raw)[:10]


def _port_course_sections(reader, alignment, course_id: str):
    sections = reader.course_sections(course_id)
    sections = sorted(sections, key=lambda s: (s.get("start_page") or 0, s["id"]))
    course_concepts = _course_concepts(reader, alignment, course_id)
    out = []
    for s in sections:
        # legacy: coalesce(stored summary, covered concepts[0..10], ...) -- a stored
        # list (even empty) wins; covered is never null so the slide fallback is dead.
        concepts = s.get("concept_summary")
        if concepts is None:
            raw = [c["concept"] for c in s["covers"]]
            disp = alignment.display_names(_distinct(raw))
            concepts = _distinct(disp[n] for n in raw)[:10]
        inherited = not concepts
        if inherited:
            concepts = course_concepts
        level = s.get("level")
        out.append({"id": s["id"], "title": s["title"],
                    "level": level if level is not None else 0, "parent_id": s.get("parent_id"),
                    "concepts": concepts, "slide_count": len(s.get("slide_ids") or []),
                    "concepts_inherited": inherited})
    return out


def _port_slide_details(reader, alignment, slide_id: str):
    s = reader.slide(slide_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Slide not found")
    return _slide_model(reader, alignment, s, _course_title(reader, s.get("course_id")))


def _slide_model(reader, alignment, s, course_title=None):
    slide_id = s["id"]
    # Legacy parity: slide detail shows every taught concept (no salience cut),
    # with max(salience) per display name.
    kept = [t for t in s["teaches"] if t.get("concept")]
    disp = alignment.display_names(_distinct(t["concept"] for t in kept))
    best: Dict[str, Optional[float]] = {}
    for t in kept:
        n = disp[t["concept"]]
        best[n] = _max_salience(best.get(n), t["salience"])
    concepts = [ConceptNode(name=n, domain="General", salience=v) for n, v in best.items()]
    try:
        elements = json.loads(s["elements"]) if s.get("elements") else []
    except Exception:
        elements = []
    return SourceSlide(
        id=s["id"],
        s3_url=reader.page_preview_url(slide_id) or "",
        text_preview=s["text"] or "",
        concepts=concepts,
        elements=elements,
        number=s.get("number"),
        course_id=s.get("course_id"),
        course_title=course_title,
    )


def _bbox_and_canvas(coords):
    coords = coords or {}
    points = coords.get("points", [])
    bbox = None
    if points and len(points) >= 2:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
    system = coords.get("system") or {}
    return (bbox,
            coords.get("layout_width") or system.get("layout_width"),
            coords.get("layout_height") or system.get("layout_height"))


def _port_embedded_images(reader, course_id: str):
    images = []
    for im in reader.embedded_images(course_id):
        bbox, cw, ch = _bbox_and_canvas(im.get("coordinates"))
        images.append({
            "filename": im["name"],
            "url": reader.resolve_ref(im["ref"]),
            "size": None,  # not part of the port
            "object_name": im["ref"],
            "bbox": bbox,
            "canvas_width": cw,
            "canvas_height": ch,
            "page_number": im.get("page_number"),
        })
    return {"course_id": course_id, "images": images}


def _port_embedded_images_for_slides(reader, slide_ids: List[str]):
    course_pages: Dict[str, set] = {}
    for s in reader.slides(slide_ids):
        course_pages.setdefault(s["course_id"], set()).add(s["number"])
    all_images = []
    for course_id, pages in course_pages.items():
        for img in _port_embedded_images(reader, course_id)["images"]:
            if img.get("page_number") is not None and img["page_number"] in pages:
                all_images.append(img)
    return {"images": all_images}


def _port_resolve_image_urls(reader, urls: List[str]):
    return {"urls": {u: (reader.resolve_ref(u) or u) for u in urls}}


def _port_resolve_image_url(reader, url: str):
    resolved = _port_resolve_image_urls(reader, [url])["urls"].get(url, url)
    return {"original": url, "presigned": resolved}


def _port_search_concepts(reader, q: str):
    return reader.search(q, None, 10)


def _port_slides_by_concept(reader, name: str):
    return _distinct(r["slide_id"] for r in reader.slides_teaching([name]))


def _port_heatmap(reader, alignment, term: str):
    t = term.lower()
    hits = [n for n in reader.concept_names() if t in n.lower()]
    if not hits:
        return {}
    names = _distinct(alignment.synonyms(hits))
    per_slide: Dict[str, Dict[str, Any]] = {}
    seen = set()
    for r in reader.slides_teaching(names):
        key = (r["slide_id"], r["concept"])
        if key in seen:
            continue
        seen.add(key)
        sal = r["salience"] if r["salience"] is not None else 0.5
        e = per_slide.setdefault(r["slide_id"], {"course_id": r["course_id"], "score": 0})
        e["score"] += sal
    heatmap: Dict[str, Any] = {}
    for sid, e in per_slide.items():
        heatmap[sid] = {"score": e["score"], "type": "slide"}
        c = heatmap.setdefault(e["course_id"], {"score": 0, "type": "course"})
        c["score"] = max(c["score"], e["score"])
    return heatmap


def _port_search_source_tree(reader, alignment, request):
    filters = request.filters or {}
    courses = reader.list_courses(None)
    if filters.get("origin"):
        courses = [c for c in courses if c.get("business_unit") == filters["origin"]]
    if filters.get("domain"):
        courses = [c for c in courses if c.get("discipline") == filters["domain"]]

    candidate_ids = None
    if request.query:
        candidate_ids = reader.search(request.query, [c["id"] for c in courses], 50)
        if not candidate_ids:
            return []
        candidate_ids = set(candidate_ids)

    want_type = filters.get("type")
    if want_type == "All Types":
        want_type = None
    want_intent = filters.get("intent")

    rows = []
    for c in courses:
        slides = reader.slides([s["id"] for s in reader.course_slides(c["id"])])
        picked = []
        for s in slides:
            if candidate_ids is not None and s["id"] not in candidate_ids:
                continue
            if want_type and (s.get("asset_type") or "").lower() != want_type.lower():
                continue
            # pedagogical_intent is not exposed per slide by the port (null in v1)
            if want_intent and s.get("pedagogical_intent") != want_intent:
                continue
            picked.append(s)
        if not picked:
            continue
        names = _distinct(t["concept"] for s in picked for t in s["teaches"])
        disp = alignment.display_names(names)
        out_slides = []
        for s in picked:
            best: Dict[str, Optional[float]] = {}
            for t in s["teaches"]:
                n = disp[t["concept"]]
                best[n] = _max_salience(best.get(n), t["salience"])
            out_slides.append({
                "id": s["id"],
                "number": s["number"],
                "text": s["text"],
                "s3_url": reader.page_preview_url(s["id"]),
                "concepts": [{"name": n, "domain": None, "salience": v} for n, v in best.items()],
            })
        rows.append((c, out_slides))

    def extra_for(slides_by_course):
        return lambda c: {"slides": slides_by_course[c["id"]], "has_children": True}

    by_course = {c["id"]: sl for c, sl in rows}
    return _course_tree([c for c, _ in rows], extra_for(by_course))
