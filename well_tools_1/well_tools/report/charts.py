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

import matplotlib
matplotlib.use("Agg")          # headless: never touch a display
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from .tables import (
    GRADE_COLORS, MAX_LOSS_IDX, grade_for_loss, is_excluded, read_joints,
)

GRADES = ("A", "B", "C", "D")

# Header band of the small table — Excel "Blue, Accent 1".
_HEADER_BLUE = "#2E75B6"


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

    fig = plt.figure(figsize=(5.0, 5.6), dpi=120)
    fig.suptitle(f"ML% Classification Pie Chart\n{pipe['suffix']}",
                 fontsize=16, y=0.98)

    # Pie occupies the upper ~58%, the table the lower ~32%.
    ax_pie = fig.add_axes([0.02, 0.40, 0.74, 0.46])
    ax_tab = fig.add_axes([0.08, 0.02, 0.84, 0.30])
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
            textprops={"fontsize": 11},
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
    table.set_fontsize(11)
    table.scale(1, 1.6)

    n_rows = len(cell_text)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#BFBFBF")
        if r == 0:                                   # header band
            cell.set_text_props(color="white", fontweight="bold")
        elif r == n_rows - 1:                        # Total row
            cell.set_text_props(fontweight="bold")
        elif c == 0:                                 # grade letter cell
            cell.set_text_props(fontweight="bold")

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
