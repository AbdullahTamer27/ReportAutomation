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
import re
import json
import shutil
import logging
from datetime import datetime

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


# ------------------------------------------------------------------ runtime ops

def _safe_stem(config_key: str) -> str:
    """Turn a config key into a safe, filesystem-friendly filename stem."""
    s = config_key.replace("×", "x").replace(" ", "_")
    s = re.sub(r"[^\w\-.]", "_", s)
    return s.strip("._") or "template"


def update_manifest(db) -> None:
    """Rewrite TEMPLATES_DIR/manifest.json from the current DB contents.
    Called after any register/delete so the file always stays in sync."""
    rows = db.query(Template).order_by(Template.config_key).all()
    entries = []
    for t in rows:
        entries.append({
            "name": t.name,
            "damage_count": t.damage_count,
            "config_key": t.config_key,
            "filename": os.path.basename(t.file_path),
            "placeholders": t.placeholders or [],
        })
    manifest_path = os.path.join(TEMPLATES_DIR, MANIFEST_NAME)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"templates": entries}, f, indent=2, ensure_ascii=False)
    logger.info("manifest.json written (%d entries).", len(entries))


def register_template(db, name: str, config_key: str, source_path: str) -> Template:
    """Copy `source_path` into TEMPLATES_DIR and upsert the template in DB +
    manifest. If a template with the same config_key already exists it is
    updated (file overwritten, name refreshed). Returns the saved Template row."""
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")
    if not source_path.lower().endswith(".docx"):
        raise ValueError("Template must be a .docx file.")

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    # Choose destination filename from config_key, avoid collisions.
    stem = _safe_stem(config_key)
    dest_filename = f"{stem}.docx"
    dest_path = os.path.join(TEMPLATES_DIR, dest_filename)

    # If the file already exists and belongs to a DIFFERENT config, add suffix.
    counter = 1
    while os.path.exists(dest_path):
        occupant = db.query(Template).filter_by(file_path=dest_path).one_or_none()
        if occupant is None or occupant.config_key == config_key:
            break  # safe to overwrite
        dest_filename = f"{stem}_{counter}.docx"
        dest_path = os.path.join(TEMPLATES_DIR, dest_filename)
        counter += 1

    shutil.copy2(source_path, dest_path)
    logger.info("Template file copied: %s -> %s", source_path, dest_path)

    # Upsert in DB (key: config_key with damage_count=0).
    existing = (
        db.query(Template)
        .filter_by(config_key=config_key, damage_count=0)
        .one_or_none()
    )
    if existing:
        existing.name = name
        existing.file_path = dest_path
        existing.updated_at = datetime.utcnow()
        logger.info("Template updated: '%s' (%s)", name, config_key)
    else:
        existing = Template(
            name=name,
            damage_count=0,
            config_key=config_key,
            file_path=dest_path,
            placeholders=None,
        )
        db.add(existing)
        logger.info("Template registered: '%s' (%s)", name, config_key)

    db.commit()
    db.refresh(existing)
    update_manifest(db)
    return existing


def delete_template(db, template_id: int, remove_file: bool = False) -> bool:
    """Delete a template from the DB (and optionally its file from disk).
    Returns True if found and deleted, False if not found."""
    t = db.get(Template, template_id)
    if t is None:
        return False
    file_path = t.file_path
    db.delete(t)
    db.commit()
    if remove_file and file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
            logger.info("Template file removed: %s", file_path)
        except OSError as e:
            logger.warning("Could not remove template file %s: %s", file_path, e)
    update_manifest(db)
    return True
