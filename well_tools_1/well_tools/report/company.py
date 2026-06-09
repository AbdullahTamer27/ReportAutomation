"""Company logo + name placement.

The chosen company contributes to the report in three ways:

  1. Logo body — a borderless 1x1 table whose cell text is ``{{COMP}}`` (same
     shape as the report images in ``images``). The logo is inserted there and
     the tag is removed.

  2. Logo headers — the company logo also lives in the running header(s). A
     two-section report (first-page section + body section) has two header
     definitions, each with a first-page / default / even-page variant. The
     template author marks the logo picture by setting its **Alt Text** to
     ``{{COMP}}`` (in Word: right-click the image -> Alt Text -> Description).
     Every header picture so marked has its embedded image bytes swapped for the
     chosen logo, keeping its existing size/position so layout is preserved.

  3. Company name text — the registered company name is written wherever the
     text tag ``{{COMPNAME}}`` appears. This is meant for the footers (which have
     no image, two sections), but it is replaced everywhere it occurs — body,
     headers, and footers — so it works regardless of placement.

Unlike the IMGS-folder images, the logo file is not supplied by the user per run;
it comes from the registered company chosen in the UI (see webapp Company Manager).
"""

import os

from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn

from .images import insert_image_gentle
from .text_fields import iter_headers, replace_fields_in_doc

# Borderless body logo: target width, capped by height (aspect preserved).
COMPANY_IMG_WIDTH = Inches(2.5)
COMPANY_MAX_HEIGHT = Inches(1.5)

TAG = "{{COMP}}"
NAME_TAG = "{{COMPNAME}}"


# ---------------- Company-name text replacement ----------------
def _replace_company_name(doc, name):
    """Replace {{COMPNAME}} with `name` across body, headers and footers
    (run-preserving, via text_fields). Returns the number of replacements."""
    return replace_fields_in_doc(doc, {NAME_TAG: name}).get(NAME_TAG, 0)


def _docpr_matches_tag(drawing):
    """True if the drawing's wp:docPr name/descr/title contains the tag."""
    docPr = drawing.find(".//" + qn("wp:docPr"))
    if docPr is None:
        return False
    for attr in ("descr", "name", "title"):
        val = docPr.get(attr)
        if val and TAG in val:
            return True
    return False


def _swap_header_logos(doc, logo_bytes):
    """Replace the embedded bytes of every header picture tagged {{COMP}}.

    Returns the number of header pictures swapped. The same physical image part
    may back several headers; each is only rewritten once."""
    swapped = 0
    rewritten_parts = set()
    for header in iter_headers(doc):
        el = header._element
        drawings = el.findall(".//" + qn("wp:inline")) + el.findall(".//" + qn("wp:anchor"))
        for drawing in drawings:
            if not _docpr_matches_tag(drawing):
                continue
            blip = drawing.find(".//" + qn("a:blip"))
            if blip is None:
                continue
            rid = blip.get(qn("r:embed"))
            if not rid:
                continue
            part = header.part.related_parts.get(rid)
            if part is None:
                continue
            if id(part) not in rewritten_parts:
                part._blob = logo_bytes
                rewritten_parts.add(id(part))
            swapped += 1
    return swapped


# ---------------- Body table logo ----------------
def _fill_body_logo(doc, logo_path):
    """Insert the logo into the borderless 1x1 {{COMP}} table. Returns True if
    the table was found."""
    for table in doc.tables:
        if len(table.rows) == 1 and len(table.columns) == 1:
            cell = table.rows[0].cells[0]
            if TAG in cell.text.strip():
                insert_image_gentle(
                    cell, logo_path, TAG,
                    COMPANY_IMG_WIDTH, COMPANY_MAX_HEIGHT, border_pt=0,
                )
                return True
    return False


# ---------------- Orchestration ----------------
def place_company_logo(path, logo_path, company_name=None, progress=None, review=None):
    """Open `path` and apply the chosen company: insert `logo_path` into the body
    {{COMP}} table and every header picture tagged {{COMP}}, and replace the
    {{COMPNAME}} text tag with `company_name` (body/headers/footers). Saves in
    place. Returns counts."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    if not logo_path or not os.path.isfile(logo_path):
        rev(f"❌ Company logo not placed — file not found: {logo_path}")
        return {"body": False, "headers": 0, "name": 0}

    with open(logo_path, "rb") as f:
        logo_bytes = f.read()

    doc = Document(path)
    body_done = _fill_body_logo(doc, logo_path)
    headers_done = _swap_header_logos(doc, logo_bytes)
    name_done = _replace_company_name(doc, company_name) if company_name else 0
    doc.save(path)

    if body_done:
        log(f"Company logo placed in {TAG} body table.")
    else:
        rev(f"⚠ No {TAG} table in the body — body logo not placed.")
    if headers_done:
        log(f"Company logo swapped in {headers_done} header picture(s).")
    else:
        rev(f"⚠ No header picture tagged {TAG} (Alt Text) — header logos unchanged.")
    if company_name:
        if name_done:
            log(f"Company name written into {name_done} {NAME_TAG} location(s).")
        else:
            rev(f"⚠ No {NAME_TAG} text found — company name not written.")

    return {"body": body_done, "headers": headers_done, "name": name_done}
