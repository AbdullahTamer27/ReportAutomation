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

1. **Report Automation** — merges a **universal** Word `.docx` template with an Excel data workbook and a folder of images to produce a single, fully-populated report (tables, pie charts, images, company branding, disclaimers, and well metadata). A configuration string adapts the one template to each well's pipe layout, and an optional schematic PDF pre-fills the well details.
2. **Interval Generator** — parses a WellSchematic XML (plus an optional thickness sheet) and writes a clean depth-interval / pipe-summary "Raw Data" sheet into an Excel template.
3. **Ghost Merger** — merges "ghost collar" intervals in a SmartLog Joint-Analysis CSV and exports a cleaned Excel.

**Template Manager** and **Company Manager** live *inside* Report Automation (they configure the templates and company logos it uses).

---

## Features

- 🧩 **Template-driven** — drop tags into a Word template (`{{joints_<sheet>}}`, `{{highest_<sheet>}}`, `{{SUMMARY}}`, `{{proc}}`, `{{COMP}}`, `{{well_name}}`, …) and let the tool fill them in.
- 🧱 **One universal template, any pipe layout** — a single master template adapts to the well via a **configuration string** (e.g. `18.625-13.375-9.625-7LNR-4.5TBG`). Pipe-specific sections are repeated or removed to match, so you don't maintain a template per configuration.
- 📊 **Smart "highest metal loss" tables** — always shows the top joints and auto-expands to include **every** Class C and Class D joint.
- 🧮 **Dynamic cross-pipe summary** — a `{{SUMMARY}}` table with **one header + one data row** is cloned per pipe at generation time (worst joint's metal loss, grade + color, max-loss depth), bottom-anchored so the first pipe lands in the last row.
- 🥧 **Per-pipe pie charts** — matplotlib-rendered metal-loss classification pies (A/B/C/D), placed into `{{pie_<role>}}` slots. Completion-affected joints (casing shoes / DVPs / annotated rows) are excluded from the counts, exactly like the tables.
- 📄 **Schematic-PDF pre-fill** — load a Well Cross Section Plot PDF to auto-fill the optional fields (well name, type, original completion, last workover) for review before generating.
- 🖼️ **Borderless image placement** — images are sized to fit their cells with a clean border drawn on the picture; damage photos scale by N damage points, via a repeatable block **or** static `{{DMGi_j}}` slots.
- 🏢 **Company branding** — pick a registered company; its logo fills the `{{COMP}}` body table **and** swaps the logo in every section header, while `{{COMPNAME}}` writes the name.
- 📝 **Well-metadata tags** — `{{well_name}}`, `{{well_type}}`, `{{btm_depth}}`, `{{field}}`, `{{log_date}}`, `{{orig_comp}}`, `{{last_wko}}`, plus an auto `{{delivery_date}}`, with dates normalized to `DD-Mon-YYYY` (e.g. `09-Sep-2020`).
- 📄 **Optional disclaimer** — a `{{DISC}}` table kept or removed via a checkbox.
- 🎨 **Grade-aware coloring** — cells shaded by grade (A/B/C/D) to match the standard severity palette.
- 🔎 **Report notes** — engine warnings (missing images, untagged headers, grade corrections, summary mismatches, config/Excel pipe-count mismatches) surface in the UI after each run.
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
            ├── pipe_config.py    # Parses the configuration string → pipe model
            ├── pipe_sections.py  # Repeats/removes per-pipe sections; cleans conclusion lines
            ├── tables.py         # Tagged tables (joints / highest / SUMMARY)
            ├── charts.py         # Per-pipe metal-loss pie charts (matplotlib)
            ├── schematic.py      # Extracts well metadata from a schematic PDF
            ├── damage_blocks.py  # Repeats the damage section N times
            ├── images.py         # Places & borders tagged images; removes unfilled slots
            ├── company.py        # Company logo (body + headers)
            ├── conditional.py    # Company-conditional lines (e.g. {{weatherford_corr}})
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
| `matplotlib`      | Per-pipe metal-loss pie charts                     |
| `pymupdf` / `docx2pdf` | PDF preview rendering (preview needs MS Word); `pymupdf` also reads schematic PDFs |

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
| **Template**       | The universal master template (managed in Template Manager).                |
| **Configuration**  | A string describing the well's pipes — required. Drives which pipe sections are kept and what the per-pipe tags resolve to. |
| **Company**        | Chosen from the dropdown (managed in Company Manager) — required.           |
| **Schematic PDF**  | *Optional* — a Well Cross Section Plot PDF; loading it pre-fills the well details below for review. |
| **Well details**   | Well name, type, bottom depth, field, dates, damage count, disclaimer toggle (all optional). |

**Pipeline** (`report_builder.build_automation_report`): keep/remove per-pipe sections (from the configuration) → fill tagged tables + dynamic summary → expand damage sections (×N) → keep/remove disclaimer → place & border images → place company logo + name → fill well-metadata text tags → company-conditional lines → render & place per-pipe pie charts (unfilled `{{pie_<role>}}` slots removed). Curated warnings are returned and shown as **Report notes** in the UI.

### Configuration string

Pipes are listed largest-to-smallest, separated by `-`. Each pipe is `size[(x|×)size][type]`, where `type` is `CSG` (default), `LNR`, or `TBG`, and the optional `×size` denotes a tapered string. Up to seven pipes map to the roles `firstPipe … seventhPipe`.

```
18.625-13.375-9.625-7LNR-4.5x3.5TBG
```

Each role exposes tags (`{{firstPipe_name}}`, `{{firstPipe_suffix}}`, `{{firstPipe_shoe}}`, `{{firstPipe_highest_grade}}`, `{{pie_firstPipe}}`) and a repeatable/removable section bounded by `{{firstPipe_start}}` … `{{firstPipe_end}}`. Roles not present in the configuration have their section and any leftover tag-lines removed automatically. If the configuration lists more pipes than the workbook has sheets, **Generate** is blocked; the reverse only warns.

### Output filename

Reports are named `wellname_logdate_EPDT_RIGLESS_REPORT_companyname.docx` (missing parts become `NA`).

### Schematic PDF extraction

`schematic.py` reads a Well Cross Section Plot PDF and pre-fills the optional fields for review:

| Field | Source | Example |
| ----- | ------ | ------- |
| Well name | line above `WB :N of M`, dashes → underscores + wellbore number | `ZULF-65` → `ZULF_65_0` |
| Original completion | `ORIGINAL COMP.:` | `1981/07/13` → `13-Jul-1981` |
| Last workover | `LATEST WKO :` (with the `#N` workover count) | `2013/09/06 #4` → `06-Sep-2013 #4` |
| Well type | `WELLBORE TYPE :` | `KHFJ OIL (WET) PRODUCER` |

Bottom depth and log date are left blank (not reliably present in the schematic).

### Supported tags

| Tag                     | Effect                                                              |
| ----------------------- | ------------------------------------------------------------------ |
| `{{joints_<sheet>}}`    | Fills a full joints table from columns A–J of `<sheet>`.           |
| `{{highest_<sheet>}}`   | Fills the highest-metal-loss table (top joints + all C/D joints).  |
| `{{SUMMARY}}`           | Cross-pipe summary table. Author it with **one header row + one data row**; the data row is cloned per pipe at generation time. Fills, per row, the worst joint's Metal Loss (%), Grade (+ background color) and Max Loss Depth — columns 2–4. Column 1 (pipe suffix) is filled too; rows fill bottom-anchored (first pipe → last row). |
| `{{<role>_start}}` … `{{<role>_end}}` | Bounds a per-pipe section (`role` = `firstPipe … seventhPipe`). Kept (markers stripped) if the pipe exists, removed entirely if not. |
| `{{<role>_name}}` / `{{<role>_suffix}}` | Pipe name / sized suffix, e.g. `7"` / `7" LNR`. |
| `{{<role>_shoe}}`       | Pipe shoe depth (max Bottom Body from its sheet).                  |
| `{{<role>_highest_grade}}` | Worst-grade severity word: **Light** (A), **Minor** (B), **Moderate** (C), **Intensive** (D). |
| `{{pie_<role>}}`        | Alt Text of a placeholder picture → replaced by that pipe's metal-loss pie chart. Unfilled slots (absent pipes) are removed. |
| `{{casings}}` / `{{liners}}` / `{{tubings}}` | Comma-separated list of sizes for that pipe type, largest first. |
| `{{proc}}`, `{{wh}}`, … | Image placeholders (`proc`, `tempgr`, `wh`, `raw`, `well`, `ts`), mapped to files in the working/IMGS folder. |
| `{{DMG<i>_<j>}}`        | Damage photos — 3 per damage point (`DMG1_1…DMG1_3`, `DMG2_1`, …). Use a repeatable `{{damage_block_start}}`/`{{damage_block_end}}` block **or** static `{{DMGi_j}}` slots. |
| `{{DISC}}`              | First cell of a disclaimer table. Checked → tag removed, table kept; unchecked → whole table deleted. |
| `{{COMP}}`              | Company logo. Put it in a borderless 1×1 table (body) **and** set it as the **Alt Text** of the logo picture in each section header (Word → right-click image → Alt Text → Description). |
| `{{COMPNAME}}`          | Company name as text (body / headers / footers).                   |
| `{{well_name}}`         | Well name (also used for the output filename).                     |
| `{{well_type}}`         | Well type (e.g. "Oil producer").                                   |
| `{{btm_depth}}`         | Bottom depth (e.g. "7233 ft").                                     |
| `{{field}}`             | Field name (e.g. "Zuluf").                                         |
| `{{log_date}}`, `{{orig_comp}}`, `{{last_wko}}` | Dates, normalized to `DD-Mon-YYYY` (non-dates like `N/A` pass through). |
| `{{delivery_date}}`     | Auto-filled with today's date in `DD-Mon-YYYY`.                    |

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
