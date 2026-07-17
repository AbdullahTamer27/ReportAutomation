"""The field registry must match today's Saudi metadata form exactly (C1)."""

from webapp import field_registry as fr


def test_user_fields_match_todays_form():
    keys = [f.key for f in fr.user_fields()]
    assert keys == ["well_name", "field", "well_type", "btm_depth",
                    "log_date", "orig_comp", "last_wko"]


def test_tag_key_dom_id_consistent():
    for f in fr.user_fields():
        assert f.tag == "{{" + f.key + "}}"      # tag mirrors the payload key
        assert f.dom_id and f.label
        assert f.source == "user"
        assert f.width in ("full", "half")


def test_dates_are_normalised():
    # These three go through normalize_date on the backend today.
    for key in ("log_date", "orig_comp", "last_wko"):
        assert fr.by_key(key).normalize == "date"
    # The plain-text ones are not normalised.
    for key in ("well_name", "field", "well_type", "btm_depth"):
        assert fr.by_key(key).normalize == ""


def test_layout_widths_reproduce_pairs():
    widths = {f.key: f.width for f in fr.user_fields()}
    assert widths["field"] == "half" and widths["well_type"] == "half"   # side by side
    assert widths["log_date"] == "half" and widths["orig_comp"] == "half"
    assert widths["well_name"] == "full" and widths["btm_depth"] == "full"


def test_as_dicts_is_serialisable():
    ds = fr.as_dicts(fr.user_fields())
    assert all(isinstance(d, dict) and "tag" in d and "dom_id" in d for d in ds)


def test_fields_serialise_group_and_required():
    # C4: every serialised field carries its group + required flag for the form.
    for d in fr.as_dicts(fr.user_fields()):
        assert d["group"] == "Optional details"
        assert d["required"] is False


def test_generic_field_is_optional_in_default_group():
    g = fr.generic_field("{{block}}")
    assert g.required is False
    assert g.group == "Optional details"
    assert g.label == "Block"
