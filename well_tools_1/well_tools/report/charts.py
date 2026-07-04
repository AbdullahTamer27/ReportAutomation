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
import re
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

# Force matplotlib's bundled DejaVu Sans as the global default. Requesting the
# Windows system fonts (Calibri/Tahoma) is what broke the frozen exe: there they
# resolve to font files the PyInstaller build can't rasterize, so the wedge %
# labels and table numbers rendered blank (title/legend survived only because
# they happened to fall back). DejaVu ships inside matplotlib, so it renders
# identically on every machine — dev already used it via fallback.
matplotlib.rcParams["font.family"] = "DejaVu Sans"

from .tables import (
    GRADE_COLORS, MAX_LOSS_IDX, grade_for_loss, is_excluded, read_joints,
)

GRADES = ("A", "B", "C", "D")

# Alt Text on a pie placeholder picture, e.g. {{pie_firstPipe}}. Placeholders
# matching this whose pipe is absent are deleted (no section markers needed).
_PIE_PLACEHOLDER = re.compile(r"^\{\{pie_\w+\}\}$")

# Header band of the small table — matches the original report's pie table.
_HEADER_BLUE = "#0070C0"

# All chart text uses the bundled DejaVu Sans (see rcParams note above) so it
# renders reliably in the frozen exe. `_FONT` is the single knob for the family.
_FONT = "DejaVu Sans"
_TITLE_FONT = _FONT
_TITLE_SIZE = 14

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

    # Layout mirrors the original report's pie images (measured as canvas
    # fractions): a modest pie centred near x=0.44 with clear whitespace above
    # the table, the table spanning the full image width. set_aspect("equal")
    # keeps the pie a true circle (height-constrained here), so it is never
    # stretched. The pie box height (~0.39) sets the circle's diameter.
    ax_pie = fig.add_axes([0.15, 0.335, 0.58, 0.49])
    ax_tab = fig.add_axes([0.01, 0.02, 0.98, 0.30])
    ax_tab.axis("off")

    if total > 0:
        slice_idx = [i for i, v in enumerate(values) if v > 0]
        slice_pcts = [pcts[i] for i in slice_idx]
        wedges, _texts, autotexts = ax_pie.pie(
            [values[i] for i in slice_idx],
            colors=[_hex(GRADES[i]) for i in slice_idx],
            startangle=90, counterclock=False,
            autopct="%d",   # placeholder — real whole-number labels set just below
            pctdistance=0.7,
            textprops={"fontfamily": _FONT, "fontsize": 7},
            wedgeprops={"edgecolor": "white", "linewidth": 0.5},
        )
        # Set each wedge's whole-number percentage explicitly, AFTER pie(). The
        # previous approach pulled labels from an iterator inside the autopct
        # callback, which assumes matplotlib calls it exactly once per wedge, in
        # order — that assumption changed across matplotlib versions and rendered
        # the labels blank in the frozen (CI-built) exe. Setting the text objects
        # directly is version-robust.
        for at, p in zip(autotexts, slice_pcts):
            at.set_text(f"{p}%")
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

    # Legend: always all four grades, to the right of the pie. Small markers and
    # text, like the original report's pie images.
    handles = [Patch(facecolor=_hex(g), edgecolor="none", label=g) for g in GRADES]
    ax_pie.legend(handles=handles, loc="center left",
                  bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=6.5,
                  handlelength=0.8, handleheight=0.8,
                  labelspacing=0.4, borderaxespad=0.1, handletextpad=0.4)

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
    # Fonts (all DejaVu Sans — see _FONT): header 9 bold; grade letters and the
    # 'Total' label 8 bold; all other data cells (incl. Total's count + %) 8.
    n_rows = len(cell_text)
    unit = 1.0 / (n_rows + 1)            # +1 because the header is double height
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#BFBFBF")
        cell.set_height(2 * unit if r == 0 else unit)
        if r == 0:                                   # header — 9 bold
            cell.set_text_props(fontfamily=_FONT, fontsize=9,
                                fontweight="bold", color="white")
        elif r == n_rows - 1:                        # Total row
            if c == 0:                               # 'Total' label — 8 bold
                cell.set_text_props(fontfamily=_FONT, fontsize=8,
                                    fontweight="bold")
            else:                                    # count + % — like the data cells
                cell.set_text_props(fontfamily=_FONT, fontsize=8)
        elif c == 0:                                 # grade letter — 8 bold
            cell.set_text_props(fontfamily=_FONT, fontsize=8,
                                fontweight="bold")
        else:                                        # data — 8
            cell.set_text_props(fontfamily=_FONT, fontsize=8)

    # Save at the exact figure size (no tight crop) so the image is precisely
    # _IMG_W_IN x _IMG_H_IN; the axes layout already removes side padding.
    fig.savefig(out_path, dpi=120, facecolor="white")
    plt.close(fig)
    return out_path


# ---------------- orchestration ----------------
def place_pie_charts(output_path, pipe_model, excel_path, progress=None, review=None,
                     doc=None):
    """Render a pie for every present pipe, drop each into its ``{{pie_<role>}}``
    alt-text placeholder, then delete any ``{{pie_*}}`` placeholder that wasn't
    filled (a pipe that doesn't exist).

    Omission keys off each placeholder's own Alt Text, so the template needs no
    ``{{<role>_start}}…{{<role>_end}}`` markers around the charts — which aren't
    practical when the pies are arranged side-by-side. Returns the count placed.
    When `doc` is given, operate on it and do not save (caller owns the single
    open/save); otherwise open and save `output_path`."""
    log = progress or print
    rev = review or (lambda m: None)

    from docx import Document
    from . import _wbcache
    from .images import place_images_by_alttext, remove_unfilled_alttext_placeholders

    # One-time provenance line: which font file the chart text actually resolves
    # to. If a frozen build ever renders labels blank again, this tells us at a
    # glance whether the font resolved (problem elsewhere) or not (font problem).
    try:
        from matplotlib.font_manager import findfont, FontProperties
        log(f"Pie chart font: '{_FONT}' -> {findfont(FontProperties(family=_FONT))}")
    except Exception as e:  # noqa: BLE001 — diagnostics must never break a report
        log(f"Pie chart font: resolve check failed — {e}")

    wb = _wbcache.load(excel_path, data_only=True)
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

        own = doc is None
        if own:
            doc = Document(output_path)
        placed, skipped = 0, 0
        if tag_to_file:
            # restrict_to_dict: only touch {{pie_*}} placeholders. Without this,
            # the shared placer would also match {{DMGi_j}} (a pattern family),
            # look for those files in the pie temp folder, and falsely warn.
            placed, skipped, _missing = place_images_by_alttext(
                doc, tmp, tag_to_file, progress=log, review=rev, restrict_to_dict=True)
        # Sweep out every pie placeholder we didn't fill — the absent pipes.
        removed = remove_unfilled_alttext_placeholders(
            doc, set(tag_to_file), _PIE_PLACEHOLDER, progress=log)
        if own and (placed or removed):
            doc.save(output_path)
        rev(f"Pie charts — placed {placed}"
            + (f", {removed} un-inserted removed" if removed else "")
            + (f", {skipped} placeholder(s) missing" if skipped else ""))
        return placed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
