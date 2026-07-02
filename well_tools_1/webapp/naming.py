"""Filename and date-formatting helpers (no web/DB dependencies).

Extracted from ``webapp.main`` so both the HTTP layer and ``report_service`` can
use them without importing each other.
"""

import os
import re
from datetime import datetime

# Accepted date inputs, parsed in order and reformatted to DD-Mon-YYYY.
# Ambiguous numeric forms are read day-first (regional convention).
DATE_INPUT_FORMATS = (
    "%d-%b-%Y", "%d-%B-%Y",          # 09-Sep-2020 / 09-September-2020 (target-ish)
    "%Y-%m-%d", "%Y/%m/%d",          # ISO (also what a date picker yields)
    "%d %b %Y", "%d %B %Y",          # 09 Sep 2020 / 09 September 2020
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",   # day-first numeric
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y",  # Sep 9, 2020
)
DATE_OUTPUT_FORMAT = "%d-%b-%Y"     # -> 09-Sep-2020


def normalize_date(value):
    """Reformat a date-like string to DD-Mon-YYYY (e.g. 09-Sep-2020).

    Tries a fixed set of common formats; if none match (e.g. "N/A", "", or free
    text), the original value is returned unchanged so the report still fills it.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime(DATE_OUTPUT_FORMAT)
        except ValueError:
            continue
    return s


def safe_filename(name: str) -> str:
    """Make a filesystem-safe stem from a well name."""
    s = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip().strip(".")
    return s


def report_filename(well_name, log_date_disp, company_name):
    """wellname_logdate_EPDT_RIGLESS_REPORT_companyname.docx (blanks → 'NA')."""
    parts = [
        (well_name or "").strip() or "NA",
        (log_date_disp or "").strip() or "NA",
        "EPDT", "RIGLESS", "REPORT",
        (company_name or "").strip() or "NA",
    ]
    stem = safe_filename("_".join(parts)).replace(" ", "_")
    return f"{stem}.docx"
