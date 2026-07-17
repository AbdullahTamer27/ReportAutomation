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

import re

from docx import Document
from docx.oxml.ns import qn

from .field_registry import (
    USER_FIELDS, user_fields, as_dicts, is_non_user_tag, generic_field,
)

_TAG = re.compile(r"\{\{[^{}]+\}\}")
_W_P = qn("w:p")
_W_T = qn("w:t")


def _scan(element, out):
    for p in element.iter(_W_P):
        text = "".join(t.text or "" for t in p.iter(_W_T))
        if "{{" in text:
            out.update(_TAG.findall(text))


def extract_tags(docx_path):
    """Return the set of ``{{tags}}`` anywhere in the document — body, tables,
    text-boxes, headers and footers."""
    doc = Document(docx_path)
    tags = set()
    _scan(doc.element.body, tags)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.first_page_header, section.first_page_footer,
                   section.even_page_header, section.even_page_footer):
            _scan(hf._element, tags)
    return tags


def template_fields(docx_path):
    """The form fields to render for `docx_path`: registry user fields whose tag
    the template contains (in registry order), then generic text boxes for any
    unknown user-ish tags. Serialised as dicts for /api/fields."""
    tags = extract_tags(docx_path)
    known = {f.tag for f in USER_FIELDS}
    present = [f for f in user_fields() if f.tag in tags]
    extras = [generic_field(t) for t in sorted(tags)
              if t not in known and not is_non_user_tag(t)]
    return as_dicts(present + extras)
