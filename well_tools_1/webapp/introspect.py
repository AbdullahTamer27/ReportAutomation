"""Template introspection (Epic C3).

Scan a report template for the ``{{tags}}`` it contains, then decide which form
fields to show for it: the registry's user fields whose tag is present, plus a
generic text box for any genuinely-unknown user-ish tag. Engine/derived tags
(pies, per-pipe tables, overlays, computed lists) are hidden.

The scan walks every ``w:p`` in the body (which includes tables and text-boxes)
and in every header/footer, concatenating the runs within each paragraph — so a
tag Word split across runs, or one living in a table cell / overlay / header, is
still found.
"""

import os
import re
import zipfile

from docx import Document
from docx.oxml.ns import qn

from .field_registry import (
    USER_FIELDS, user_fields, as_dicts, is_non_user_tag, generic_field, controls_state,
)

_TAG = re.compile(r"\{\{[^{}]+\}\}")
_XML_TAG = re.compile(rb"<[^>]+>")
_W_P = qn("w:p")
_W_T = qn("w:t")

# Scans are memoised on (path, mtime, size) — the same key `_wbcache` uses for
# workbooks. A template's tags can't change unless the file does, and on Windows
# an antivirus-inspected 20 MB open is far from free.
_CACHE = {}


def _scan_zip(docx_path):
    """Fast tag scan: read the document/header/footer XML parts and strip the XML
    tags, which concatenates the runs (so a tag Word split across runs re-joins),
    then regex for ``{{tags}}``. ~6x faster than building the python-docx object
    model, and cross-checked against it in the tests."""
    tags = set()
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            base = name.rsplit("/", 1)[-1]
            if not base.startswith(("document", "header", "footer")):
                continue
            text = _XML_TAG.sub(b"", z.read(name)).decode("utf-8", "ignore")
            if "{{" in text:
                tags.update(_TAG.findall(text))
    return tags


def _scan_docx(docx_path):
    """Reference scan via python-docx — body (incl. tables and text-boxes) plus
    every header/footer. Kept as the correctness baseline for `_scan_zip`."""
    def walk(element, out):
        for p in element.iter(_W_P):
            text = "".join(t.text or "" for t in p.iter(_W_T))
            if "{{" in text:
                out.update(_TAG.findall(text))

    doc = Document(docx_path)
    tags = set()
    walk(doc.element.body, tags)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.first_page_header, section.first_page_footer,
                   section.even_page_header, section.even_page_footer):
            walk(hf._element, tags)
    return tags


def extract_tags(docx_path):
    """The set of ``{{tags}}`` anywhere in the document — body, tables, text-boxes,
    headers and footers. Cached per (path, mtime, size)."""
    try:
        st = os.stat(docx_path)
        key = (os.path.abspath(docx_path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and key in _CACHE:
        return set(_CACHE[key])          # copy — callers must not mutate the cache
    tags = _scan_zip(docx_path)
    if key is not None:
        _CACHE[key] = frozenset(tags)
    return tags


def ops_tags():
    """The ``{{tags}}`` in the bundled OPS workbook.

    The one-page summary is built from its own Excel template, so the fields it
    needs — the rig, say — appear nowhere in the Word template. Without this the
    form would never offer them. Same zip-and-regex scan as a .docx: an xlsx
    keeps its text in sharedStrings.xml."""
    from . import config

    path = config.OPS_TEMPLATE_PATH
    try:
        st = os.stat(path)
        key = ("ops", os.path.abspath(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return set()                       # not bundled / not built yet
    if key in _CACHE:
        return set(_CACHE[key])

    tags = set()
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith("xl/") and name.endswith(".xml"):
                    text = _XML_TAG.sub(b"", z.read(name)).decode("utf-8", "ignore")
                    if "{{" in text:
                        tags.update(_TAG.findall(text))
    except (zipfile.BadZipFile, OSError):
        return set()
    _CACHE[key] = frozenset(tags)
    return tags


def template_form(docx_path):
    """The whole form for `docx_path`: ``{"fields": [...], "controls": [...]}``.

    Fields = registry user fields whose tag the template contains (in registry
    order) + generic text boxes for unknown user-ish tags. Controls = per-control
    visibility (checkboxes / damage count shown only when their tag is present)."""
    tags = extract_tags(docx_path)
    # A template that places the one-page summary also needs whatever the OPS
    # workbook asks for, so those tags join the template's own.
    if "{{ops}}" in tags:
        tags = tags | ops_tags()
    known = {f.tag for f in USER_FIELDS}
    present = [f for f in user_fields() if f.tag in tags]
    extras = [generic_field(t) for t in sorted(tags)
              if t not in known and not is_non_user_tag(t)]
    return {"fields": as_dicts(present + extras), "controls": controls_state(tags)}
