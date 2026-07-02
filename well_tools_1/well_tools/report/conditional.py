"""Company-conditional report lines.

A "line" is a Word paragraph. A conditional tag (e.g. ``{{weatherford_corr}}``)
marks a paragraph that should only appear under a certain condition:

  * condition true  -> keep the paragraph, strip just the tag (run-preserving, so
                       the rest of the line keeps its formatting).
  * condition false -> remove the whole paragraph from the report.

Driven by a {tag: keep?} mapping, so it generalizes to other company-specific
lines later. Currently used for ``{{weatherford_corr}}`` (kept only when the
chosen company is Weatherford).

Scope: the document body, including paragraphs inside tables. Removing the sole
paragraph of a table cell would produce invalid OOXML, so in that one case the
paragraph is cleared instead of deleted.
"""

from docx import Document
from docx.oxml.ns import qn

from .text_fields import replace_in_paragraph

_W_P = qn("w:p")
_W_T = qn("w:t")
_W_TC = qn("w:tc")


def _paragraph_text(p):
    return "".join(t.text or "" for t in p.iter(_W_T))


def apply_conditional_lines(path, mapping, progress=None, review=None, doc=None):
    """Apply a {tag: keep_bool} mapping to the body paragraphs.

    For each tagged paragraph: keep & strip the tag if keep is True, else remove
    the paragraph. Returns {tag: {"kept": n, "removed": n}}. When `doc` is given,
    operate on it and do not save; otherwise open and save `path` as before."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    own = doc is None
    if own:
        doc = Document(path)
    body = doc.element.body
    results = {}

    for tag, keep in mapping.items():
        kept = removed = 0
        # Snapshot — we mutate the tree as we go.
        for p in list(body.iter(_W_P)):
            if tag not in _paragraph_text(p):
                continue
            if keep:
                replace_in_paragraph(p, tag, "")   # strip tag, preserve formatting
                kept += 1
            else:
                parent = p.getparent()
                if parent is None:
                    continue
                # Don't leave a table cell with zero paragraphs (invalid OOXML).
                if parent.tag == _W_TC and len(parent.findall(_W_P)) == 1:
                    for t in p.iter(_W_T):
                        t.text = ""
                else:
                    parent.remove(p)
                removed += 1

        results[tag] = {"kept": kept, "removed": removed}
        if keep and kept:
            log(f"Conditional {tag}: kept {kept} line(s).")
        elif not keep and removed:
            log(f"Conditional {tag}: removed {removed} line(s).")
        else:
            log(f"Conditional {tag}: no lines found.")

    if own:
        doc.save(path)
    return results
