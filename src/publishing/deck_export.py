"""Exports a consolidated course as a .pptx against docs/contracts/deck-template.md.

The code names no template, layout or placeholder index; those come from the mapping file.
"""
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.shapes.placeholder import PicturePlaceholder

from src.publishing.deck_template import DECK_TEMPLATE_VERSION, STANDIN_MAPPING
from src.publishing.image_ids import ImageRefError
from src.publishing.course import (
    DEFAULT_MAX_BULLETS, DEFAULT_MAX_SUMMARY_ITEMS, Course, DeckExportError, course_concepts, deck_slides, decks, format_citation, more_in_notes, summary_items,
    format_deck_line, iter_leaves, notes_text, sources_body, title_body,
)

NOTES_PAGE = "notes-page"

DEFAULT_MAPPING = STANDIN_MAPPING

ROLES = {
    "title": {"required": ["title"], "optional": ["body"]},
    "section": {"required": ["title"], "optional": ["body"]},
    "concept": {"required": ["title", "body"], "optional": ["notes"]},
    "concept-with-figure": {"required": ["title", "body", "image"], "optional": ["notes"]},
    "summary": {"required": ["title", "body"], "optional": []},
    "sources": {"required": ["title", "body"], "optional": []},
}
# Fields an older mapping may still name: accepted and warned about, never written, so the sweep removes the placeholder.
RETIRED_FIELDS = {"concept": ["citation"], "concept-with-figure": ["citation"]}
IMAGE_TYPES = (PP_PLACEHOLDER.PICTURE, PP_PLACEHOLDER.OBJECT)


@dataclass
class Mapping:
    path: Path
    version: object
    template: Optional[str]
    roles: Dict[str, dict]
    max_bullets_per_slide: object = DEFAULT_MAX_BULLETS
    max_summary_items: object = DEFAULT_MAX_SUMMARY_ITEMS

    @property
    def template_path(self) -> Optional[Path]:
        return (self.path.parent / self.template) if self.template else None


def load_mapping(path) -> Mapping:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise DeckExportError([f"mapping file {path} could not be read: {e}"])
    if not isinstance(raw, dict):
        raise DeckExportError([f"mapping file {path} is not a mapping"])
    return Mapping(path, raw.get("deck_template"), raw.get("template"), raw.get("roles") or {},
                   raw.get("max_bullets_per_slide", DEFAULT_MAX_BULLETS), raw.get("max_summary_items", DEFAULT_MAX_SUMMARY_ITEMS))


def _all_layouts(prs):
    """Every layout in template order: each master in turn, then its layouts. A layout_index counts in this order."""
    return [lo for master in prs.slide_masters for lo in master.slide_layouts]


def _resolve_layout(prs, role, spec):
    """(layout, problem, warning) for a role's layout and optional layout_index; contract section 2.3."""
    layouts = _all_layouts(prs)
    name = spec.get("layout")
    carriers = [i for i, lo in enumerate(layouts) if lo.name == name]
    if "layout_index" in spec:
        i = spec["layout_index"]
        if isinstance(i, bool) or not isinstance(i, int):
            return None, f"role '{role}': layout_index must be an integer, got {i!r}", None
        if not 0 <= i < len(layouts):
            return None, f"role '{role}': layout_index {i} is out of range; the template has {len(layouts)} layouts", None
        if layouts[i].name != name:
            return None, (f"role '{role}': layout_index {i} is layout '{layouts[i].name}', "
                          f"but the role names layout '{name}'"), None
        if len(carriers) > 1:
            return layouts[i], None, (f"role '{role}': layout '{name}' is carried by {len(carriers)} layouts; "
                                      f"using the one at position {i}")
        return layouts[i], None, None
    if not carriers:
        return None, (f"role '{role}': layout '{name}' is not in the template; its layouts are: "
                      + ", ".join(sorted({lo.name for lo in layouts}))), None
    if len(carriers) > 1:
        return layouts[carriers[0]], None, (
            f"role '{role}': layout '{name}' is carried by {len(carriers)} layouts and no layout_index is set; "
            f"using the first, at position {carriers[0]}. Set layout_index to choose explicitly")
    return layouts[carriers[0]], None, None


def mapping_warnings(mapping: Mapping) -> List[str]:
    """Warnings for a mapping; layout warnings need the template, so none of those when it cannot be opened."""
    out = []
    for role, spec in mapping.roles.items():
        if role in RETIRED_FIELDS and isinstance(spec, dict) and isinstance(spec.get("placeholders"), dict):
            for f in RETIRED_FIELDS[role]:
                if f in spec["placeholders"]:
                    out.append(f"role '{role}': field '{f}' is retired; citations now go in the speaker notes "
                               f"and the placeholder is removed from the slide")
    try:
        prs = Presentation(str(mapping.template_path))
    except Exception:
        return out
    for role, spec in mapping.roles.items():
        if role in ROLES and isinstance(spec, dict) and spec.get("layout"):
            warning = _resolve_layout(prs, role, spec)[2]
            if warning:
                out.append(warning)
    return out


def _valid_count(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _needed_roles(course, max_bullets=DEFAULT_MAX_BULLETS):
    return list(dict.fromkeys(role for role, _ in deck_slides(course, max_bullets)))


def validate(mapping: Mapping, course) -> List[str]:
    v = mapping.max_bullets_per_slide
    return validate_mapping(mapping, _needed_roles(course, v if _valid_count(v) else DEFAULT_MAX_BULLETS))


def validate_mapping(mapping: Mapping, needed_roles) -> List[str]:
    problems: List[str] = []
    if mapping.version != DECK_TEMPLATE_VERSION:
        problems.append(f"deck_template is {mapping.version!r}, this exporter reads {DECK_TEMPLATE_VERSION}")
    if not _valid_count(mapping.max_bullets_per_slide):
        problems.append(f"max_bullets_per_slide must be a whole number of at least 1, got {mapping.max_bullets_per_slide!r}")
    if not _valid_count(mapping.max_summary_items):
        problems.append(f"max_summary_items must be a whole number of at least 1, got {mapping.max_summary_items!r}")
    prs = None
    if not mapping.template:
        problems.append("the mapping names no template")
    elif not mapping.template_path.is_file():
        problems.append(f"template file {mapping.template_path} is missing")
    else:
        try:
            prs = Presentation(str(mapping.template_path))
        except Exception as e:
            problems.append(f"template file {mapping.template_path} could not be opened: {e}")

    for role in needed_roles:
        if role not in mapping.roles:
            problems.append(f"role '{role}' is not mapped")

    for role, spec in mapping.roles.items():
        if role not in ROLES:
            problems.append(f"unknown role '{role}'")
            continue
        spec = spec or {}
        fields = spec.get("placeholders") or {}
        known = ROLES[role]["required"] + ROLES[role]["optional"]
        retired = RETIRED_FIELDS.get(role, [])
        for f in fields:
            if f not in known and f not in retired:
                problems.append(f"role '{role}': unknown field '{f}'")
        for f in ROLES[role]["required"]:
            if f not in fields:
                problems.append(f"role '{role}': required field '{f}' is not mapped")
        if role == "title" and "body" not in fields:
            problems.append(f"role 'title': the course has a subtitle and the role maps no 'body' field for it")

        name = spec.get("layout")
        if not name:
            problems.append(f"role '{role}': no layout named")
            continue
        if not prs:
            continue
        layout, problem, _ = _resolve_layout(prs, role, spec)
        if problem:
            problems.append(problem)
            continue
        types = {p.placeholder_format.idx: p.placeholder_format.type for p in layout.placeholders}
        used: Dict[int, str] = {}
        for f, idx in fields.items():
            if f not in known:  # unknown, or retired and so never read
                continue
            if f == "notes" and idx == NOTES_PAGE:
                continue
            if isinstance(idx, bool) or not isinstance(idx, int):
                problems.append(f"role '{role}': field '{f}' must be a placeholder idx, got {idx!r}")
                continue
            if idx not in types:
                problems.append(f"role '{role}': field '{f}' names placeholder {idx}, which layout '{name}' does not have")
                continue
            if f == "image" and types[idx] not in IMAGE_TYPES:
                problems.append(f"role '{role}': image placeholder {idx} on layout '{name}' cannot take a picture")
            if idx in used:
                problems.append(f"role '{role}': placeholder {idx} is mapped to both '{used[idx]}' and '{f}'")
            used[idx] = f
    return problems


def _runs(text):
    parts = re.split(r"(\*\*.+?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            yield part[2:-2], True
        elif part:
            yield part, False


def write_text(text_frame, markdown):
    """Paragraphs from markdown lines: bullets and indentation become levels, `**x**` and `#` headers become bold."""
    lines = [ln.rstrip() for ln in (markdown or "").splitlines() if ln.strip()]
    text_frame.clear()
    first = True
    for line in lines:
        indent = len(line.replace("\t", "    ")) - len(line.replace("\t", "    ").lstrip())
        content = line.strip()
        bold_all = False
        m = re.match(r"^(#+)\s+(.*)$", content)
        if m:
            content, bold_all = m.group(2), True
            indent = 0
        else:
            m = re.match(r"^[-*+]\s+(.*)$", content)
            if m:
                content = m.group(1)
        p = text_frame.paragraphs[0] if first else text_frame.add_paragraph()
        first = False
        p.level = min(indent // 2, 8)
        for text, bold in _runs(content):
            r = p.add_run()
            r.text = text
            if bold or bold_all:
                r.font.bold = True


def _plain(text_frame):
    return [p.text for p in text_frame.paragraphs if p.text.strip()]


def _expected_fields(role, item, course):
    """field -> markdown text for a slide's role."""
    if role == "title":
        return {"title": course.title, "body": title_body(course)}
    if role == "section":
        return {"title": item.title}
    if role in ("concept", "concept-with-figure"):
        return {"title": item.title, "body": item.body, "notes": notes_text(item)}
    if role == "summary":
        return {"title": item.title, "body": item.body, "notes": item.notes}
    return {"title": "Sources", "body": sources_body(course), "notes": "\n".join(format_deck_line(d) for d in decks(course))}


def _drop_template_slides(prs):
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)


def deck_digest(course, images, max_bullets=DEFAULT_MAX_BULLETS, max_summary=DEFAULT_MAX_SUMMARY_ITEMS) -> str:
    """sha256 of what the exporter writes: each slide's number, role, fields and picture bytes.
    It hashes the content, not the file: a pptx is a zip with write times in it."""
    rows = []
    for n, (role, item) in enumerate(deck_slides(course, max_bullets, max_summary), start=1):
        data = images.get(item.id) if role == "concept-with-figure" else None
        rows.append([n, role, _expected_fields(role, item, course),
                     hashlib.sha256(data).hexdigest() if data else None])
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _comments(digest, render_anyway):
    return f"deck_export/1 slides_sha256={digest}" + (" render_anyway=yes" if render_anyway else "")


def export_deck(course: Course, mapping_path, out_path, resolve_image, render_anyway: bool = False) -> Path:
    out_path = Path(out_path)
    mapping = load_mapping(mapping_path)
    problems = validate(mapping, course)
    if problems:
        raise DeckExportError(problems)

    images: Dict[str, bytes] = {}
    for leaf in iter_leaves(course):
        if not leaf.figure:
            continue
        try:
            data = resolve_image(leaf.figure.ref)
        except ImageRefError as e:
            problems.append(f"leaf '{leaf.title}': {e}")
            continue
        except Exception:
            data = None
        if not data:
            problems.append(f"image '{leaf.figure.ref}' on '{leaf.title}' could not be resolved")
        else:
            images[leaf.id] = data
    if problems:
        raise DeckExportError(problems)

    digest = deck_digest(course, images, mapping.max_bullets_per_slide, mapping.max_summary_items)
    comments = _comments(digest, render_anyway)
    prs = Presentation(str(mapping.template_path))
    prs.core_properties.comments = comments
    for warning in mapping_warnings(mapping):
        print(f"WARN: deck template: {warning}")
    _drop_template_slides(prs)
    for role, item in deck_slides(course, mapping.max_bullets_per_slide, mapping.max_summary_items):
        spec = mapping.roles[role]
        fields = dict(spec.get("placeholders") or {})
        if "notes" in ROLES[role]["optional"]:
            fields.setdefault("notes", NOTES_PAGE)  # contract section 2.2: omitted means the notes page
        slide = prs.slides.add_slide(_resolve_layout(prs, role, spec)[0])
        values = _expected_fields(role, item, course)
        used = set()
        for f, idx in fields.items():
            if f == "image":
                # python-pptx gives only a picture placeholder insert_picture; an object placeholder takes it the same way.
                ph = slide.placeholders[idx]
                PicturePlaceholder(ph._element, ph._parent).insert_picture(io.BytesIO(images[item.id]))
                used.add(idx)
            elif f == "notes":
                if idx == NOTES_PAGE:
                    slide.notes_slide.notes_text_frame.text = values["notes"]
                else:
                    write_text(slide.placeholders[idx].text_frame, values["notes"])
                    used.add(idx)
            elif f in values:
                frame = slide.placeholders[idx].text_frame
                write_text(frame, values[f])
                if f == "body":
                    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE  # shrink on overflow; no font or size is set
                used.add(idx)
        if role == "sources" or (role == "summary" and item.notes):
            slide.notes_slide.notes_text_frame.text = values["notes"]
        for ph in list(slide.placeholders):
            if ph.placeholder_format.idx not in used:
                ph._element.getparent().remove(ph._element)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".part")
    try:
        prs.save(str(tmp))
        problems = check_round_trip(course, mapping, tmp)
        written = Presentation(str(tmp)).core_properties.comments
        if written != comments:
            problems.append(f"the deck records {written!r} in its properties, expected {comments!r}")
        if problems:
            raise DeckExportError(problems)
        os.replace(tmp, out_path)
        course.slides_sha256 = digest
    finally:
        if tmp.exists():
            tmp.unlink()
    return out_path


def _slide_text(slide, mapping, role, field):
    """The paragraphs a slide holds for a field, or None when the slide has no such text."""
    idx = (mapping.roles[role].get("placeholders") or {}).get(field)
    if field == "notes" and idx in (None, NOTES_PAGE):
        if not slide.has_notes_slide:
            return None
        return _plain(slide.notes_slide.notes_text_frame)
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx and ph.has_text_frame:
            return _plain(ph.text_frame)
    return None


def _has_picture(slide):
    return any(sp.tag.endswith("}pic") for sp in slide.shapes._spTree)


def check_round_trip(course, mapping, pptx_path) -> List[str]:
    """Contract section 6: read the written deck back and compare it with the course."""
    if not isinstance(mapping, Mapping):
        mapping = load_mapping(mapping)
    problems: List[str] = []
    prs = Presentation(str(pptx_path))
    slides = list(prs.slides)
    expected = list(deck_slides(course, mapping.max_bullets_per_slide, mapping.max_summary_items))

    want = [mapping.roles[role]["layout"] for role, _ in expected]
    got = [s.slide_layout.name for s in slides]
    if want != got:
        problems.append(f"slide sequence: expected {len(want)} slides with layouts {want}, found {len(got)} with {got}")
        return problems

    seen: Dict[str, List[int]] = {}
    summary: List[str] = []
    summary_notes: List[str] = []
    for n, (slide, (role, item)) in enumerate(zip(slides, expected), start=1):
        if role in ("concept", "concept-with-figure"):
            lines = _slide_text(slide, mapping, role, "notes") or []
            line = next((ln for ln in reversed(lines) if ln.startswith("Concepts:")), None)
            actual = [c.strip() for c in line[len("Concepts:"):].split(";") if c.strip()] if line else []
            if line is None:
                problems.append(f"slide {n} ('{item.title}'): no 'Concepts:' line in the notes")
            for c in item.concepts:
                if c not in actual:
                    problems.append(f"slide {n} ('{item.title}'): concept '{c}' is missing from the notes")
            for c in actual:
                if c not in item.concepts:
                    problems.append(f"slide {n} ('{item.title}'): concept '{c}' is not in the course for this leaf")
                seen.setdefault(c, []).append(n)

            if item.sources:
                want_cite = format_citation(item.sources)
                at = lines.index(line) if line in lines else -1
                if at < 1 or lines[at - 1] != want_cite:
                    problems.append(f"slide {n} ('{item.title}'): the notes lack the citation {want_cite!r} "
                                    f"directly before the Concepts line")

        has_pic = _has_picture(slide)
        if role == "concept-with-figure" and not has_pic:
            problems.append(f"slide {n} ('{item.title}'): the figure is missing")
        if role != "concept-with-figure" and has_pic:
            problems.append(f"slide {n} ({role}): holds a picture but should not")

        if role == "summary":
            summary += _slide_text(slide, mapping, role, "body") or []
            summary_notes = _slide_text(slide, mapping, role, "notes") or []  # the last summary slide's wins
        if role == "sources":
            body = _slide_text(slide, mapping, role, "body")
            if body != [sources_body(course)]:
                problems.append(f"slide {n}: the sources slide reads {body}, expected {[sources_body(course)]}")
            notes = _slide_text(slide, mapping, role, "notes")
            want_lines = [format_deck_line(d) for d in decks(course)]
            if notes != want_lines:
                problems.append(f"slide {n}: the sources slide notes list {notes}, the course cites {want_lines}")

        face = " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
        for d in decks(course):
            if d["filename"] in face:
                problems.append(f"slide {n}: source filename '{d['filename']}' is on the slide face")

    shown, rest = summary_items(course, mapping.max_summary_items)
    want_face = shown + ([more_in_notes(rest)] if rest else [])
    if summary != want_face:
        problems.append(f"the summary slides list {summary}, the course has {want_face}")
    if summary_notes != rest:
        problems.append(f"the last summary slide's notes list {summary_notes}, the course has {rest} beyond the summary")
    for c in course_concepts(course):
        if c not in seen:
            problems.append(f"concept '{c}' appears on no concept slide")
    return problems
