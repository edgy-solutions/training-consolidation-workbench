"""Image ids are '<deck prefix>--<name>'. No dagster or neo4j imports: shared by the synthesizer, readers and exporter."""
import re

_SPLIT = re.compile(r"^([0-9a-f]{12})--(.+)$", re.S)
_PLACEHOLDER = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


class ImageRefError(ValueError):
    """A resolver's refusal; the message goes into the export's problem list."""


def deck_prefix(course_id: str) -> str:
    return course_id.split(":", 1)[-1][:12]


def qualify(course_id: str, name: str) -> str:
    return f"{deck_prefix(course_id)}--{name}"


def split(image_id):
    """(prefix, name) for '<12 lowercase hex>--<non-empty>', else None."""
    m = _SPLIT.match(image_id or "")
    return (m.group(1), m.group(2)) if m else None


def qualify_placeholders(markdown, offered_ids) -> str:
    """Rewrite a bare {{x}} to the one offered id ending in '--x'; anything else is left for the export to refuse."""
    offered = list(dict.fromkeys(offered_ids or []))
    offered_set = set(offered)

    def fix(m):
        x = m.group(1)
        if x in offered_set:
            return m.group(0)
        hits = [o for o in offered if o.endswith("--" + x)]
        return "{{" + hits[0] + "}}" if len(hits) == 1 else m.group(0)

    return _PLACEHOLDER.sub(fix, markdown or "")


def list_generated_objects(minio_client, bucket, course_id):
    """Every object under the deck's generated folder (images, text.json, ...)."""
    return list(minio_client.list_objects(bucket, prefix=f"{course_id}/generated/", recursive=True))


def image_objects(objects):
    return [o for o in objects if not o.is_dir and "/images/" in o.object_name]
