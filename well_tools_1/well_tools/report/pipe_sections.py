"""Per-pipe section keep/remove for the universal master template.

The master template carries a block for every possible pipe (firstPipe …
seventhPipe), each wrapped in marker paragraphs ``{{firstPipe_start}}`` /
``{{firstPipe_end}}``. A pipe appears in more than one place (its block in the
"Highest Metal Loss" section AND its block in the "Full Joint Analysis"
section), so a role can have several marker ranges — all are handled together.

For each role:
  * pipe present  -> remove just the two marker paragraphs of every range (keep
                     the content; the metadata tags inside are filled later).
  * pipe absent   -> remove each whole range (markers + everything between),
                     so no orphaned heading/table/blank page is left behind.

This runs first (template -> output), before the tables/images passes, so the
absent pipes' tables never reach the table filler.
"""

from docx import Document
from docx.oxml.ns import qn

_W_P = qn("w:p")
_W_T = qn("w:t")
_W_TC = qn("w:tc")


def _para_text(p):
    return "".join(t.text or "" for t in p.iter(_W_T))


def _remove_absent_pipe_lines(body, absent_roles):
    """Delete any body paragraph still referencing an absent pipe's tag
    (e.g. a conclusion line with {{seventhPipe_highest_grade}}). Present pipes'
    tags are filled later, so they never match here. Returns #removed."""
    if not absent_roles:
        return 0
    prefixes = tuple("{{%s_" % r for r in absent_roles)
    removed = 0
    for p in list(body.iter(_W_P)):
        txt = _para_text(p)
        if not any(pre in txt for pre in prefixes):
            continue
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
    return removed


def _process_role(body, role, keep):
    """Process every {{role_start}}…{{role_end}} range. Returns (#ranges, #removed_elements)."""
    start_tok = "{{%s_start}}" % role
    end_tok = "{{%s_end}}" % role
    ranges = removed = 0

    while True:
        children = list(body)
        start = end = None
        si = ei = None
        for idx, el in enumerate(children):
            if el.tag == _W_P and start is None and start_tok in _para_text(el):
                start, si = el, idx
            elif start is not None and el.tag == _W_P and end_tok in _para_text(el):
                end, ei = el, idx
                break
        if start is None or end is None:
            break

        between = children[si + 1:ei]
        if not keep:
            for el in between:
                body.remove(el)
                removed += 1
        body.remove(start)
        body.remove(end)
        ranges += 1

    return ranges, removed


def apply_pipe_sections(template_path, output_path, present_roles, all_roles,
                        progress=None, review=None):
    """Open `template_path`, keep the sections of `present_roles` (strip markers)
    and delete the sections of every other role in `all_roles`, save to
    `output_path`. Returns {kept_roles, removed_roles}."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    present = set(present_roles)
    doc = Document(template_path)
    body = doc.element.body

    kept_roles, removed_roles, found_any = [], [], False
    for role in all_roles:
        keep = role in present
        ranges, _ = _process_role(body, role, keep)
        if ranges:
            found_any = True
            (kept_roles if keep else removed_roles).append(role)

    # Remove standalone lines (e.g. conclusions) that reference an absent pipe.
    absent = [r for r in all_roles if r not in present]
    pruned = _remove_absent_pipe_lines(body, absent)
    if pruned:
        log(f"Removed {pruned} line(s) referencing absent pipe(s).")

    doc.save(output_path)

    if found_any:
        log(f"Pipe sections: kept {kept_roles or '—'}, removed {removed_roles or '—'}.")
        # Present pipes whose section markers weren't found in the template.
        missing = [r for r in present_roles if r not in kept_roles]
        for r in missing:
            rev(f"⚠ No {{{{{r}_start}}}}/{{{{{r}_end}}}} section in the template for {r}.")
    else:
        rev("⚠ Configuration set, but the template has no {{<pipe>_start}}/{{<pipe>_end}} "
            "sections — nothing to keep or remove.")
    return {"kept": kept_roles, "removed": removed_roles}
