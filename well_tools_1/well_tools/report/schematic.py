"""Extract well metadata from a Saudi Aramco 'Well Cross Section Plot' PDF.

The plot carries a labelled header block, e.g.::

    ZULF-65
    WB :0 of 0
    ...
    WELLBORE TYPE
    :KHFJ OIL (WET) PRODUCER
    ORIGINAL COMP.:1981/07/13
    LATEST WKO
    :2013/09/06 #4

fitz often splits a label and its value onto separate lines, so matching runs
over the whole page text with whitespace-tolerant regexes (``\\s*`` happily
spans the newline between a label and its ``:value``).

Only the fields the report's optional inputs use are returned, and only the ones
that are reliably present in the schematic:

    well_name, well_type, orig_comp, last_wko

``btm_depth`` and ``log_date`` are intentionally NOT extracted — the schematic
holds several competing bottom depths, and its printed ``DATE`` is the plot date,
not the EPDT logging date. They are left blank for the user to fill.

Parsing never raises on bad content: anything not found is simply omitted, with a
note in ``warnings``.
"""

import re
from datetime import datetime

# A YYYY/MM/DD date as printed in the header (one capture group).
_DATE = r"(\d{4}/\d{2}/\d{2})"


def _fmt_date(raw):
    """'1981/07/13' -> '13-Jul-1981'; None if it doesn't parse."""
    try:
        return datetime.strptime(raw, "%Y/%m/%d").strftime("%d-%b-%Y")
    except ValueError:
        return None


def _page_text(pdf_path):
    """Text of the first page (the header block lives there). '' if empty."""
    import fitz
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            return ""
        return doc[0].get_text()


def parse_schematic(pdf_path):
    """Parse a well-schematic PDF into report optional fields.

    Returns ``{"fields": {...}, "warnings": [...]}``. ``fields`` holds only the
    keys that were found, among ``well_name``, ``well_type``, ``orig_comp``,
    ``last_wko``; dates are normalised to DD-Mon-YYYY."""
    text = _page_text(pdf_path)
    fields, warnings = {}, []
    if not text.strip():
        warnings.append("No extractable text in the PDF — it may be a scanned image.")
        return {"fields": fields, "warnings": warnings}

    lines = text.splitlines()

    # Well name: the nearest non-empty line above the "WB :N of M" line, with the
    # wellbore number N appended. The schematic prints e.g. 'ZULF-65' / 'WB :0 of 0';
    # we want 'ZULF_65_0' — dashes become underscores and N is tacked on.
    for i, ln in enumerate(lines):
        wb = re.match(r"^\s*WB\s*:\s*(\d+)", ln)
        if wb:
            for j in range(i - 1, -1, -1):
                cand = lines[j].strip()
                if cand:
                    fields["well_name"] = f"{cand.replace('-', '_')}_{wb.group(1)}"
                    break
            break

    # Original completion date.
    m = re.search(r"ORIGINAL\s+COMP\.?\s*:\s*" + _DATE, text)
    if m:
        d = _fmt_date(m.group(1))
        if d:
            fields["orig_comp"] = d
        else:
            warnings.append(f"Original completion date '{m.group(1)}' is not a valid date.")

    # Latest workover date (the trailing '#4' run number is ignored).
    m = re.search(r"LATEST\s+WKO\s*:\s*" + _DATE, text)
    if m:
        d = _fmt_date(m.group(1))
        if d:
            fields["last_wko"] = d
        else:
            warnings.append(f"Last workover date '{m.group(1)}' is not a valid date.")

    # Wellbore type (value runs to end of its line).
    m = re.search(r"WELLBORE\s+TYPE\s*:\s*([^\n]+)", text)
    if m:
        val = m.group(1).strip()
        if val:
            fields["well_type"] = val

    return {"fields": fields, "warnings": warnings}
