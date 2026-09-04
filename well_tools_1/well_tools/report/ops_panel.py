"""One-page-summary panel — the authored half of the ``{{ops}}`` picture.

The OPS is two panels side by side: the processed log presentation on the right
(the existing ``proc`` image, used as-is) and, on the left, a page of well
information the engine already computes — completion strings, a hot-spot
summary, and the conclusions. This module renders that left panel to a PNG.

Nothing here derives new data. Every value has an owner elsewhere and is read
from it, so the panel can never disagree with the report it sits in:

* completion strings  → ``build_pipe_summary`` (the RawData workbook's TABLE 2)
* hot spots           → ``tables.worst_joint``, the same worst-joint row and the
                        same corrected grade the ``{{SUMMARY}}`` table uses
* grade colours       → ``tables.GRADE_COLORS``
* conclusion wording  → ``pipe_config.SEVERITY`` + the pipe's own type word
* dates / well type   → the submitted form fields, already normalised

The panel is drawn with PyMuPDF, already bundled for the PDF preview, so it costs
no new dependency and renders identically on Windows, on CI, and inside the
frozen exe. Prose goes into wrapping text boxes — the hand-made version of this
page clipped its own text mid-word at the panel edge — while the two tables are
drawn to fixed column proportions, which no HTML layout here could hold.

``compose_ops_image`` puts the finished panel beside the proc image to make the
whole ``{{ops}}`` picture.
"""

import os

import fitz

from .pipe_config import SEVERITY, TYPE_FULL
from .tables import GRADE_COLORS

# The rig state is not modelled yet — every report is currently rigless.
RIGLESS_TEXT = "RIGLESS"
# Always stated, on every well, regardless of the data.
TEMPERATURE_NOTE = "Temperature anomaly observed across the logging interval."

# Panel geometry in points. The width is the design's; the height is a starting
# box — the caller re-renders to whatever height the proc image needs.
DEFAULT_WIDTH_PT = 300
DEFAULT_HEIGHT_PT = 850
DEFAULT_DPI = 200


class OpsPanelError(Exception):
    """The panel could not be built or rendered."""


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def _info_lines(fields):
    """The bulleted well-information block, in the order the design shows it.

    Only lines with a value are emitted — a well with no recorded workover gets
    no workover line rather than a line reading "N/A"."""
    lines = [RIGLESS_TEXT]
    well_type = (fields.get("well_type") or "").strip()
    if well_type:
        lines.append(f"{well_type}.")
    for label, key in (("Log Date", "log_date"),
                       ("Original Completion Date", "orig_comp"),
                       ("Latest Workover Date", "last_wko")):
        value = (fields.get(key) or "").strip()
        if value and value.upper() != "N/A":
            lines.append(f"•{label}: {value}.")
    return lines


def _conclusion(pipe, grade):
    """One conclusions bullet, e.g. "Moderate metal loss detected across the
    7 5/8" liner string." — the severity word the rest of the report uses."""
    severity = SEVERITY.get(grade)
    if not severity:
        return None
    label = pipe.get("suffix", "").rsplit(" ", 1)[0]          # size, minus TBG/LNR/CSG
    kind = TYPE_FULL.get(pipe.get("type"), "").lower()
    return f"{severity} metal loss detected across the {label} {kind} string."


def build_panel_data(fields, pipe_summary_rows, hotspots):
    """Assemble the panel's content.

    `fields` are the submitted metadata values keyed by registry key.
    `pipe_summary_rows` are TABLE 2's rows as dicts with its own column names.
    `hotspots` are ``{"pipe": <pipe dict>, "max_loss": str, "grade": str,
    "depth": str}`` in report order — worst joint per pipe, grade already
    corrected."""
    conclusions = [c for c in
                   (_conclusion(h["pipe"], h.get("grade")) for h in hotspots) if c]
    conclusions.append(TEMPERATURE_NOTE)

    return {
        "well_name": (fields.get("well_name") or "").strip(),
        "info_lines": _info_lines(fields),
        "strings": [
            {"od": r.get("Pipe OD", ""), "weight": r.get("Weight (ppf)", ""),
             "top": r.get("Top (ft)", ""), "bottom": r.get("Bottom (ft)", ""),
             "nom": r.get("Thick_Nom", "")}
            for r in pipe_summary_rows
        ],
        "hotspots": [
            {"od": h["pipe"].get("suffix", ""), "max_loss": h.get("max_loss", ""),
             "grade": h.get("grade", ""), "depth": h.get("depth", "")}
            for h in hotspots
        ],
        "conclusions": conclusions,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
# The panel is drawn directly rather than laid out from HTML. PyMuPDF's Story
# ignores every column-width mechanism there is — the `width` attribute, CSS
# `width`, `<colgroup>`, `table-layout: fixed` — and sizes columns purely by
# content, which handed the Pipe OD column half the panel. These tables have
# fixed proportions in the design, so the tables are drawn to those proportions
# and the free-flowing text still goes through a wrapping text box.
#
# Fonts are the PDF base-14 (Helvetica), which are built into every PDF reader
# and into PyMuPDF itself — nothing to bundle, and no repeat of the missing-font
# surprise the pie charts hit inside the frozen exe.
_FONT = "helv"
_FONT_BOLD = "hebo"

_TITLE_PT = 15
_HEADING_PT = 10.5
_BODY_PT = 8.5
_TH_PT = 7.5
_TD_PT = 8

_MARGIN_PT = 3
_HEADER_ROW_PT = 26          # two lines: name over unit
_DATA_ROW_PT = 17
_MAX_HEIGHT_PT = 4000        # the scratch page layout is measured against

_HEADER_FILL = "1F3864"
_LINE_WIDTH = 0.6

# Column proportions, as fractions of the panel width. These are the design's.
STRINGS_COLUMNS = (0.26, 0.15, 0.17, 0.17, 0.25)   # OD · weight · top · bottom · nom
HOTSPOT_COLUMNS = (0.26, 0.15, 0.34, 0.25)         # OD · max WL · grade · depth

# Bullets are *drawn*, not typed. The base-14 fonts have no "•" or "●" glyph and
# render either as "?", so the marker is a filled circle and these characters are
# only ever a signal in the text that one belongs there.
_BULLET_CHARS = "•●"
_BULLET_RADIUS_PT = 1.3
_BULLET_GAP_PT = 2

# insert_textbox refuses to draw at all if the box is a hair too short, so the
# space a line needs is measured generously: ~1.7x the font size for the first
# line and ~1.4x for each one after it.
_FIRST_LINE = 1.75
_NEXT_LINE = 1.4

_LEFT, _CENTRE = 0, 1


def _rgb(value):
    """"1F3864" → the (r, g, b) floats PyMuPDF wants."""
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _grade_fill(grade):
    """The grade's cell colour, from the palette the Word tables use. Anything
    ungraded stays white rather than guessing a colour."""
    code = GRADE_COLORS.get(grade)
    return _rgb(code) if code else None


# Values are drawn straight onto the page, so they are never escaped — an "&" in
# a cell has to reach the paper as an "&".
def _thickness(value):
    """Nominal thickness to three decimals — 0.250, not 0.25. The trailing zero
    is significant to a reader comparing it against a measured thickness."""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _number(value):
    """Drop the decimal point from whole numbers (32.0 → 32) and leave anything
    non-numeric — "Didn't Detect" is a legitimate cell value — untouched."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:g}"


def _line_height(lines, size):
    """The vertical space `lines` lines of `size` text need to be drawn at all."""
    return size * (_FIRST_LINE + max(0, lines - 1) * _NEXT_LINE)


def _bullet_line(page, y, width_pt, text, size):
    """Draw one flush-left line, with a drawn bullet if `text` starts with one.
    Returns the height used."""
    marked = text[:1] in _BULLET_CHARS
    body = text[1:].lstrip() if marked else text

    x = _MARGIN_PT
    if marked:
        centre = fitz.Point(x + _BULLET_RADIUS_PT, y + size * 0.85)
        page.draw_circle(centre, _BULLET_RADIUS_PT, color=(0, 0, 0), fill=(0, 0, 0))
        x += 2 * _BULLET_RADIUS_PT + _BULLET_GAP_PT

    rect = fitz.Rect(x, y, width_pt - _MARGIN_PT, y + _line_height(4, size))
    return _text(page, rect, body, size)


def _text(page, rect, text, size, bold=False, align=_LEFT, colour=(0, 0, 0)):
    """Write wrapped text into `rect`; returns the height it used.

    Text that does not fit comes back as the full box height, so the caller's
    running cursor stays honest even when something overflows."""
    left = page.insert_textbox(
        rect, text, fontname=(_FONT_BOLD if bold else _FONT), fontsize=size,
        align=align, color=colour)
    return rect.height if left < 0 else rect.height - left


def _cell(page, rect, text, size, *, bold=False, align=_CENTRE,
          fill=None, colour=(0, 0, 0)):
    """One table cell: border, optional fill, and vertically centred text."""
    page.draw_rect(rect, color=(0, 0, 0), fill=fill, width=_LINE_WIDTH)
    lines = str(text).split("\n")
    needed = _line_height(len(lines), size)
    top = rect.y0 + max(0, (rect.height - needed) / 2)
    inner = fitz.Rect(rect.x0 + 2, top, rect.x1 - 2, rect.y1)
    page.insert_textbox(inner, "\n".join(lines), fontname=(_FONT_BOLD if bold else _FONT),
                        fontsize=size, align=align, color=colour)


def _row(page, y, width_pt, columns, cells, height, *, header=False, fills=None):
    """Draw one table row across `columns` (fractions) and return the next y."""
    x = _MARGIN_PT
    usable = width_pt - 2 * _MARGIN_PT
    fills = fills or [None] * len(cells)
    for index, (fraction, text) in enumerate(zip(columns, cells)):
        cell_width = usable * fraction
        rect = fitz.Rect(x, y, x + cell_width, y + height)
        _cell(page, rect, text, _TH_PT if header else _TD_PT,
              bold=header, colour=(1, 1, 1) if header else (0, 0, 0),
              align=_LEFT if (index == 0 and not header) else _CENTRE,
              fill=_rgb(_HEADER_FILL) if header else fills[index])
        x += cell_width
    return y + height


def _heading(page, y, width_pt, text, size=_HEADING_PT, gap_above=7, gap_below=3):
    y += gap_above
    rect = fitz.Rect(_MARGIN_PT, y, width_pt - _MARGIN_PT, y + size * 2)
    used = _text(page, rect, text, size, bold=True)
    return y + used + gap_below


def _layout(page, data, width_pt):
    """Draw the whole panel onto `page`; returns the y it finished at, which is
    the panel's natural height."""
    usable = width_pt - 2 * _MARGIN_PT
    y = _MARGIN_PT

    rect = fitz.Rect(_MARGIN_PT, y, width_pt - _MARGIN_PT, y + _TITLE_PT * 2)
    y += _text(page, rect, data["well_name"], _TITLE_PT, bold=True)

    y = _heading(page, y, width_pt, "Well Information")
    y = _heading(page, y, width_pt, "ePDT  Pipe Metal loss Summary", gap_above=2)

    for line in data["info_lines"]:
        y += _bullet_line(page, y, width_pt, line, _BODY_PT)

    y = _heading(page, y, width_pt, "Completion Strings")
    y = _row(page, y, width_pt, (STRINGS_COLUMNS[0], STRINGS_COLUMNS[1],
                                 STRINGS_COLUMNS[2] + STRINGS_COLUMNS[3],
                                 STRINGS_COLUMNS[4]),
             ["Pipe OD\n(inch)", "Weight\n(ppf)", "Pipe Interval\n(ft)",
              "Thick_Nom\n(inch)"], _HEADER_ROW_PT, header=True)
    for string in data["strings"]:
        y = _row(page, y, width_pt, STRINGS_COLUMNS,
                 [string["od"], _number(string["weight"]), _number(string["top"]),
                  _number(string["bottom"]), _thickness(string["nom"])],
                 _DATA_ROW_PT)

    y = _heading(page, y, width_pt, "Hot Spot Summary")
    y = _row(page, y, width_pt, HOTSPOT_COLUMNS,
             ["Pipe OD\n(inch)", "Max WL", "Grade of Metal loss",
              "Hotter Spot Depth\n(ft)"], _HEADER_ROW_PT, header=True)
    for spot in data["hotspots"]:
        y = _row(page, y, width_pt, HOTSPOT_COLUMNS,
                 [spot["od"], spot["max_loss"], spot["grade"], spot["depth"]],
                 _DATA_ROW_PT,
                 fills=[None, None, _grade_fill(spot["grade"]), None])

    y = _heading(page, y, width_pt, "Conclusions")
    for line in data["conclusions"]:
        y += _bullet_line(page, y, width_pt, "•" + line, _BODY_PT) + 2

    return y + _MARGIN_PT


def content_height_pt(data, width_pt=DEFAULT_WIDTH_PT):
    """The panel's natural height at `width_pt` — what the caller needs to scale
    it against the proc image."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=width_pt, height=_MAX_HEIGHT_PT)
        return _layout(page, data, width_pt)
    finally:
        doc.close()


def render_panel(data, dest_path, width_pt=DEFAULT_WIDTH_PT, height_pt=None,
                 dpi=DEFAULT_DPI):
    """Render the panel to `dest_path` as a PNG.

    `height_pt` defaults to the content's own height, so the panel comes out
    trimmed rather than padded with dead space; pass a height to render into a
    fixed box instead. Returns ``{"path", "size", "warnings"}`` — content that
    overruns a given box is reported, never silently cut."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=width_pt, height=max(height_pt or 0, _MAX_HEIGHT_PT))
        used = _layout(page, data, width_pt)

        warnings = []
        if height_pt is not None and used > height_pt:
            warnings.append("the summary panel did not fit its box — it is cut short")

        clip = fitz.Rect(0, 0, width_pt, height_pt if height_pt is not None else used)
        # A zoom matrix rather than dpi=: composition derives a fractional dpi
        # from the proc image's height, and get_pixmap(dpi=) takes only ints.
        zoom = dpi / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        pixmap.save(dest_path)
        size = (pixmap.width, pixmap.height)
    finally:
        doc.close()

    return {"path": dest_path, "size": size, "warnings": warnings}


# --------------------------------------------------------------------------
# Composition — the panel beside the processed log
# --------------------------------------------------------------------------
# The design gives the panel roughly a third of the sheet and the log the rest.
# Fixing the *share* rather than the panel's pixel width is what keeps a well
# with three pipes looking like a well with seven: the panel column stays put and
# short content simply leaves white space below it, exactly as the hand-made
# sheet does.
PANEL_SHARE = 0.37
SEPARATOR_PT = 1


def compose_ops_image(data, proc_path, dest_path, panel_share=PANEL_SHARE):
    """Draw the panel beside `proc_path` and write `dest_path` as a PNG.

    The proc image is never resampled — it sets the composite's height, and the
    panel is rendered to match. Rendering the panel to size, rather than scaling
    it afterwards, keeps its text crisp at whatever height the log happens to be.

    Returns ``{"path", "size", "warnings"}``."""
    from PIL import Image, ImageDraw

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(proc_path) as handle:
        proc = handle.convert("RGB")

    height = proc.height
    total_width = round(proc.width / (1 - panel_share))
    panel_width = total_width - proc.width

    # Render the panel straight into a box `panel_width` px wide, full height.
    dpi = panel_width / DEFAULT_WIDTH_PT * 72
    height_pt = height / dpi * 72

    panel_path = os.path.splitext(dest_path)[0] + "_panel.png"
    panel = render_panel(data, panel_path, width_pt=DEFAULT_WIDTH_PT,
                         height_pt=height_pt, dpi=dpi)

    # Rasterising rounds, so the canvas is built from the panel that came out
    # rather than the width that was asked for — otherwise a 1px seam appears.
    with Image.open(panel_path) as handle:
        rendered = handle.convert("RGB")
    panel_width = rendered.width
    total_width = panel_width + proc.width

    # A hairline between the two halves, as on the hand-made sheet. It gets its
    # own column of the canvas rather than being drawn on top of anything —
    # painting it at the boundary would erase proc's first column of pixels.
    rule = max(1, round(SEPARATOR_PT * dpi / 72))
    total_width += rule

    canvas = Image.new("RGB", (total_width, height), "white")
    canvas.paste(rendered, (0, 0))
    canvas.paste(proc, (panel_width + rule, 0))
    ImageDraw.Draw(canvas).rectangle(
        [panel_width, 0, panel_width + rule - 1, height - 1], fill=(0, 0, 0))

    canvas.save(dest_path)
    os.remove(panel_path)
    return {"path": dest_path, "size": canvas.size, "warnings": panel["warnings"]}
