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

from dataclasses import dataclass, asdict, field as _dc_field


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


def as_dicts(fields):
    """Serialise fields for the /api/fields response the frontend renders from."""
    return [asdict(f) for f in fields]


def by_key(key):
    """Look up a field by its payload key, or None."""
    return next((f for f in USER_FIELDS if f.key == key), None)
