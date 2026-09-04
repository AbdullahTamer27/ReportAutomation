"""Web app configuration.

All paths are derived here so they have a single source of truth.

Two distinct roots matter once the app is frozen by PyInstaller (especially in
one-file mode):

  * Read-only bundled resources (templates shipped inside the EXE) are extracted
    to ``sys._MEIPASS`` — a TEMP folder that is wiped when the app exits.
  * Writable data (the SQLite DB, the PDF-preview cache, and any templates the
    user adds via the Template Manager) must live somewhere permanent, or it is
    lost every time the app closes. We use ``%APPDATA%\\Talos`` on Windows.

In dev (not frozen) both roots collapse back to ``webapp/data/`` as before, so
nothing about the development workflow changes.
"""

import os
import sys

# webapp/ source directory
HERE = os.path.dirname(os.path.abspath(__file__))

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # Read-only resources bundled into the EXE (see datas= in Talos.spec).
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # Writable, persistent app data — survives across runs and rebuilds.
    _APP_HOME = os.environ.get("APPDATA") or os.path.expanduser("~")
    DATA_DIR = os.path.join(_APP_HOME, "Talos")
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

# Company logos directory — managed like templates (a folder + manifest.json,
# editable from the Company Manager UI).
COMPANIES_DIR = os.environ.get("COMPANIES_DIR", os.path.join(DATA_DIR, "companies"))

# Registry file inside TEMPLATES_DIR / COMPANIES_DIR.
MANIFEST_NAME = "manifest.json"

# --- Read-only bundled paths -------------------------------------------------
# Templates baked into the EXE, used to seed TEMPLATES_DIR on first run. In dev
# this points at the same folder as TEMPLATES_DIR, so seeding is a no-op.
if _FROZEN:
    BUNDLED_TEMPLATES_DIR = os.path.join(BUNDLE_DIR, "webapp", "data", "templates")
    BUNDLED_COMPANIES_DIR = os.path.join(BUNDLE_DIR, "webapp", "data", "companies")
    _OPS_DIR = os.path.join(BUNDLE_DIR, "webapp", "data", "ops")
else:
    BUNDLED_TEMPLATES_DIR = os.path.join(HERE, "data", "templates")
    BUNDLED_COMPANIES_DIR = os.path.join(HERE, "data", "companies")
    _OPS_DIR = os.path.join(HERE, "data", "ops")

# The one-page-summary workbook. Unlike the report templates this is a fixed
# part of the engine: read-only, never copied into DATA_DIR, and never listed by
# the Template Manager — so it cannot be swapped or deleted by a user, and
# changing it means shipping a new build. The env var is an escape hatch for
# working on the design without cutting a release; nothing in the UI exposes it.
def _ops_template():
    """The bundled OPS workbook. Either extension is accepted: the authored file
    is macro-enabled, and whether the macros are kept is not worth a rename."""
    for name in ("OPS.xlsx", "OPS.xlsm"):
        path = os.path.join(_OPS_DIR, name)
        if os.path.isfile(path):
            return path
    return os.path.join(_OPS_DIR, "OPS.xlsx")


OPS_TEMPLATE_PATH = os.environ.get("OPS_TEMPLATE") or _ops_template()


def ensure_user_data():
    """Create the writable data dirs and, on first run of a frozen build, seed
    the user's templates folder from the read-only bundle.

    Idempotent and a no-op in dev (bundle and user templates are the same dir).
    """
    import shutil

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(COMPANIES_DIR, exist_ok=True)

    def _seed(bundled_dir, user_dir):
        # Dev mode (or a custom dir that already is the bundle): nothing to copy.
        if os.path.abspath(bundled_dir) == os.path.abspath(user_dir):
            return
        # Already seeded — leave the user's files untouched.
        if os.path.exists(os.path.join(user_dir, MANIFEST_NAME)):
            return
        if not os.path.isdir(bundled_dir):
            return
        for entry in os.listdir(bundled_dir):
            src = os.path.join(bundled_dir, entry)
            dst = os.path.join(user_dir, entry)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

    _seed(BUNDLED_TEMPLATES_DIR, TEMPLATES_DIR)
    _seed(BUNDLED_COMPANIES_DIR, COMPANIES_DIR)
