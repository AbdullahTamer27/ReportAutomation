# Well Tools

> A desktop toolkit for automating well-integrity reporting — turning WellSchematic XML, Excel inspection data, and a folder of images into polished, ready-to-send Word reports.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="API" src="https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="UI" src="https://img.shields.io/badge/UI-Web%20%2B%20pywebview-7c8cff">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-555">
  <img alt="Status" src="https://img.shields.io/badge/status-active-success">
</p>

---

## Overview

**Well Tools** runs as a native desktop window backed by a local web app (FastAPI + a vanilla-JS frontend in a [pywebview](https://pywebview.flowrl.com/) shell). Everything runs locally — no servers, no cloud, no manual copy-paste — and ships as a single `WellTools.exe`.

It bundles three standalone tools:

1. **Report Automation** — merges a Word `.docx` template with an Excel data workbook and a folder of images to produce a single, fully-populated report (tables, images, company branding, disclaimers, and well metadata).
2. **Interval Generator** — parses a WellSchematic XML (plus an optional thickness sheet) and writes a clean depth-interval / pipe-summary "Raw Data" sheet into an Excel template.
3. **Ghost Merger** — merges "ghost collar" intervals in a SmartLog Joint-Analysis CSV and exports a cleaned Excel.

**Template Manager** and **Company Manager** live *inside* Report Automation (they configure the templates and company logos it uses).

---

## Features

- 🧩 **Template-driven** — drop tags into a Word template (`{{joints_<sheet>}}`, `{{highest_<sheet>}}`, `{{SUMMARY}}`, `{{proc}}`, `{{COMP}}`, `{{well_name}}`, …) and let the tool fill them in.
- 📊 **Smart "highest metal loss" tables** — always shows the top joints and auto-expands to include **every** Class C and Class D joint.
- 🧮 **Cross-pipe summary** — a `{{SUMMARY}}` table fills the worst joint per pipe (metal loss, grade + color, max-loss depth) into a pre-built per-config table.
- 🖼️ **Borderless image placement** — images are sized to fit their cells with a clean border drawn on the picture; damage photos scale by N damage points.
- 🏢 **Company branding** — pick a registered company; its logo fills the `{{COMP}}` body table **and** swaps the logo in every section header, while `{{COMPNAME}}` writes the name.
- 📝 **Well-metadata tags** — `{{well_name}}`, `{{well_type}}`, `{{btm_depth}}`, `{{log_date}}`, `{{orig_comp}}`, `{{last_wko}}`, with dates normalized to `DD-Mon-YYYY` (e.g. `09-Sep-2020`).
- 📄 **Optional disclaimer** — a `{{DISC}}` table kept or removed via a checkbox.
- 🎨 **Grade-aware coloring** — cells shaded by grade (A/B/C/D) to match the standard severity palette.
- 🔎 **Report notes** — engine warnings (missing images, untagged headers, grade corrections, summary mismatches) surface in the UI after each run.
- 👁️ **PDF preview** — generated reports render to page images in-app (requires Microsoft Word for the conversion).
- 📦 **Single-file build** — ships as a standalone `WellTools.exe` via PyInstaller, with persistent data in `%APPDATA%\WellTools`.

---

## Project Structure

```
ReportAutomation/
└── well_tools_1/
    ├── run.py                    # Legacy tkinter entry point
    ├── WellTools.spec            # PyInstaller spec (single-file EXE)
    ├── build_webapp.bat          # One-click Windows build
    ├── webapp/                   # Web app (primary UI)
    │   ├── app.py                # pywebview launcher (native window + file dialogs)
    │   ├── main.py               # FastAPI app: report / interval / ghost / managers
    │   ├── interval.py           # Interval Generator service
    │   ├── ghost.py              # Ghost Merger service
    │   ├── preview.py            # DOCX → PDF → PNG preview
    │   ├── registry.py           # Template + Company registries (folder + manifest + DB)
    │   ├── models.py / db.py / config.py
    │   ├── static/               # index.html · app.js · style.css
    │   └── data/                 # templates/ · companies/ · app.db · outputs/
    └── well_tools/
        ├── main.py               # Legacy tkinter two-tab window
        ├── core/                 # Interval Generator logic
        │   ├── xml_parser.py · intervals.py · thickness.py
        │   ├── formatting.py · excel_output.py
        └── report/               # Automation Report engine
            ├── report_builder.py # Orchestrates the pipeline
            ├── tables.py         # Tagged tables (joints / highest / SUMMARY)
            ├── damage_blocks.py  # Repeats the damage section N times
            ├── images.py         # Places & borders tagged images
            ├── company.py        # Company logo (body + headers)
            ├── disclaimer.py     # {{DISC}} keep/remove
            └── text_fields.py    # Run-preserving text-tag replacement
```

> The `well_tools/` engine is UI-agnostic; both the web app and the legacy tkinter app drive it. New features live in the web app.

---

## Installation

Requires **Python 3.9+**.

```bash
cd well_tools_1
pip install -r webapp/requirements.txt
```

| Dependency        | Purpose                                            |
| ----------------- | -------------------------------------------------- |
| `fastapi` / `uvicorn` | Local API + server                             |
| `pywebview`       | Native desktop window                              |
| `sqlalchemy`      | Template / company registry + run history          |
| `python-docx`     | Reading/writing Word documents                     |
| `openpyxl`        | Reading/writing Excel workbooks                    |
| `pandas`          | Interval + ghost-merge data handling               |
| `lxml`            | Low-level docx XML (image borders, headers)        |
| `pymupdf` / `docx2pdf` | PDF preview rendering (preview needs MS Word) |

---

## Usage

### Run the app (native window)

```bash
cd well_tools_1
python -m webapp.app
```

### Run the API / browser dev mode

```bash
cd well_tools_1
uvicorn webapp.main:app --reload     # then open http://127.0.0.1:8000/
```

> Native "Choose file…" dialogs only work in the desktop window (`python -m webapp.app`); the browser mode is for API work.

### Build a standalone executable (Windows)

```bat
cd well_tools_1
build_webapp.bat
```

The result lands at `dist\WellTools.exe`. On first run it seeds bundled templates and company logos into `%APPDATA%\WellTools`.

---

## How the Automation Report works

Report Automation takes:

| Input              | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| **Excel data**     | A workbook whose sheets feed the tagged tables (one `…Pipe` sheet per pipe).|
| **Working folder** | Holds the images **and** receives the finished report. Images are read from `<dir>/IMGS` if present, otherwise the folder itself. |
| **Template**       | Chosen by **Configuration** (managed in Template Manager).                  |
| **Company**        | Chosen from the dropdown (managed in Company Manager) — required.           |
| **Well details**   | Well name, type, bottom depth, dates, damage count, disclaimer toggle.      |

**Pipeline** (`report_builder.build_automation_report`): fill tagged tables → expand damage sections (×N) → keep/remove disclaimer → place & border images → place company logo + name → fill well-metadata text tags. Curated warnings are returned and shown as **Report notes** in the UI.

### Supported tags

| Tag                     | Effect                                                              |
| ----------------------- | ------------------------------------------------------------------ |
| `{{joints_<sheet>}}`    | Fills a full joints table from columns A–J of `<sheet>`.           |
| `{{highest_<sheet>}}`   | Fills the highest-metal-loss table (top joints + all C/D joints).  |
| `{{SUMMARY}}`           | Cross-pipe summary table (one pre-built row per pipe). Fills, per row, the worst joint's Metal Loss (%), Grade (+ background color) and Max Loss Depth — columns 2–4. Column 1 (pipe name) is left untouched; rows fill bottom-anchored (first pipe → last row). |
| `{{proc}}`, `{{wh}}`, … | Image placeholders (`proc`, `tempgr`, `wh`, `raw`, `well`, `ts`), mapped to files in the working/IMGS folder. |
| `{{DMG<i>_<j>}}`        | Damage photos — 3 per damage point (`DMG1_1…DMG1_3`, `DMG2_1`, …). |
| `{{DISC}}`              | First cell of a disclaimer table. Checked → tag removed, table kept; unchecked → whole table deleted. |
| `{{COMP}}`              | Company logo. Put it in a borderless 1×1 table (body) **and** set it as the **Alt Text** of the logo picture in each section header (Word → right-click image → Alt Text → Description). |
| `{{COMPNAME}}`          | Company name as text (body / headers / footers).                   |
| `{{well_name}}`         | Well name (also used for the output filename).                     |
| `{{well_type}}`         | Well type (e.g. "Oil producer").                                   |
| `{{btm_depth}}`         | Bottom depth (e.g. "7233 ft").                                     |
| `{{log_date}}`, `{{orig_comp}}`, `{{last_wko}}` | Dates, normalized to `DD-Mon-YYYY` (non-dates like `N/A` pass through). |

> Text tags (`{{COMPNAME}}`, `{{well_name}}`, …) are replaced **run-preserving**, so a tag in the middle of a styled paragraph won't restyle the surrounding text. Company logos and templates are managed in the **Company Manager** / **Template Manager** (inside Report Automation), not the IMGS folder.

---

## License

Released under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026 Well Tools

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
