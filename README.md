# Well Tools

> A desktop toolkit for automating well-integrity report generation — turning raw WellSchematic XML and Excel inspection data into polished, ready-to-send Word reports.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="GUI" src="https://img.shields.io/badge/UI-Tkinter-FF6F00">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-555">
  <img alt="Status" src="https://img.shields.io/badge/status-active-success">
</p>

---

## Overview

**Well Tools** is a two-in-one GUI application that streamlines two recurring tasks in well-integrity reporting:

1. **Interval Generator** — parses a WellSchematic XML (plus an optional thickness sheet) and builds a clean depth-interval / pipe-summary table in Excel.
2. **Automation Report** — merges a Word `.docx` template with an Excel data workbook and a folder of images to produce a single, fully-populated report.

Everything runs locally through a simple tabbed desktop interface — no servers, no cloud, no manual copy-paste.

---

## Features

- 🧩 **Template-driven** — drop tags like `{{joints_<sheet>}}`, `{{highest_<sheet>}}`, or `{{proc}}` into a Word template and let the tool fill them in.
- 📊 **Smart "highest metal loss" tables** — always shows the top joints, and automatically expands to include **every** Class C (moderate) and Class D (intensive) joint when there are more than four.
- 🖼️ **Borderless image placement** — images are sized to fit their cells and given a clean, flush border drawn directly on the picture (no cell-padding gap).
- 🎨 **Grade-aware coloring** — cells are shaded by grade (A/B/C/D) to match the standard severity palette.
- 🖱️ **Drag & drop** — optional file/folder drag-and-drop (falls back to file-picker buttons if unavailable).
- 📦 **Single-file build** — ships as a standalone `WellTools.exe` via PyInstaller.

---

## Project Structure

```
ReportAutomation/
└── well_tools_1/
    ├── run.py                 # Double-click / PyInstaller entry point
    ├── build_exe.bat          # One-click Windows build script
    └── well_tools/
        ├── main.py            # App entry — builds the two-tab window
        ├── requirements.txt
        ├── core/              # Interval Generator logic
        │   ├── xml_parser.py      # WellSchematic XML parsing & pipe classification
        │   ├── intervals.py       # Builds the depth-interval table
        │   ├── thickness.py       # Optional THICKNESS sheet handling
        │   ├── formatting.py      # Shared value formatting
        │   └── excel_output.py    # Writes the "Raw Data" sheet
        ├── report/            # Automation Report logic
        │   ├── report_builder.py  # Orchestrates tables → images
        │   ├── tables.py          # Fills tagged tables from Excel
        │   └── images.py          # Places & borders tagged images
        └── ui/                # Tkinter interface
            ├── interval_tab.py
            ├── report_tab.py
            └── dnd.py             # Drag-and-drop helpers
```

---

## Installation

Requires **Python 3.9+**.

```bash
cd well_tools_1
pip install -r well_tools/requirements.txt
```

| Dependency      | Purpose                                   |
| --------------- | ----------------------------------------- |
| `pandas`        | Tabular data handling                     |
| `openpyxl`      | Reading/writing Excel workbooks           |
| `python-docx`   | Reading/writing Word documents            |
| `tkinterdnd2`   | *(optional)* drag-and-drop support        |

---

## Usage

### Run from source

```bash
cd well_tools_1
python -m well_tools.main
# or
python run.py
```

### Build a standalone executable (Windows)

```bat
cd well_tools_1
build_exe.bat
```

The result lands at `dist\WellTools.exe`.

---

## How the Automation Report works

The report builder takes three inputs:

| Input              | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| **Word template**  | A `.docx` with tagged tables and image placeholders.                        |
| **Excel data**     | A workbook whose sheets feed the tagged tables.                             |
| **Working folder** | Holds the images **and** receives the finished report. Images are read from `<dir>/IMGS` if that subfolder exists, otherwise from the folder itself. |

**Pipeline:** `tables.fill_report_tables()` populates every tagged table, then `images.place_report_images()` drops in and borders the images — both operating on a single output document.

### Supported tags

| Tag                     | Effect                                                              |
| ----------------------- | ------------------------------------------------------------------ |
| `{{joints_<sheet>}}`    | Fills a full joints table from columns A–J of `<sheet>`.           |
| `{{highest_<sheet>}}`   | Fills the highest-metal-loss table (top joints + all C/D joints).  |
| `{{SUMMARY}}`           | Cross-pipe summary table (one pre-built row per pipe). Fills, per row, the worst joint's Metal Loss (%), Grade (+ background color) and Max Loss Depth — columns 2–4. Column 1 (pipe name) is left untouched; rows are filled shallow→deep in the order the pipe tags appear. |
| `{{proc}}`, `{{wh}}`, … | Image placeholders, mapped to files in the working/IMGS folder.    |
| `{{DISC}}`              | First cell of a disclaimer table. If "Include disclaimer" is checked the tag is removed and the table is kept; otherwise the whole table is deleted. |
| `{{COMP}}`              | Company logo. Place it in a borderless 1×1 table (body) **and** set it as the **Alt Text** of the logo picture in each section header (Word → right-click image → Alt Text → Description). The logo chosen in the Company Manager fills the body table and replaces every header picture tagged this way. |

> **Company logos** are managed in the **Company Manager** (name + logo image), not the IMGS folder, and choosing one is required to generate a report.

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
