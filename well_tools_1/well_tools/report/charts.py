"""Per-pipe metal-loss pie charts, rendered with matplotlib.

Each present pipe gets one composite PNG that matches the sample report:

  * a two-line title — "ML% Classification Pie Chart" + the pipe suffix
    (e.g. ``7" CSG``, ``4 1/2" TBG``);
  * a pie of the joint grade distribution (A/B/C/D) coloured with GRADE_COLORS,
    with whole-percent labels on the non-zero slices;
  * an always-four-entry legend (A, B, C, D);
  * a ``Grade | Joints | % of Total`` table with a bold ``Total`` row.

The image is dropped into the universal master template through the same
alt-text placeholder mechanism the rest of the images use: the template carries
a placeholder picture whose Alt Text is ``{{pie_<role>}}`` (e.g.
``{{pie_firstPipe}}``) inside that pipe's repeatable section, so absent pipes'
pie placeholders are removed automatically alongside the rest of their section.

Grades come from each joint's Max Loss (%) via the same `grade_for_loss`
thresholds the tables use, so a pie can never disagree with its table.
"""

import math
import os
import shutil
import tempfile

import logging

import matplotlib
matplotlib.use("Agg")          # headless: never touch a display
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Silence "findfont: Font family 'Calibri' not found." — Calibri is present on
# the Windows target but not every dev box; the fallback renders fine.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

from .tables import (
    GRADE_COLORS, MAX_LOSS_IDX, grade_for_loss, is_excluded, read_joints,
)

GRADES = ("A", "B", "C", "D")

# Header band of the small table — matches the original report's pie table.
_HEADER_BLUE = "#0070C0"

# Title font — Calibri (body) to match the document; matplotlib falls back to
# its default sans-serif if Calibri isn't installed (e.g. on a non-Windows box).
_TITLE_FONT = "Calibri"
_TITLE_SIZE = 18

# Final image size, in inches — fixed so every pie drops into its placeholder
# at the same dimensions (the table stretches to this full width; the circle is
# left at its natural size and centred).
_IMG_W_IN = 3.34
_IMG_H_IN = 3.79


def _hex(grade):
    return "#" + GRADE_COLORS[grade]


# ---------------- data ----------------
def grade_counts(ws):
    """Count a sheet's joints into grades A/B/C/D by Max Loss (%).

    Joints affected by completion elements / casing shoes / DVPs etc. are
    *annotated* rows — their Max Loss (%) cell carries a text note instead of a
    number, which is exactly what `tables.is_excluded` detects. They still
    appear in the Word table (as a merged note row) but are NOT real
    measurements, so they are left out of the pie and its joint total: a pipe
    with 80 A + 20 B + 10 completion-affected joints charts as 80% A / 20% B
    over a total of 100, not 110. Negative Max Loss (an invalid reading) is
    skipped for the same reason. Reusing `is_excluded` keeps the pie's notion
    of 'excluded' identical to the table's — they can never drift apart."""
    counts = {g: 0 for g in GRADES}
    for row in read_joints(ws):
        if is_excluded(row):
            continue
        loss = row[MAX_LOSS_IDX]
        if loss >= 0:
            counts[grade_for_loss(loss)] += 1
    return counts


def _percentages(values):
    """Whole-number percentages that always sum to 100 (largest-remainder).

    Returns a list aligned with `values`; an all-zero input yields all zeros."""
    total = sum(values)
    if total == 0:
        return [0] * len(values)
    raw = [v * 100.0 / total for v in values]
    floors = [int(x) for x in raw]
    remainder = 100 - sum(floors)
    # Hand the leftover points to the largest fractional parts first.
    order = sorted(range(len(values)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[order[i]] += 1
    return floors


# ---------------- rendering ----------------
def render_pie(pipe, counts, out_path):
    """Render one pipe's composite pie+table PNG to `out_path`.

    `pipe` is a pipe-model dict (needs ``suffix``); `counts` is {grade: joints}."""
    values = [counts.get(g, 0) for g in GRADES]
    pcts = _percentages(values)
    total = sum(values)

    fig = plt.figure(figsize=(_IMG_W_IN, _IMG_H_IN), dpi=120)
    # y < 1 leaves a small band of padding between the top border and the title.
    title = fig.suptitle(f"ML% Classification Pie Chart\n{pipe['suffix']}",
                         fontfamily=_TITLE_FONT, fontsize=_TITLE_SIZE,
                         va="top", y=0.965)
    # Keep 18 pt as the target, but shrink just enough to never clip the width.
    # Calibri at 18 pt fits 3.34"; a wider fallback font (no Calibri installed)
    # would otherwise overflow, so measure the rendered title and scale down.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    title_w = title.get_window_extent(renderer).width
    limit_w = fig.bbox.width * 0.96
    if title_w > limit_w:
        title.set_fontsize(_TITLE_SIZE * limit_w / title_w)

    # Table spans the full image width (small side margin only). The pie sits in
    # the band between title and table; set_aspect("equal") keeps it a true
    # circle, so it takes only the width it needs and is not stretched.
    ax_pie = fig.add_axes([0.0, 0.34, 0.76, 0.46])
    ax_tab = fig.add_axes([0.01, 0.015, 0.98, 0.30])
    ax_tab.axis("off")

    if total > 0:
        slice_idx = [i for i, v in enumerate(values) if v > 0]
        slice_pcts = [pcts[i] for i in slice_idx]
        wedge_pcts = iter(slice_pcts)
        wedges, _texts, autotexts = ax_pie.pie(
            [values[i] for i in slice_idx],
            colors=[_hex(GRADES[i]) for i in slice_idx],
            startangle=90, counterclock=False,
            autopct=lambda _frac: f"{next(wedge_pcts)}%",
            pctdistance=0.7,
            textprops={"fontfamily": "Calibri", "fontsize": 9},
            wedgeprops={"edgecolor": "white", "linewidth": 0.5},
        )
        # Slices too thin to hold their label get one floated just outside the
        # ring (matches the sample, where 1–2% labels sit above the pie). When
        # several thin slices are adjacent (e.g. C=2% beside D=1%) their mid-
        # angles nearly coincide, so we fan the labels apart by a minimum gap
        # around their shared mean angle — no leader lines, like the original.
        small = [(w, at) for w, at, p in zip(wedges, autotexts, slice_pcts)
                 if p < 5]
        if small:
            mids = [math.radians((w.theta1 + w.theta2) / 2.0) for w, _ in small]
            order = sorted(range(len(small)), key=lambda j: mids[j])
            spread = [mids[j] for j in order]
            min_sep = math.radians(15)
            for k in range(1, len(spread)):
                if spread[k] - spread[k - 1] < min_sep:
                    spread[k] = spread[k - 1] + min_sep
            # Re-centre the fanned labels on the cluster's original mean angle.
            shift = (sum(mids) - sum(spread)) / len(spread)
            for k, j in enumerate(order):
                ang = spread[k] + shift
                _wedge, at = small[j]
                at.set_position((1.25 * math.cos(ang), 1.25 * math.sin(ang)))
                at.set_ha("center")
                at.set_va("center")
    else:
        ax_pie.pie([1], colors=["#D9D9D9"], startangle=90)
        ax_pie.text(0, 0, "No data", ha="center", va="center", fontsize=12)
    ax_pie.set_aspect("equal")

    # Legend: always all four grades, to the right of the pie.
    handles = [Patch(facecolor=_hex(g), edgecolor="none", label=g) for g in GRADES]
    ax_pie.legend(handles=handles, loc="center left",
                  bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=11)

    # Table: header + 4 grade rows + Total.
    cell_text = [["Grade", "Joints", "% of Total"]]
    cell_colours = [[_HEADER_BLUE] * 3]
    for i, g in enumerate(GRADES):
        cell_text.append([g, str(values[i]), f"{pcts[i]}%"])
        cell_colours.append([_hex(g), "white", "white"])
    cell_text.append(["Total", str(total), "100%" if total else "0%"])
    cell_colours.append(["white"] * 3)

    table = ax_tab.table(cellText=cell_text, cellColours=cell_colours,
                         cellLoc="center", loc="center")
    table.auto_set_font_size(False)

    # Give every row an explicit height in axes-fraction units so the table
    # exactly fills its band (no overflow that would clip the Total row). The
    # header counts as two units, making it twice as tall as a normal row.
    # Fonts: header Calibri 11 bold; grade letters and the Total row Tahoma 10
    # bold; all other data cells Calibri 10.
    n_rows = len(cell_text)
    unit = 1.0 / (n_rows + 1)            # +1 because the header is double height
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#BFBFBF")
        cell.set_height(2 * unit if r == 0 else unit)
        if r == 0:                                   # header — Calibri 11 bold
            cell.set_text_props(fontfamily="Calibri", fontsize=11,
                                fontweight="bold", color="white")
        elif r == n_rows - 1:                        # Total row — Tahoma 10 bold
            cell.set_text_props(fontfamily="Tahoma", fontsize=10,
                                fontweight="bold")
        elif c == 0:                                 # grade letter — Tahoma 10 bold
            cell.set_text_props(fontfamily="Tahoma", fontsize=10,
                                fontweight="bold")
        else:                                        # data — Calibri 10
            cell.set_text_props(fontfamily="Calibri", fontsize=10)

    # Save at the exact figure size (no tight crop) so the image is precisely
    # _IMG_W_IN x _IMG_H_IN; the axes layout already removes side padding.
    fig.savefig(out_path, dpi=120, facecolor="white")
    plt.close(fig)
    return out_path


# ---------------- orchestration ----------------
def place_pie_charts(output_path, pipe_model, excel_path, progress=None, review=None):
    """Render a pie for every present pipe and drop each into its
    ``{{pie_<role>}}`` alt-text placeholder in `output_path` (edited in place).

    Returns the number of pies placed. Pipes whose sheet is missing are skipped
    (their section — and placeholder — was already removed)."""
    log = progress or print
    rev = review or (lambda m: None)

    import openpyxl
    from docx import Document
    from .images import place_images_by_alttext

    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheets = set(wb.sheetnames)

    tmp = tempfile.mkdtemp(prefix="welltools_pies_")
    tag_to_file = {}
    try:
        for p in pipe_model:
            if p["sheet"] not in sheets:
                continue
            counts = grade_counts(wb[p["sheet"]])
            fname = f"pie_{p['role']}.png"
            render_pie(p, counts, os.path.join(tmp, fname))
            tag_to_file[f"{{{{pie_{p['role']}}}}}"] = fname
            log(f"Rendered pie for {p['suffix']} "
                f"(A={counts['A']} B={counts['B']} C={counts['C']} D={counts['D']})")

        if not tag_to_file:
            return 0

        doc = Document(output_path)
        placed, skipped, missing = place_images_by_alttext(
            doc, tmp, tag_to_file, progress=log, review=rev)
        doc.save(output_path)
        rev(f"Pie charts — placed {placed}"
            + (f", {skipped} placeholder(s) missing" if skipped else ""))
        return placed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
