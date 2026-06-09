"""Plain-text tag replacement across a document's body, headers and footers.

A "text field" is a tag like ``{{well_name}}`` that is replaced with a value
wherever it appears. Replacement is run-preserving: only the runs the tag spans
are edited, so a tag in the middle of a styled paragraph (e.g. a legal block, or
a header/footer line) does NOT reflow or restyle the surrounding text. Tags Word
has split across several runs are still handled.

Used by the company-name tag ({{COMPNAME}}) and the well-metadata tags
({{well_name}}, {{log_date}}, {{orig_comp}}, {{last_wko}}).
"""

from docx import Document
from docx.oxml.ns import qn

_W_P = qn("w:p")
_W_T = qn("w:t")


def iter_headers(doc):
    """Yield every header object across all sections (first-page / default /
    even-page variants)."""
    for section in doc.sections:
        for name in ("first_page_header", "header", "even_page_header"):
            yield getattr(section, name)


def iter_footers(doc):
    """Yield every footer object across all sections (first-page / default /
    even-page variants)."""
    for section in doc.sections:
        for name in ("first_page_footer", "footer", "even_page_footer"):
            yield getattr(section, name)


def replace_in_paragraph(p, old, new):
    """Replace every `old` -> `new` in one paragraph WITHOUT disturbing the
    formatting of runs the tag does not touch.

    Maps the paragraph's <w:t> nodes to character ranges and, for each
    occurrence, edits only the runs the tag spans: the replacement text goes into
    the first spanning run (inheriting the tag's own formatting) and the tag
    characters are removed from the others. Returns the number of replacements."""
    count = 0
    while True:
        ts = p.findall(".//" + _W_T)
        if not ts:
            return count
        texts = [t.text or "" for t in ts]
        idx = "".join(texts).find(old)
        if idx < 0:
            return count
        end = idx + len(old)

        pos = 0
        inserted = False
        for t, txt in zip(ts, texts):
            seg_start, seg_end = pos, pos + len(txt)
            pos = seg_end
            if seg_end <= idx or seg_start >= end:
                continue  # no overlap with the tag — leave this run untouched
            left = txt[: max(0, idx - seg_start)]
            right = txt[end - seg_start:] if end <= seg_end else ""
            if not inserted:
                t.text = left + new + right
                inserted = True
            else:
                t.text = left + right
        count += 1


def replace_in_element(el, old, new):
    """Replace `old` -> `new` in every paragraph under `el` (body / header /
    footer), preserving untouched runs. Returns the number of occurrences."""
    count = 0
    for p in el.iter(_W_P):
        count += replace_in_paragraph(p, old, new)
    return count


def replace_fields_in_doc(doc, mapping):
    """Apply a {tag: value} mapping across body, headers and footers.

    Values are coerced to str (None -> ""). Returns {tag: replacement_count}."""
    counts = {}
    for tag, value in mapping.items():
        new = "" if value is None else str(value)
        n = replace_in_element(doc.element.body, tag, new)
        for hdr in iter_headers(doc):
            n += replace_in_element(hdr._element, tag, new)
        for ftr in iter_footers(doc):
            n += replace_in_element(ftr._element, tag, new)
        counts[tag] = n
    return counts


def apply_text_fields(path, mapping, progress=None, review=None):
    """Open `path`, apply the {tag: value} mapping, save in place.

    Every tag is replaced (empty values clear the tag so no `{{...}}` is left in
    the output). A review warning is emitted for any tag that had a non-empty
    value but was not found in the document. Returns {tag: count}."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    doc = Document(path)
    counts = replace_fields_in_doc(doc, mapping)
    doc.save(path)

    written = sum(1 for tag, v in mapping.items() if (v not in (None, "")) and counts.get(tag))
    for tag, value in mapping.items():
        if value not in (None, "") and not counts.get(tag):
            rev(f"⚠ {tag} not found in the template — value not written.")
    log(f"Text fields: {written} field(s) written "
        f"({sum(counts.values())} replacement(s)).")
    return counts
