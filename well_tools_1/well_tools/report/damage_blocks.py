"""Damage-section expansion.

A configuration template marks ONE repeatable damage block with two marker
paragraphs containing `{{damage_block_start}}` and `{{damage_block_end}}`.
Everything between them (the three image-placeholder cells, etc.) is the unit
that repeats once per damage point.

For a report with N damage points, the block is deep-copied N times; on copy i
the sentinel `@N` is replaced by i, turning `{{DMG@N_1}}` into `{{DMG1_1}}`,
`{{DMG2_1}}`, … which the image pass then fills. N=0 removes the block entirely
(a clean report). This runs BEFORE the image-placement pass.

Run-splitting note: each affected paragraph's runs are collapsed into one before
substitution, so a `@N` that Word split across runs is still replaced reliably.
"""

import copy

from docx import Document
from docx.oxml.ns import qn

START_TOKEN = "{{damage_block_start}}"
END_TOKEN = "{{damage_block_end}}"
INDEX_SENTINEL = "@N"

_W_P = qn("w:p")
_W_T = qn("w:t")


def _element_text(el):
    return "".join(t.text or "" for t in el.iter(_W_T))


def _subst_index_in_element(el, i):
    """Replace @N -> i in every paragraph of `el`. Each paragraph that contains
    the sentinel has its runs collapsed into the first <w:t> so the token is
    replaced even if Word split it across runs."""
    for p in el.iter(_W_P):
        ts = p.findall(".//" + _W_T)
        if not ts:
            continue
        joined = "".join(t.text or "" for t in ts)
        if INDEX_SENTINEL not in joined:
            continue
        ts[0].text = joined.replace(INDEX_SENTINEL, str(i))
        for t in ts[1:]:
            t.text = ""


def expand_damage_blocks(doc, damage_count):
    """Expand the marked damage block in `doc` `damage_count` times in place.

    Returns True if the markers were found (block expanded/removed), else False.
    """
    body = doc.element.body

    start = end = None
    for el in list(body):
        if el.tag == _W_P:
            txt = _element_text(el)
            if start is None and START_TOKEN in txt:
                start = el
            elif start is not None and END_TOKEN in txt:
                end = el
                break

    if start is None or end is None:
        return False

    # Elements strictly between the markers, in document order.
    block, collecting = [], False
    for el in list(body):
        if el is start:
            collecting = True
            continue
        if el is end:
            break
        if collecting:
            block.append(el)

    # Insert N clones just before the end marker (preserves order).
    for i in range(1, int(damage_count) + 1):
        for el in block:
            clone = copy.deepcopy(el)
            _subst_index_in_element(clone, i)
            end.addprevious(clone)

    # Remove the original block + both markers.
    for el in block:
        body.remove(el)
    body.remove(start)
    body.remove(end)
    return True


def expand_in_file(path, damage_count, progress=None, review=None):
    """Open `path`, expand the damage block `damage_count` times, save in place."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    doc = Document(path)
    found = expand_damage_blocks(doc, damage_count)
    doc.save(path)

    if found:
        log(f"Damage sections: block expanded x{int(damage_count)}.")
    elif damage_count and int(damage_count) > 0:
        rev(f"⚠ Number of damages = {int(damage_count)}, but the template has no "
            f"{START_TOKEN}/{END_TOKEN} markers — no damage pictures were added.")
    else:
        log("Damage sections: no block markers (none requested).")
    return found
