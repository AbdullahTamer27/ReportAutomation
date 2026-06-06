"""Web app configuration.

All paths are derived here so they have a single source of truth.

Two distinct roots matter once the app is frozen by PyInstaller (especially in
one-file mode):

  * Read-only bundled resources (templates shipped inside the EXE) are extracted
    to ``sys._MEIPASS`` — a TEMP folder that is wiped when the app exits.
  * Writable data (the SQLite DB, the PDF-preview cache, and any templates the
    user adds via the Template Manager) must live somewhere permanent, or it is
    lost every time the app closes. We use ``%APPDATA%\\WellTools`` on Windows.

In dev (not frozen) both roots collapse back to ``webapp/data/`` as before, so
nothing about the development workflow changes.
"""

import os
import sys

# webapp/ source directory
HERE = os.path.dirname(os.path.abspath(__file__))

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # Read-only resources bundled into the EXE (see datas= in WellTools.spec).
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # Writable, persistent app data — survives across runs and rebuilds.
    _APP_HOME = os.environ.get("APPDATA") or os.path.expanduser("~")
    DATA_DIR = os.path.join(_APP_HOME, "WellTools")
else:
    BUNDLE_DIR = HERE
    DATA_DIR = os.path.join(HERE, "data")

# --- Writable paths ----------------------------------------------------------
DB_PATH = os.path.join(DATA_DIR, "app.db")

# SQLite by default; overridable via DATABASE_URL.
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# The one knob that future-proofs templates for a shared network drive.
# Default: <DATA_DIR>/templates/  (writable — the Template Manager copies new
# .docx files here and rewrites manifest.json).
TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", os.path.join(DATA_DIR, "templates"))

# Registry file inside TEMPLATES_DIR.
MANIFEST_NAME = "manifest.json"

# --- Read-only bundled paths -------------------------------------------------
# Templates baked into the EXE, used to seed TEMPLATES_DIR on first run. In dev
# this points at the same folder as TEMPLATES_DIR, so seeding is a no-op.
if _FROZEN:
    BUNDLED_TEMPLATES_DIR = os.path.join(BUNDLE_DIR, "webapp", "data", "templates")
else:
    BUNDLED_TEMPLATES_DIR = os.path.join(HERE, "data", "templates")


def ensure_user_data():
    """Create the writable data dirs and, on first run of a frozen build, seed
    the user's templates folder from the read-only bundle.

    Idempotent and a no-op in dev (bundle and user templates are the same dir).
    """
    import shutil

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    # Dev mode (or a custom TEMPLATES_DIR that already is the bundle): nothing to copy.
    if os.path.abspath(BUNDLED_TEMPLATES_DIR) == os.path.abspath(TEMPLATES_DIR):
        return

    # Already seeded — leave the user's templates untouched.
    if os.path.exists(os.path.join(TEMPLATES_DIR, MANIFEST_NAME)):
        return

    if not os.path.isdir(BUNDLED_TEMPLATES_DIR):
        return

    for entry in os.listdir(BUNDLED_TEMPLATES_DIR):
        src = os.path.join(BUNDLED_TEMPLATES_DIR, entry)
        dst = os.path.join(TEMPLATES_DIR, entry)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
