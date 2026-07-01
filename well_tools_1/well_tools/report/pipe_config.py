"""Configuration parsing + the pipe model.

Turns a configuration string like ``4.5x3.5TBG-7LNR-9.625`` into an ordered list
of pipes (the "pipe model"), the single source of truth that drives per-pipe
report content (tables, names, shoe depths, and later the pie charts/overlays).

Grammar
-------
    config = pipe ("-" pipe)*
    pipe   = size (("x"|"X"|"×") size)?  type?
    type   = TBG | LNR | CSG     (case-insensitive; absent ⇒ CSG)
    size   = decimal inches (7, 4.5, 9.625, …)

Rules
-----
* Position = role: 1st pipe → firstPipe, 2nd → secondPipe, … (max 7).
* A pipe with two sizes (``4.5x3.5``) is tapered; the single type covers it.
* ``name``   = full label,    e.g. ``4 1/2" × 3 1/2" Tubing``.
* ``suffix`` = abbreviated,   e.g. ``4 1/2" × 3 1/2" TBG``.
* sizes render as compound fractions (``4 1/2"``, ``9 5/8"``).
* The Excel sheet for each pipe is its role name (``firstPipe`` …).
* ``shoe`` = the deepest point the pipe reaches = max Bottom Body (ft) across
  that pipe's joints; formatted with up to one decimal, trailing ``.0`` dropped
  (4435.0 → "4435", 7654.5 → "7654.5").
"""

import os
import re
from math import gcd

ROLE_NAMES = [
    "firstPipe", "secondPipe", "thirdPipe", "fourthPipe",
    "fifthPipe", "sixthPipe", "seventhPipe",
]
MAX_PIPES = len(ROLE_NAMES)

TYPE_FULL = {"TBG": "Tubing", "LNR": "Liner", "CSG": "Casing"}
TYPE_CODES = tuple(TYPE_FULL)

# Grade → severity word for the highest-metal-loss grade of a pipe.
SEVERITY = {"A": "Light", "B": "Minor", "C": "Moderate", "D": "Intensive"}

# Column indices in the 10-column joints block.
_BOTTOM_BODY_IDX = 2
_MAX_LOSS_IDX = 7

_SEGMENT = re.compile(
    r"^\s*(\d+(?:\.\d+)?)(?:[xX×](\d+(?:\.\d+)?))?\s*(TBG|LNR|CSG)?\s*$",
    re.IGNORECASE,
)


class ConfigParseError(Exception):
    """Raised when a configuration string can't be parsed."""


def fraction_inches(size):
    """Decimal inches → compound-fraction label, e.g. 4.5 → '4 1/2\"',
    9.625 → '9 5/8\"', 7 → '7\"'. Rounded to the nearest 1/16, reduced."""
    whole = int(size)
    sixteenths = round((float(size) - whole) * 16)
    if sixteenths == 16:
        whole += 1
        sixteenths = 0
    if sixteenths == 0:
        return f'{whole}"'
    g = gcd(sixteenths, 16)
    return f'{whole} {sixteenths // g}/{16 // g}"'


def format_depth(value):
    """Up to one decimal, dropping a trailing .0: 4435.0 → '4435', 7654.5 → '7654.5'."""
    if value is None:
        return ""
    r = round(float(value), 1)
    return str(int(r)) if r == int(r) else f"{r:.1f}"


def _sizes_label(sizes):
    return " × ".join(fraction_inches(s) for s in sizes)


def parse_config(config_str):
    """Parse `config_str` into the ordered pipe model (without Excel data).

    Returns a list of pipe dicts. Raises ConfigParseError on bad input."""
    if not config_str or not config_str.strip():
        raise ConfigParseError("Configuration is empty.")

    segments = config_str.strip().split("-")
    if any(not s.strip() for s in segments):
        raise ConfigParseError("Empty pipe segment — check the dashes.")
    if len(segments) > MAX_PIPES:
        raise ConfigParseError(
            f"Too many pipes ({len(segments)}); the maximum is {MAX_PIPES}."
        )

    pipes = []
    for i, seg in enumerate(segments):
        m = _SEGMENT.match(seg)
        if not m:
            raise ConfigParseError(
                f"Can't read pipe '{seg.strip()}'. Use e.g. 4.5x3.5TBG, 7LNR, or 9.625."
            )
        size1 = float(m.group(1))
        size2 = float(m.group(2)) if m.group(2) else None
        type_code = (m.group(3) or "CSG").upper()
        sizes = [size1] + ([size2] if size2 is not None else [])
        label = _sizes_label(sizes)
        pipes.append({
            "index": i + 1,
            "role": ROLE_NAMES[i],
            "sizes": sizes,
            "tapered": size2 is not None,
            "type": type_code,                         # TBG / LNR / CSG
            "name": f"{label} {TYPE_FULL[type_code]}",  # full, e.g. 4 1/2" × 3 1/2" Tubing
            "suffix": f"{label} {type_code}",           # abbreviated, e.g. … TBG
            "sheet": ROLE_NAMES[i],
        })
    return pipes


def _apply_xml_depths(pipes, xml_pipes, warnings, rev):
    """Override each config pipe's shoe (bottom) and hanger (top) with the XML's
    exact depths, matched by primary OD (+type when possible). The XML is
    authoritative. A config pipe with no XML match keeps its Excel shoe and gets
    a warning. Each XML pipe is used at most once."""
    used = set()
    for p in pipes:
        po = float(p["sizes"][0])
        best = None
        # Prefer a same-OD, same-type match; fall back to OD-only.
        for want_type in (True, False):
            for i, x in enumerate(xml_pipes):
                if i in used:
                    continue
                if abs(x["sizes"][0] - po) < 0.02 and (not want_type or x["type"] == p["type"]):
                    best = i
                    break
            if best is not None:
                break
        if best is not None:
            used.add(best)
            x = xml_pipes[best]
            p["shoe"] = x["bottom"]      # XML bottom = shoe (authoritative)
            p["hanger"] = x["top"]       # XML top = liner hanger
        else:
            p.setdefault("hanger", None)
            msg = f"⚠ No XML pipe matched {p['suffix']} — using the Excel shoe depth."
            warnings.append(msg)
            rev(msg)


def build_pipe_model(config_str, excel_path=None, review=None, xml_path=None):
    """Parse `config_str` and, if `excel_path` is given, enrich each pipe with
    its joint count and shoe depth (max Bottom Body) from its sheet.

    If `xml_path` is given, the pipe's shoe (bottom) and hanger (top) depths are
    overridden with the XML's exact values (matched by OD) — the XML is the
    source of truth over the Excel.

    Returns {"pipes": [...], "warnings": [...]}. Raises ConfigParseError on bad
    config input. A missing sheet is a warning, not an error."""
    rev = review or (lambda m: None)
    pipes = parse_config(config_str)
    warnings = []

    if excel_path and os.path.isfile(excel_path):
        import openpyxl
        from .tables import read_joints, grade_for_loss

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        sheets = set(wb.sheetnames)
        for p in pipes:
            p["sheet_found"] = p["sheet"] in sheets
            if p["sheet"] in sheets:
                rows = read_joints(wb[p["sheet"]])
                bottoms = [r[_BOTTOM_BODY_IDX] for r in rows
                           if isinstance(r[_BOTTOM_BODY_IDX], (int, float))]
                losses = [r[_MAX_LOSS_IDX] for r in rows
                          if isinstance(r[_MAX_LOSS_IDX], (int, float)) and r[_MAX_LOSS_IDX] >= 0]
                p["joint_count"] = len(rows)
                p["shoe"] = max(bottoms) if bottoms else None
                p["highest_grade"] = grade_for_loss(max(losses)) if losses else None
            else:
                p["joint_count"] = 0
                p["shoe"] = None
                p["highest_grade"] = None
                msg = f"⚠ Configuration: no '{p['sheet']}' sheet in the workbook for {p['suffix']}."
                warnings.append(msg)
                rev(msg)
            p["shoe_text"] = format_depth(p["shoe"])
            p["highest_severity"] = SEVERITY.get(p["highest_grade"], "")
        # Case 2: workbook pipe sheets the configuration doesn't reference.
        config_sheets = {p["sheet"] for p in pipes}
        extra = sorted(s for s in sheets if s.endswith("Pipe") and s not in config_sheets)
        for s in extra:
            msg = (f"⚠ Workbook has a '{s}' sheet not in the configuration "
                   f"— its data is not included.")
            warnings.append(msg)
            rev(msg)
    else:
        for p in pipes:
            p["joint_count"] = None
            p["shoe"] = None
            p["shoe_text"] = ""
            p["highest_grade"] = None
            p["highest_severity"] = ""
            p["sheet_found"] = None

    # XML depths (authoritative) override the Excel-derived shoe and add hanger.
    if xml_path and os.path.isfile(xml_path):
        try:
            xml_pipes = pipes_from_xml(xml_path)
        except Exception as e:  # noqa: BLE001
            xml_pipes = []
            msg = f"⚠ Could not read pipe depths from the XML: {e}"
            warnings.append(msg)
            rev(msg)
        _apply_xml_depths(pipes, xml_pipes, warnings, rev)
        for p in pipes:
            p["shoe_text"] = format_depth(p["shoe"])

    return {"pipes": pipes, "warnings": warnings}


# ---------------- Configuration from the WellSchematic XML ----------------
def _od_token(value):
    """Format an OD as a config-size token: 7.0 → '7', 9.625 → '9.625'."""
    v = round(float(value), 3)
    return str(int(v)) if v == int(v) else ("%g" % v)


def pipes_from_xml(xml_path):
    """Determine the pipe configuration from a WellSchematic XML.

    Groups sections into strings (by PipeSet), and for each string captures its
    OD size(s), type, top (shallowest = liner hanger) and bottom (deepest = shoe)
    depths. A weight change splits one physical string into several sections /
    PipeSets that share the SAME size(s) and type — those are consolidated into a
    single pipe (union of depths) so the configuration never has duplicate sizes
    and the shoe is the string's true deepest point.

    Pipes are ordered INNER→OUTER (smallest OD first, e.g. 4.5-7-9.625-…), unlike
    the outer→inner raw-data table, and assigned roles firstPipe, secondPipe, …
    (max 7), matching the config string. Returns [{role, sizes, type, top, bottom}].
    The XML depths are the *authoritative* ones (source of truth over the Excel)."""
    from well_tools.core.xml_parser import parse_wellschematic_xml

    df = parse_wellschematic_xml(xml_path)

    # One raw string per PipeSet (keeps a tapered string's multiple ODs together).
    raw = []
    for _pset, g in df.groupby("PipeSet"):
        raw.append({
            "sizes": sorted({round(float(v), 3) for v in g["OD"]}, reverse=True),
            "type": str(g["Type"].iloc[0]).upper(),
            "top": float(g["Start"].min()),
            "bottom": float(g["End"].max()),
        })

    # Consolidate strings that are the same physical pipe split by a weight change
    # into one pipe spanning all their depths. A weight change can put the lower
    # section in a different section/PipeSet, which the classifier may even
    # mislabel (the deeper part of a casing looks like a liner because its top
    # isn't at surface). We therefore key on (size, is-tubing) rather than the
    # exact type:
    #   * two same-size NON-tubing strings can only be a weight change — you can't
    #     stack a same-OD casing and liner (a liner is smaller than its casing);
    #   * the tubing (reliably PipeSet 1 → TBG) is NEVER merged with a same-OD
    #     casing/liner, so a 4.5" tubing and a separate 4.5" liner stay distinct.
    # The merged type comes from the SHALLOWEST section (a casing reaches surface).
    merged, order = {}, []
    for s in raw:
        key = (tuple(s["sizes"]), s["type"] == "TBG")
        if key in merged:
            m = merged[key]
            if s["top"] < m["_shallow"]:
                m["type"] = s["type"]
                m["_shallow"] = s["top"]
            m["top"] = min(m["top"], s["top"])
            m["bottom"] = max(m["bottom"], s["bottom"])
        else:
            m = dict(s, _shallow=s["top"])
            merged[key] = m
            order.append(key)
    pipes = [merged[k] for k in order]
    for p in pipes:
        p.pop("_shallow", None)

    # Inner → outer (smallest OD first); on a same-OD tie the tubing is innermost.
    pipes.sort(key=lambda s: (s["sizes"][0], 0 if s["type"] == "TBG" else 1))
    pipes = pipes[:MAX_PIPES]
    for i, p in enumerate(pipes):
        p["role"] = ROLE_NAMES[i]
    return pipes


def deepest_point_from_xml(xml_path):
    """The well's deepest point = the largest BottomDepth across all XML sections
    (the total depth). Returns a float, or None if the XML has no sections."""
    from well_tools.core.xml_parser import parse_wellschematic_xml
    df = parse_wellschematic_xml(xml_path)
    return float(df["End"].max()) if len(df) else None


def config_string_from_pipes(strings):
    """Build a config string (e.g. '18.625-13.375-9.625-7LNR-4.5TBG') from the
    XML-derived pipe list, so it can pre-fill / cross-check the typed config."""
    parts = []
    for s in strings:
        size = "x".join(_od_token(v) for v in s["sizes"])
        suffix = "" if s["type"] == "CSG" else s["type"]
        parts.append(size + suffix)
    return "-".join(parts)


# ---------------- Type lists (casings / liners / tubings) ----------------
def pipes_of_type(pipes, type_code):
    """Pipes of a given type (TBG/LNR/CSG), sorted by primary size, descending."""
    return sorted((p for p in pipes if p.get("type") == type_code),
                  key=lambda p: p["sizes"][0], reverse=True)


def sizes_list_string(pipes, type_code):
    """Comma-separated size labels for all pipes of `type_code`, largest first
    (sizes only, no type word). E.g. '18 5/8", 13 3/8", 9 5/8"'."""
    return ", ".join(_sizes_label(p["sizes"]) for p in pipes_of_type(pipes, type_code))
