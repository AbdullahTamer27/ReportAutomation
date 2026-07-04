# Talos.spec
# PyInstaller spec — one-dir build for the Talos desktop web app.
#
# Run from the well_tools_1/ directory (where this file lives):
#   pyinstaller --clean --noconfirm Talos.spec
#
# Output: dist/Talos/Talos.exe  (+ _internal/ with all dependencies)

import os
import sys
import glob

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect pywebview and PyMuPDF fully — they embed DLLs / data that
# the standard analysis misses.
wv_data,  wv_bins,  wv_hidden  = collect_all("webview")
fitz_data, fitz_bins, fitz_hidden = collect_all("fitz")

# matplotlib renders the per-pipe metal-loss pie charts (well_tools/report/
# charts.py). Collect its mpl-data (fonts, rcParams) so the Agg backend works
# in the frozen build — without this the EXE crashes the first time it draws.
mpl_data, mpl_bins, mpl_hidden = collect_all("matplotlib")

# certifi ships the CA bundle the self-updater verifies TLS against. Collect its
# cacert.pem so certifi.where() resolves inside the frozen exe — without it,
# HTTPS to GitHub fails with CERTIFICATE_VERIFY_FAILED (update download breaks).
certifi_data, certifi_bins, certifi_hidden = collect_all("certifi")

# pywin32 system DLLs (pythoncom3X.dll, pywintypes3X.dll) must be in the
# bundle root so Windows COM infrastructure can find them at run-time.
# Without this, docx2pdf silently fails when launched from the frozen EXE.
_pywin32_sysdir = os.path.join(
    sys.prefix, "Lib", "site-packages", "pywin32_system32"
)
_pywin32_dlls = [
    (dll, ".")                        # place DLLs at the _internal/ root
    for dll in glob.glob(os.path.join(_pywin32_sysdir, "*.dll"))
]

block_cipher = None

a = Analysis(
    ["webapp/app.py"],
    pathex=["."],                    # well_tools_1/ — finds both packages
    binaries=wv_bins + fitz_bins + mpl_bins + certifi_bins + _pywin32_dlls,
    datas=[
        # Static frontend served by FastAPI
        ("webapp/static",           "webapp/static"),
        # Bundled template folder (manifest.json + .docx files)
        ("webapp/data/templates",   "webapp/data/templates"),
        # Bundled company-logos folder (manifest.json + logo images)
        ("webapp/data/companies",   "webapp/data/companies"),
    ] + wv_data + fitz_data + mpl_data + certifi_data,
    hiddenimports=(
        wv_hidden + fitz_hidden + mpl_hidden + certifi_hidden
        + collect_submodules("well_tools")   # engine + core
        + collect_submodules("sqlalchemy")
        + [
            # SQLAlchemy SQLite dialect
            "sqlalchemy.dialects.sqlite",
            "sqlalchemy.dialects.sqlite.pysqlite",
            "sqlalchemy.sql.default_comparator",
            # Uvicorn internals (not always auto-detected)
            "uvicorn.logging",
            "uvicorn.loops",
            "uvicorn.loops.auto",
            "uvicorn.protocols",
            "uvicorn.protocols.http",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.websockets",
            "uvicorn.protocols.websockets.auto",
            "uvicorn.lifespan",
            "uvicorn.lifespan.on",
            "uvicorn.config",
            # ASGI / async
            "anyio",
            "anyio._backends._asyncio",
            # docx2pdf → COM / pywin32
            "docx2pdf",
            "win32com",
            "win32com.client",
            "pywintypes",
            "pythoncom",
            # lxml (python-docx dependency)
            "lxml.etree",
            "lxml._elementpath",
            "lxml.objectify",
            # openpyxl / pandas
            "openpyxl",
            "openpyxl.cell._writer",
            "pandas",
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_pywin32.py"],
    excludes=[
        "tkinter", "_tkinter",      # desktop Tkinter UI — not used by the web app
        "scipy",                    # matplotlib draws the pies but never needs scipy
        "IPython", "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,         # onefile: bundle all DLLs / binaries into the EXE
    a.zipfiles,
    a.datas,            # onefile: bundle static frontend + templates into the EXE
    [],
    name="Talos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX can trigger antivirus false-positives; keep off
    runtime_tmpdir=None,  # unpack to the OS temp dir at launch
    console=False,        # no terminal window — change to True to see server logs
    icon="talos.ico",     # Talos sentinel-helm mark (built from static/img/talos-icon.svg)
)

# NOTE: one-file build. Output is a single dist/Talos.exe.
# (Previous one-dir COLLECT removed.) The exe still requires the Edge WebView2
# runtime (UI) and Microsoft Word (PDF preview) on the target machine — those
# are external apps and cannot be embedded into the executable.
