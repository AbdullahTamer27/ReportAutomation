"""The field registry must match today's Saudi metadata form exactly (C1)."""

from webapp import field_registry as fr


def test_user_fields_match_todays_form():
    keys = [f.key for f in fr.user_fields()]
    assert keys == ["well_name", "field", "well_type", "btm_depth", "rig",
                    "log_date", "orig_comp", "last_wko"]


def test_tag_key_dom_id_consistent():
    for f in fr.user_fields():
        # The tag mirrors the payload key, but not its case: {{RIG}} is written
        # the way the template author wrote it, while the key stays lowercase
        # like every other payload key.
        assert f.tag.lower() == "{{" + f.key.lower() + "}}"
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
    assert widths["btm_depth"] == "half" and widths["rig"] == "half"     # side by side
    assert widths["log_date"] == "half" and widths["orig_comp"] == "half"
    assert widths["well_name"] == "full" and widths["last_wko"] == "full"


def test_half_width_fields_pair_up_evenly():
    """The form pairs *consecutive* half-width fields, so an odd one out would
    silently take a whole row and break the two-column layout."""
    run = 0
    for f in fr.user_fields():
        if f.width == "half":
            run += 1
        else:
            assert run % 2 == 0, f"odd half-width run before {f.key}"
            run = 0
    assert run % 2 == 0


def test_rig_answers_for_itself_when_blank():
    """A blank rig is an answer — the job was rigless — not a missing value, so
    the field carries its own default instead of being flagged as skipped."""
    assert fr.by_key("rig").default == "RIGLESS"
    assert all(f.default == "" for f in fr.user_fields() if f.key != "rig")


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


def test_engine_markers_and_image_slots_are_never_form_fields():
    """Introspection turns unknown tags into text boxes, which is right for a new
    metadata tag and wrong for anything the engine owns. Block markers and image
    slots are engine-owned — a text box asking the user to type
    "Damage block start" is a question with no correct answer."""
    for tag in ("{{damage_block_start}}", "{{damage_block_end}}",
                "{{proc}}", "{{tempgr}}", "{{wh}}", "{{raw}}", "{{well}}",
                "{{ts}}", "{{qc}}"):
        assert fr.is_non_user_tag(tag), tag


def test_every_image_tag_is_classified():
    """Adding an image tag to the engine without teaching the registry about it
    would silently put a text box on the form — so check the two lists agree."""
    from well_tools.report.images import TAG_TO_FILE

    for tag in TAG_TO_FILE:
        assert fr.is_non_user_tag(tag), tag


# --- how a field's value reaches the document ------------------------------
def test_blank_fields_are_defaulted_and_reported():
    """The normal case: a blank is an omission, so it writes "N/A" and the run
    tells the user which fields were left empty."""
    from webapp.report_service import resolve_field, OPTIONAL_DEFAULT

    defaulted = []
    field = fr.by_key("well_type")
    assert resolve_field(field, {"well_type": ""}, defaulted) == OPTIONAL_DEFAULT
    assert defaulted == [field.label]


def test_a_field_with_its_own_default_is_not_reported_as_missing():
    """A blank Rig is an answer, not an omission — {{RIG}} becomes RIGLESS in the
    Word document exactly as it does in the OPS workbook, and the run says
    nothing about it."""
    from webapp.report_service import resolve_field

    rig = fr.by_key("rig")
    for value in ("", "   ", None, "N/A", "n/a"):
        defaulted = []
        assert resolve_field(rig, {"rig": value}, defaulted) == "RIGLESS"
        assert defaulted == []


def test_a_typed_rig_wins_over_its_default():
    from webapp.report_service import resolve_field

    defaulted = []
    assert resolve_field(fr.by_key("rig"), {"rig": "Rig 42"}, defaulted) == "Rig 42"
    assert defaulted == []
