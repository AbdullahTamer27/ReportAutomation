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

# Bottom Body (ft) is column index 2 in the 10-column joints block.
_BOTTOM_BODY_IDX = 2

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


def build_pipe_model(config_str, excel_path=None, review=None):
    """Parse `config_str` and, if `excel_path` is given, enrich each pipe with
    its joint count and shoe depth (max Bottom Body) from its sheet.

    Returns {"pipes": [...], "warnings": [...]}. Raises ConfigParseError on bad
    config input. A missing sheet is a warning, not an error."""
    rev = review or (lambda m: None)
    pipes = parse_config(config_str)
    warnings = []

    if excel_path and os.path.isfile(excel_path):
        import openpyxl
        from .tables import read_joints

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        sheets = set(wb.sheetnames)
        for p in pipes:
            if p["sheet"] in sheets:
                rows = read_joints(wb[p["sheet"]])
                bottoms = [r[_BOTTOM_BODY_IDX] for r in rows
                           if isinstance(r[_BOTTOM_BODY_IDX], (int, float))]
                p["joint_count"] = len(rows)
                p["shoe"] = max(bottoms) if bottoms else None
            else:
                p["joint_count"] = 0
                p["shoe"] = None
                msg = f"⚠ Configuration: no '{p['sheet']}' sheet in the workbook for {p['suffix']}."
                warnings.append(msg)
                rev(msg)
            p["shoe_text"] = format_depth(p["shoe"])
    else:
        for p in pipes:
            p["joint_count"] = None
            p["shoe"] = None
            p["shoe_text"] = ""

    return {"pipes": pipes, "warnings": warnings}
