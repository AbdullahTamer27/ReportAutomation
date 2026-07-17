"""Field registry — the single source of truth for the report's input fields.

Each entry describes one template text-tag: its name, how it is edited in the
form, and where its value comes from. The form (frontend) renders the user-input
fields from this list, and the backend assembles ``text_fields`` from the same
list — so a field is defined in exactly ONE place.

Epic C, phase C1: this covers the free-text metadata fields (what the Saudi form
has today). Later phases add the *derived* fields (config/XML/schematic) and let
template introspection (C3) show only the tags a chosen template actually uses.

Authoring is intentionally in code (a technical maintainer edits this file), per
the locked decisions in PLAN.md → Epic C.
"""

import re
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Field:
    tag: str                      # template tag, e.g. "{{well_name}}"
    key: str                      # API / payload key, e.g. "well_name"
    dom_id: str                   # form element id, e.g. "wellName"
    label: str
    type: str = "text"            # text | date | number  (rendering hint)
    group: str = "Optional details"
    width: str = "full"           # full | half  (half → paired side-by-side)
    placeholder: str = ""
    mono: bool = False            # monospace input, for data-ish fields
    required: bool = False
    source: str = "user"          # user | derived | engine
    normalize: str = ""           # "date" → normalize_date() on the backend


# Free-text metadata fields, in form order. Widths reproduce today's layout:
# well name (full) · field | well type · bottom depth (full) · log | orig comp ·
# last workover (full).
USER_FIELDS = (
    Field("{{well_name}}", "well_name", "wellName", "Well name",
          placeholder="e.g. HRDH-1702"),
    Field("{{field}}", "field", "fieldName", "Field", width="half",
          placeholder="e.g. Zuluf"),
    Field("{{well_type}}", "well_type", "wellType", "Well type", width="half",
          placeholder="e.g. Oil producer"),
    Field("{{btm_depth}}", "btm_depth", "btmDepth", "Bottom depth", mono=True,
          placeholder="e.g. 7233 ft"),
    Field("{{log_date}}", "log_date", "logDate", "Log date", type="date",
          width="half", mono=True, placeholder="e.g. 09-Sep-2020", normalize="date"),
    Field("{{orig_comp}}", "orig_comp", "origComp", "Original completion",
          type="date", width="half", mono=True, placeholder="e.g. 26-Apr-1988",
          normalize="date"),
    Field("{{last_wko}}", "last_wko", "lastWko", "Last workover", mono=True,
          placeholder="e.g. 03-Mar-2024 (or N/A)", normalize="date"),
)


def user_fields():
    """The user-input metadata fields (source == 'user'), in form order."""
    return [f for f in USER_FIELDS if f.source == "user"]


@dataclass(frozen=True)
class Control:
    """A non-text form control (checkbox / damage count) that only makes sense
    when the template contains its `tag`. `section_id` is the HTML section the
    form shows/hides. Values still flow to the backend as their existing flags."""
    key: str            # payload flag key (damage_count, include_disclaimer, …)
    section_id: str     # id of the <section> to show/hide
    tag: str            # controlling tag; present in the template ⇒ show the control


# Controls hardcoded in index.html, each gated on the tag it drives.
CONTROLS = (
    Control("damage_count", "ctl-damage", "{{damage_block_start}}"),
    Control("include_disclaimer", "ctl-disclaimer", "{{DISC}}"),
    Control("wellhead_damage", "ctl-wellhead", "{{ovl_wellhead}}"),
    Control("fw16", "ctl-fw16", "{{tool_type}}"),
)


def controls_state(tags=None):
    """Per-control visibility: ``[{key, section_id, present}]``. With no `tags`
    (no template chosen) every control is shown, as before."""
    return [
        {"key": c.key, "section_id": c.section_id,
         "present": True if tags is None else (c.tag in tags)}
        for c in CONTROLS
    ]


def as_dicts(fields):
    """Serialise fields for the /api/fields response the frontend renders from."""
    return [asdict(f) for f in fields]


def by_key(key):
    """Look up a field by its payload key, or None."""
    return next((f for f in USER_FIELDS if f.key == key), None)


# --- Tag classification (for template introspection, Epic C3) ----------------
# Engine-managed or derived tags that must NEVER appear as form inputs. Exact
# names + prefix/pattern families for the per-pipe / per-section tags.
_NON_USER_EXACT = {
    "{{SUMMARY}}", "{{DISC}}", "{{COMP}}", "{{COMPNAME}}", "{{INTERVALS}}",
    "{{casings}}", "{{liners}}", "{{tubings}}", "{{pipe_config}}",
    "{{delivery_date}}", "{{hotspot}}", "{{tool_type}}", "{{weatherford_corr}}",
}
_NON_USER_PREFIXES = ("{{highest_", "{{joints_", "{{pie_", "{{ovl", "{{DMG")
_ROLE_TAG = re.compile(r"^\{\{\w+Pipe_")     # firstPipe_name, secondPipe_suffix, …


def is_non_user_tag(tag):
    """True for engine/derived tags — introspection hides these from the form."""
    if tag in _NON_USER_EXACT or _ROLE_TAG.match(tag):
        return True
    return any(tag.startswith(p) for p in _NON_USER_PREFIXES)


def generic_field(tag):
    """A plain text Field for a user-ish tag the registry doesn't define, so a
    brand-new template's unknown tag still gets an input (labelled from the tag)."""
    key = tag[2:-2].strip()                       # inner name, e.g. "block"
    return Field(tag=tag, key=key, dom_id=key,
                 label=key.replace("_", " ").capitalize())
