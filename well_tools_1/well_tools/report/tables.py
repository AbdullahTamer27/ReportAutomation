"""Automation-report table filling.

Fills tables in a Word template from an Excel workbook, driven by tags placed
in each table's top-left header cell:

    {{joints_<sheet>}}   -> columns A..J (1..10)  of <sheet>
    {{highest_<sheet>}}  -> columns P..Y (16..25) of <sheet>, top N rows

Behavior is unchanged from the original script; it has only been turned into a
callable (`fill_report_tables`) so the report builder / UI can drive it, with
`print` routed through a `progress` callback.
"""

import re
import copy

import openpyxl
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import RGBColor, Pt

# ---------------- Settings ----------------
GRADE_COLORS = {"A": "FFFF00", "B": "FFC000", "C": "0070C0", "D": "FF0000"}
ROUND = {1: 1, 2: 1, 3: 1, 4: 3, 5: 3, 6: 1, 7: 1}

JOINTS_TAG = re.compile(r"\{\{joints_(\w+)\}\}")
HIGHEST_TAG = re.compile(r"\{\{highest_(\w+)\}\}")

HIGHEST_TOP_N = 4   # how many rows in the highest-loss tables


# ---------------- Excel reading ----------------
def read_table_block(ws, cols, start_col_for_hashcheck):
    """Read rows for a set of 1-based column indices. cols is a list of 10 column
    indices (the A..J-equivalent block). Stops when the '#' column stops being numeric."""
    rows = []
    hash_col = cols[0]
    for r in range(2, ws.max_row + 1):
        a = ws.cell(row=r, column=hash_col).value
        if not isinstance(a, (int, float)):
            if rows:
                break
            continue
        rows.append([ws.cell(row=r, column=c).value for c in cols])
    return rows


def read_joints(ws):
    # columns A..J = 1..10
    return read_table_block(ws, list(range(1, 11)), 1)


def read_highest(ws, top_n):
    # columns P..Y = 16..25  (P=#, Q..Y = the 10-col block; Z=rank ignored)
    # The block is pre-ranked by severity, so the worst joints sit at the top.
    # Show at least `top_n` rows, but if there are more than `top_n` joints graded
    # C (moderate) or D (intensive), extend the table to include all of them.
    rows = read_table_block(ws, list(range(16, 26)), 16)
    # Grade is column index 8 within each 10-col block.
    cd_count = sum(1 for v in rows if str(v[8]).strip() in ("C", "D"))
    n = max(top_n, cd_count)
    return rows[:n]


def is_excluded(vals):
    return not isinstance(vals[5], (int, float))


def fmt(val, idx):
    if val is None:
        return ""
    if isinstance(val, (int, float)) and idx in ROUND:
        return f"{val:.{ROUND[idx]}f}"
    return str(val)


# ---------------- Word helpers ----------------
def hex_to_rgb(h):
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def clear_cell_shading(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for shd in tcPr.findall(qn('w:shd')):
        tcPr.remove(shd)


def set_cell_bg(cell, hexc):
    clear_cell_shading(cell)
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), hexc)
    tcPr.append(shd)


def set_cell_font_color(cell, hexc):
    rgb = hex_to_rgb(hexc)
    for p in cell.paragraphs:
        for run in p.runs:
            run.font.color.rgb = rgb


def set_cell_text(cell, text):
    p = cell.paragraphs[0]
    if p.runs:
        p.runs[0].text = text
        for run in p.runs[1:]:
            run.text = ""
    else:
        p.add_run(text)


def clear_cell_paragraphs(cell):
    for p in cell.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    first = cell.paragraphs[0]
    for run in first.runs:
        run.text = ""
    return first


def reset_cell(cell):
    set_cell_text(cell, "")
    clear_cell_shading(cell)


def clone_row(table, template_row):
    new_tr = copy.deepcopy(template_row._tr)
    table._tbl.append(new_tr)
    return table.rows[-1]


def fill_table(table, data_rows):
    """Fill a tagged table with data_rows using the cloned-style-row approach."""
    template_row = table.rows[1]   # the single styled data row
    for vals in data_rows:
        new_row = clone_row(table, template_row)
        cells = new_row.cells
        for c in cells:
            reset_cell(c)
        if is_excluded(vals):
            for i in range(5):
                set_cell_text(cells[i], fmt(vals[i], i))
            merged = cells[5]
            for i in range(6, 10):
                merged = merged.merge(cells[i])
            para = clear_cell_paragraphs(merged)
            run = para.add_run(str(vals[5]))
            run.font.name = "Calibri"; run.font.size = Pt(10)
        else:
            for i in range(10):
                set_cell_text(cells[i], fmt(vals[i], i))
            grade = str(vals[8]).strip()
            if grade in GRADE_COLORS:
                set_cell_bg(cells[8], GRADE_COLORS[grade])
                set_cell_font_color(cells[9], GRADE_COLORS[grade])
    # remove the template row
    template_row._tr.getparent().remove(template_row._tr)


def delete_table(table):
    table._tbl.getparent().remove(table._tbl)
    # NOTE: this leaves the heading/caption around the table behind.
    # Pending the answer on how headings are structured, we'll also remove those.


# ---------------- Orchestration ----------------
def fill_report_tables(template_path, workbook_path, output_path,
                       highest_top_n=HIGHEST_TOP_N, progress=None):
    """Fill all tagged tables in `template_path` from `workbook_path` and save to
    `output_path`. Returns a result dict: {filled, deleted, used, warnings}."""
    log = progress or print

    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    sheets = set(wb.sheetnames)

    doc = Document(template_path)

    # Snapshot the tables up front (we'll be modifying the doc)
    tables = list(doc.tables)

    filled, deleted, warnings = 0, 0, []
    used = set()

    for table in tables:
        if len(table.rows) < 2 or len(table.columns) < 10:
            continue
        header0 = table.rows[0].cells[0].text

        mj = JOINTS_TAG.search(header0)
        mh = HIGHEST_TAG.search(header0)

        if mj:
            sheet_name = mj.group(1)
            if sheet_name in sheets:
                rows = read_joints(wb[sheet_name])
                fill_table(table, rows)
                set_cell_text(table.rows[0].cells[0], "#")  # restore header
                used.add(sheet_name)
                filled += 1
                log(f"OK joints_{sheet_name}: {len(rows)} rows")
            else:
                delete_table(table)
                deleted += 1
                log(f"DEL joints_{sheet_name}: sheet not found -> table deleted")

        elif mh:
            sheet_name = mh.group(1)
            if sheet_name in sheets:
                rows = read_highest(wb[sheet_name], highest_top_n)
                fill_table(table, rows)
                set_cell_text(table.rows[0].cells[0], "#")
                filled += 1
                log(f"OK highest_{sheet_name}: {len(rows)} rows")
            else:
                delete_table(table)
                deleted += 1
                log(f"DEL highest_{sheet_name}: sheet not found -> table deleted")

    # Validation: pipe sheets that exist but were never filled by any tag
    pipe_sheets = {s for s in sheets if s.endswith("Pipe")}
    for s in pipe_sheets - used:
        warnings.append(f"sheet '{s}' has no matching tag in template")

    doc.save(output_path)
    log(f"Tables: filled {filled}, deleted {deleted}. Saved -> {output_path}")
    for w in warnings:
        log("WARNING: " + w)

    return {"filled": filled, "deleted": deleted, "used": used, "warnings": warnings}
