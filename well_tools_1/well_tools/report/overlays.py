"""Floating-overlay text boxes — a deliberately self-contained pass.

Overlays are anchored text boxes whose visible text is an ``{{ovl_...}}`` tag.
This module fills those tags (and, for later overlays, removes boxes that don't
apply). It lives on its own on purpose: it imports nothing from the rest of the
report engine and shares no helpers with it. Overlay tags only ever appear
*inside text boxes* (``w:txbxContent``) — a region no other pass touches — so a
bug here cannot reach the working code, and a working-code bug cannot reach here.
If something is wrong with an overlay, this is the only file to read.

Implemented so far:
    {{ovl_wellhead}}  -> the well-head damage / clean statement (a checkbox picks).
"""

from docx import Document
from docx.oxml.ns import qn

# --- Well-head overlay text (overlay #1) -------------------------------------
WELLHEAD_TAG = "{{ovl_wellhead}}"
WELLHEAD_DAMAGE = (
    "Pipes’ damage or well-head effect observed below well-head interval."
)
WELLHEAD_CLEAN = (
    "No clear pipes’ damage  or well-head effect observed "
    "around well-head interval."
)

_W_T = qn("w:t")
_W_P = qn("w:p")
_W_TXBX = qn("w:txbxContent")


# --- Local XML helpers (intentionally not shared) ----------------------------
def _replace_tags_in_paragraph(p, mapping):
    """Replace every mapping tag found in one text-box paragraph, run-preserving
    on the first run (so the box's font/size/colour are kept). Joining the runs
    first means a tag Word split across runs is still matched. Returns 1 if the
    paragraph changed, else 0."""
    ts = p.findall(".//" + _W_T)
    if not ts:
        return 0
    joined = "".join(t.text or "" for t in ts)
    new = joined
    for tag, value in mapping.items():
        if tag in new:
            new = new.replace(tag, value)
    if new == joined:
        return 0
    ts[0].text = new
    # Keep whitespace inside the value (e.g. the double space) intact.
    ts[0].set(qn("xml:space"), "preserve")
    for t in ts[1:]:
        t.text = ""
    return 1


def _replace_in_textboxes(doc, mapping):
    """Apply `mapping` to every text box in the body. Returns the count of boxes
    (paragraphs) changed. Modern boxes carry both a DrawingML copy and a VML
    fallback of the same text — iterating all `w:txbxContent` updates both, so
    they stay in sync."""
    changed = 0
    for txbx in doc.element.body.iter(_W_TXBX):
        for p in txbx.iter(_W_P):
            changed += _replace_tags_in_paragraph(p, mapping)
    return changed


# --- Public entry point ------------------------------------------------------
def apply_overlays(path, wellhead_damage=None, progress=None, review=None):
    """Fill the overlay text boxes in the document at `path` (edited in place).

    `wellhead_damage`: True -> damage statement, False -> clean statement,
    None -> leave the well-head overlay alone. Returns the number of boxes filled.
    """
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    mapping = {}
    if wellhead_damage is not None:
        mapping[WELLHEAD_TAG] = WELLHEAD_DAMAGE if wellhead_damage else WELLHEAD_CLEAN

    if not mapping:
        return 0

    doc = Document(path)
    changed = _replace_in_textboxes(doc, mapping)
    if changed:
        doc.save(path)
        log(f"Overlays: filled {changed} overlay text box(es).")
        rev(f"Overlays — well-head statement set "
            f"({'damage' if wellhead_damage else 'clean'}).")
    else:
        log("Overlays: no matching overlay text boxes found "
            "(template may not carry them yet).")
    return changed
