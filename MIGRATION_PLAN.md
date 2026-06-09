# Migration Plan — Tkinter Desktop → Local-First Web App

This document captures the target architecture for migrating the well-integrity
report-automation tool from its Tkinter desktop UI to a local-first web app
packaged as a double-click Windows `.exe`. It exists so future sessions have the
full context without re-deriving it.

## Guiding principle

**The report ENGINE stays as-is.** The new app calls it; it does not rewrite it.

- Engine entry point: `well_tools/report/report_builder.py` →
  `build_automation_report(word_template_path, excel_data_path, working_dir, output_path=None, highest_top_n=4, progress=None, review=None)`
- Engine helpers (also untouched): `well_tools/report/tables.py`, `well_tools/report/images.py`
- The existing Tkinter UI (`well_tools/ui/…`, `well_tools/main.py`, `run.py`)
  **stays runnable**. The web app is built alongside it. Tkinter is retired only
  once the web version is proven.

## Target architecture

| Layer | Choice |
|-------|--------|
| **Frontend** | Vanilla HTML + ES modules + `fetch()`. No framework, no build step. |
| **Backend** | FastAPI + Uvicorn. Serves both the JSON API and the static frontend. |
| **Report history** | Local SQLite via SQLAlchemy. |
| **Templates** | Word `.docx` templates stored as files in a templates dir with a `manifest.json` registry. The dir path is configurable (future: a shared network drive). |
| **DOCX → PDF** | `docx2pdf` (Word is installed on all target machines). |
| **PDF → PNG preview** | PyMuPDF (`fitz`). Rendered after the form is submitted — not live/reactive. |
| **Native window** | `pywebview` wrapping the local server. |
| **Packaging** | PyInstaller → single Windows `.exe`. |

## Per-job inputs

- **Word template**: chosen from the registry (a dropdown populated from `manifest.json`).
- **Excel data file**: picked by the user per job.
- **Working directory**: picked by the user per job (holds images in `IMGS/` or the
  dir itself, and is where the report is written — same contract as today).

## Package layout

```
well_tools_1/
├── well_tools/          # EXISTING engine + Tkinter UI — do not modify the engine
│   ├── report/          # report_builder.py, tables.py, images.py  (the engine)
│   ├── core/            # interval-generator logic
│   └── ui/              # Tkinter UI (stays runnable)
├── webapp/              # NEW web app package (this migration)
│   ├── main.py          # FastAPI app + routes
│   └── requirements.txt # web app deps (+ engine deps)
└── run.py               # existing Tkinter entry point (unchanged)
```

The `webapp` package sits **alongside** `well_tools` so it can
`from well_tools.report.report_builder import build_automation_report` while the
engine continues to import and run independently.

## Phased delivery

- **Phase 1 (this session):** FastAPI app with one endpoint
  `POST /api/report/generate` that accepts `{word_template_path, excel_path,
  working_dir}`, calls `build_automation_report`, and returns the output `.docx`
  path (or a clean error). Engine `progress`/`review` callbacks are routed to
  server logs. No frontend, DB, preview, or packaging yet.
- **Phase 2:** Vanilla HTML/JS frontend + static serving; the generate form.
- **Phase 3:** SQLite report history (SQLAlchemy); templates registry + `manifest.json`.
- **Phase 4:** DOCX→PDF (`docx2pdf`) and PDF→PNG preview (PyMuPDF) after submit.
- **Phase 5:** `pywebview` native window + PyInstaller `.exe` packaging.

## Notes / open considerations

- **Concurrency & temp files:** as inputs move to uploads later, give each job an
  isolated working dir and clean up artifacts so the machine doesn't fill up.
- **Path config:** the templates dir path must be overridable (env var / config)
  to point at a shared network drive in the future.
- **Engine contract is the seam:** `progress`/`review` callbacks are the streaming
  hook; the web app currently logs them and can later stream them to the page.
