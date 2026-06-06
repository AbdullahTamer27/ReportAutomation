"""Template registry: load TEMPLATES_DIR/manifest.json and upsert into the DB.

Manifest format — a JSON array (or an object with a "templates" array) of:
    {
      "name": "...",
      "damage_count": 4,
      "config_key": "4.5-7-9-13-18",
      "filename": "sample.docx",
      "placeholders": ["{{proc}}", "{{joints_3LinerPipe}}"]
    }

`filename` is resolved relative to TEMPLATES_DIR into the stored absolute
`file_path`. Upsert key is (damage_count, config_key).
"""

import os
import json
import logging

from .config import TEMPLATES_DIR, MANIFEST_NAME
from .models import Template

logger = logging.getLogger("webapp.registry")


def _read_manifest_entries():
    manifest_path = os.path.join(TEMPLATES_DIR, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        logger.warning("No manifest found at %s — registry not seeded.", manifest_path)
        return []
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("templates", [])
    if not isinstance(data, list):
        logger.warning("Manifest at %s is not a list/templates array.", manifest_path)
        return []
    return data


def seed_templates_from_manifest(db):
    """Upsert manifest entries into the templates table. Returns counts."""
    entries = _read_manifest_entries()
    created, updated = 0, 0

    for e in entries:
        try:
            damage_count = int(e["damage_count"])
            config_key = str(e["config_key"])
            name = str(e["name"])
            filename = str(e["filename"])
        except (KeyError, ValueError, TypeError) as ex:
            logger.warning("Skipping invalid manifest entry %r: %s", e, ex)
            continue

        file_path = os.path.join(TEMPLATES_DIR, filename)
        placeholders = e.get("placeholders")

        if not os.path.isfile(file_path):
            logger.warning("Template file missing for '%s': %s", name, file_path)

        existing = (
            db.query(Template)
            .filter_by(damage_count=damage_count, config_key=config_key)
            .one_or_none()
        )
        if existing:
            existing.name = name
            existing.file_path = file_path
            existing.placeholders = placeholders
            updated += 1
        else:
            db.add(Template(
                name=name,
                damage_count=damage_count,
                config_key=config_key,
                file_path=file_path,
                placeholders=placeholders,
            ))
            created += 1

    db.commit()
    logger.info("Registry seeded from manifest: %d created, %d updated.", created, updated)
    return {"created": created, "updated": updated}
