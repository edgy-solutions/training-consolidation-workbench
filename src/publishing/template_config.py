"""Reading and saving a deck template from the settings screen.

inspect_template() describes a .pptx for the mapping UI. check_and_save() holds a mapping to a stricter bar than the
contract's per-course rule (all six roles) and proves it with a trial export before anything reaches the store.
"""
import base64
import io
import tempfile
from pathlib import Path
from typing import Dict, List

import yaml
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER

from src.publishing import deck_template
from src.publishing.course import Course, DeckExportError, Figure, Leaf, Section, SourceRef
from src.publishing.deck_export import (
    DECK_TEMPLATE_VERSION, IMAGE_TYPES, RETIRED_FIELDS, ROLES, _all_layouts, _resolve_layout, export_deck, load_mapping,
    validate_mapping,
)

# python-pptx does not clone these onto a new slide (iter_cloneable_placeholders), so a field mapped to one
# could never be filled.
NOT_MAPPABLE = (PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER)

# A 1x1 PNG, for the trial export's figure.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TemplateRejected(DeckExportError):
    """The template or mapping is wrong (422), as against a store failure (503)."""


def role_spec() -> Dict[str, dict]:
    """Per role the required and optional fields. The validator also demands the title slide's subtitle."""
    spec = {r: {"required": list(s["required"]), "optional": list(s["optional"])} for r, s in ROLES.items()}
    spec["title"]["required"].append("body")
    spec["title"]["optional"].remove("body")
    return spec


def _type_name(t) -> str:
    return getattr(t, "name", None) or str(t)


def _open(source):
    try:
        data = source if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
        return Presentation(io.BytesIO(data))
    except Exception as e:
        raise TemplateRejected([f"the file is not a readable .pptx: {e}"])


def inspect_template(source) -> dict:
    """Slide size and, per layout, its placeholders. `source` is a path or the bytes of a .pptx."""
    prs = _open(source)
    layouts = [lo for master in prs.slide_masters for lo in master.slide_layouts]
    counts: Dict[str, int] = {}
    for lo in layouts:
        counts[lo.name] = counts.get(lo.name, 0) + 1
    out = []
    for pos, lo in enumerate(layouts):
        phs = []
        for ph in lo.placeholders:
            t = ph.placeholder_format.type
            phs.append({
                "idx": ph.placeholder_format.idx,
                "name": ph.name,
                "type": _type_name(t),
                "accepts_image": t in IMAGE_TYPES,
                "mappable": t not in NOT_MAPPABLE,
                "left": ph.left, "top": ph.top, "width": ph.width, "height": ph.height,
            })
        out.append({"name": lo.name, "index": pos, "name_count": counts[lo.name], "placeholders": phs})
    return {"slide_width": prs.slide_width, "slide_height": prs.slide_height, "layouts": out}


def _trial_course() -> Course:
    src = [SourceRef("sha256:trial", "trial.pptx", 1, "trial-1")]
    return Course("Template check", [
        Section("s1", "A section", [
            Leaf("l1", "A concept", ["Concept one"], "- First point\n- **Second** point", "Speaker notes.", None, src),
            Leaf("l2", "A figure", ["Concept two"], "A short body.", "", Figure("trial-image"), src),
        ], "- A section point"),
    ])


def _normalise(roles):
    """Only the keys the mapping reads, so nothing else is persisted."""
    out, problems = {}, []
    for role, spec in roles.items():
        fields = spec.get("placeholders") if isinstance(spec, dict) else None
        if not isinstance(spec, dict) or not isinstance(fields or {}, dict):
            problems.append(f"role '{role}' must be an object of layout and placeholders")
            continue
        retired = RETIRED_FIELDS.get(role, [])  # an old mapping may still name one; it is not persisted
        out[role] = {"layout": spec.get("layout"),
                     "placeholders": {f: v for f, v in (fields or {}).items() if f not in retired}}
        if "layout_index" in spec:
            out[role]["layout_index"] = spec["layout_index"]  # validate_mapping reports a bad type
    if problems:
        raise TemplateRejected(problems)
    return out


def check_and_save(pptx_bytes, roles, filename, saved_by, minio=None) -> dict:
    """Validate, trial-export, then write to the store. Raises TemplateRejected with every problem found."""
    if not isinstance(roles, dict):
        raise TemplateRejected(["roles must be an object of role -> {layout, placeholders}"])
    roles = _normalise(roles)
    info = inspect_template(pptx_bytes)  # raises TemplateRejected when unreadable
    prs = _open(pptx_bytes)

    problems: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "template.pptx").write_bytes(pptx_bytes)
        body = {"deck_template": DECK_TEMPLATE_VERSION, "template": "template.pptx", "roles": roles}
        (tmp / "deck-template.yaml").write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
        mapping = load_mapping(tmp / "deck-template.yaml")
        problems += validate_mapping(mapping, list(ROLES))

        for role, spec in roles.items():
            if role not in ROLES:
                continue
            found, problem, _ = _resolve_layout(prs, role, spec)
            if problem:
                continue  # validate_mapping has reported it
            layout = info["layouts"][_all_layouts(prs).index(found)]
            phs = {p["idx"]: p for p in layout["placeholders"]}
            for field, idx in spec["placeholders"].items():
                ph = phs.get(idx) if isinstance(idx, int) else None  # validate_mapping reports a non-int
                if ph and not ph["mappable"]:
                    problems.append(
                        f"role '{role}': field '{field}' is mapped to placeholder {idx} ({ph['type']}) on layout "
                        f"'{layout['name']}', which a new slide never carries, so it could not be filled")
        if problems:
            raise TemplateRejected(problems)

        try:
            export_deck(_trial_course(), tmp / "deck-template.yaml", tmp / "trial.pptx", lambda ref: _PNG)
        except DeckExportError as e:
            raise TemplateRejected([f"trial export: {p}" for p in e.problems])
        except Exception as e:
            raise TemplateRejected([f"trial export failed: {type(e).__name__}: {e}"])

    return deck_template.save(pptx_bytes, roles, filename, saved_by, minio)
