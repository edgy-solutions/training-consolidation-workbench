"""SourceReader over the vendored contract fixture (golden.json + the pptx).

Sections, COVERS and TEACHES come from the golden's explicit edges; nothing is
derived from id grammar or formulas.
"""
import json
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REF_PREFIX = "fixture://images/"
ASSET_URL = "/source/fixture-asset/"


class FixtureReader:
    def __init__(self, fixture_dir):
        d = Path(fixture_dir)
        g = json.loads((d / "golden.json").read_text(encoding="utf-8"))
        neo = g["neo4j"]
        nd = neo["nondeterministic"]
        edges = nd["edges"]
        self.course = dict(neo["course"]["props"])
        self.course_id = self.course["id"]
        # slide node entries are flat dicts in the golden (no "props" nesting)
        self._slides = {}
        for n in neo["slides"]["nodes"]:
            p = n.get("props", n)
            self._slides[p["id"]] = dict(p)
        self._sections = {n["id"]: n for n in nd["sections"]["nodes"]}
        self._parent = {e["to"]: e["from"] for e in edges["HAS_SECTION"]}
        self._section_slides: Dict[str, List[str]] = {}
        for e in edges["section_slide"]:
            self._section_slides.setdefault(e["from"], []).append(e["to"])
        self._covers: Dict[str, List[dict]] = {}
        for e in edges["COVERS"]:
            self._covers.setdefault(e["from"], []).append({"concept": e["to"], "score": e["score"]})
        self._teaches: Dict[str, List[dict]] = {}
        for e in edges["TEACHES"]:
            self._teaches.setdefault(e["from"], []).append({"concept": e["to"], "salience": e["salience"]})
        self._concepts = [c["name"] for c in nd["concepts"]["nodes"]]
        # images: golden media keys under /images/ -> bytes from the pptx zip
        keys = [k for k in g["minio"]["keys_required"] if "/images/" in k]
        names = [os.path.basename(k) for k in keys]
        self._image_bytes: Dict[str, bytes] = {}
        with zipfile.ZipFile(d / g["fixture"]["deck"]) as z:
            media = sorted(n for n in z.namelist() if n.startswith("ppt/media/"))
            by_base = {os.path.basename(m): m for m in media}
            unmatched = [m for m in media if os.path.basename(m) not in names]
            for name in names:
                if name in by_base:
                    self._image_bytes[name] = z.read(by_base[name])
                elif unmatched:
                    # golden name absent from the pptx: map in order
                    self._image_bytes[name] = z.read(unmatched.pop(0))
        self._image_names = names

    def _slide_shape(self, s: dict) -> dict:
        el = s.get("elements")
        return {
            "id": s["id"],
            "course_id": self.course_id,
            "number": s["number"],
            "text": s.get("text") or "",
            "elements": el if isinstance(el, str) else json.dumps(el if el is not None else []),
            "asset_type": s.get("asset_type"),
            "layout_style": s.get("layout_style"),
            "teaches": [dict(t) for t in self._teaches.get(s["id"], [])],
        }

    def list_courses(self, discipline=None):
        c = self.course
        rows = [{"id": c["id"], "title": c.get("title"), "business_unit": c.get("business_unit"),
                 "discipline": c.get("discipline")}]
        if discipline:
            rows = [r for r in rows if r["discipline"] and discipline.lower() in r["discipline"].lower()]
        return sorted(rows, key=lambda r: (r["business_unit"] or "", r["title"] or ""))

    def facets(self):
        slides = list(self._slides.values())

        def distinct(vals):
            return sorted({v for v in vals if v})

        return {
            "business_unit": distinct([self.course.get("business_unit")]),
            "discipline": distinct([self.course.get("discipline")]),
            "pedagogical_intent": distinct(s.get("pedagogical_intent") for s in slides),
            "asset_type": distinct(s.get("asset_type") for s in slides),
        }

    def course_slides(self, course_id):
        if course_id != self.course_id:
            return []
        return [{"id": s["id"], "number": s["number"], "text": s.get("text")}
                for s in sorted(self._slides.values(), key=lambda s: s["number"])]

    def course_sections(self, course_id):
        if course_id != self.course_id:
            return []
        out = []
        for sid, n in self._sections.items():
            parent = self._parent.get(sid)
            if parent == self.course_id:
                parent = None
            covers = sorted(self._covers.get(sid, []), key=lambda c: -c["score"])
            out.append({
                "id": sid, "parent_id": parent, "title": n.get("title"), "level": n.get("level"),
                "start_page": n.get("start_page"), "end_page": n.get("end_page"),
                "concept_summary": n.get("concept_summary"),
                "slide_ids": list(self._section_slides.get(sid, [])),
                "covers": [dict(c) for c in covers],
            })
        return out

    def slide(self, slide_id):
        s = self._slides.get(slide_id)
        return self._slide_shape(s) if s else None

    def slides(self, slide_ids):
        return [self._slide_shape(self._slides[i]) for i in slide_ids if i in self._slides]

    def page_preview_url(self, slide_id):
        return None

    def embedded_images(self, course_id):
        if course_id != self.course_id:
            return []
        coords: Dict[str, Tuple[Optional[int], Optional[dict]]] = {}
        for s in self._slides.values():
            el = s.get("elements")
            if isinstance(el, str):
                el = json.loads(el)
            for e in el or []:
                md = e.get("metadata") or {}
                if md.get("image_path"):
                    coords[os.path.basename(md["image_path"])] = (md.get("page_number"), md.get("coordinates"))
        out = []
        for name in self._image_names:
            page, co = coords.get(name, (None, None))
            if page is None:
                m = re.match(r"slide_(\d+)_img_\d+", name)
                page = int(m.group(1)) if m else None
            out.append({"ref": REF_PREFIX + name, "name": name, "page_number": page, "coordinates": co})
        return out

    def resolve_ref(self, ref):
        if ref.startswith(REF_PREFIX) and ref[len(REF_PREFIX):] in self._image_bytes:
            return ASSET_URL + ref[len(REF_PREFIX):]
        return None

    def asset(self, name: str) -> Optional[Tuple[bytes, str]]:
        b = self._image_bytes.get(name)
        if b is None:
            return None
        return b, mimetypes.guess_type(name)[0] or "application/octet-stream"

    def concept_names(self):
        return list(self._concepts)

    def slides_teaching(self, names):
        wanted = set(names)
        out = []
        for s in sorted(self._slides.values(), key=lambda s: s["number"]):
            for t in self._teaches.get(s["id"], []):
                if t["concept"] in wanted:
                    out.append({"course_id": self.course_id, "slide_id": s["id"],
                                "concept": t["concept"], "salience": t["salience"]})
        return out

    def search(self, query, course_ids, limit):
        """FAKE: a stand-in for the API's vector search. Case-insensitive term overlap
        between query words and slide text, score desc, ties by slide id."""
        if course_ids is not None and self.course_id not in course_ids:
            return []
        terms = set(re.findall(r"\w+", query.lower()))
        scored = []
        for s in self._slides.values():
            words = set(re.findall(r"\w+", (s.get("text") or "").lower()))
            score = len(terms & words)
            if score:
                scored.append((-score, s["id"]))
        return [i for _, i in sorted(scored)][:limit]
