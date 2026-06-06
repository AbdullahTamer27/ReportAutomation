"""Web app configuration.

All paths are derived here so they have a single source of truth. TEMPLATES_DIR
is intentionally a single env-configurable constant so it can later point at a
shared network drive with no code change.
"""

import os

# webapp/ directory
HERE = os.path.dirname(os.path.abspath(__file__))

# Local data lives under webapp/data/
DATA_DIR = os.path.join(HERE, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")

# SQLite by default; overridable via DATABASE_URL.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# The one knob that future-proofs templates for a shared network drive.
# Default: webapp/data/templates/
TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", os.path.join(DATA_DIR, "templates"))

# Registry file inside TEMPLATES_DIR.
MANIFEST_NAME = "manifest.json"
