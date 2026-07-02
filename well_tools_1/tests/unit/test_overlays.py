"""Unit tests for the overlay text mappings — exact wording of the damage
callouts and the shoe/hanger rules (bottom-string shoe omitted, hangers only for
liners). No document I/O; just the mapping builders."""

from well_tools.report import overlays

INCH = "”"   # ” — the typographic inch mark the overlays use


# ---- damage callouts --------------------------------------------------------
def test_damage_mapping_exact_wording_and_channel():
    clusters = [[
        {"suffix": '9 5/8" CSG', "severity": "Intensive",
         "loss": 20.8, "depth": 10184.5, "channel": "54"},
    ]]
    m = overlays._damage_mapping(clusters)
    ml = f"Intensive metal loss in 9 5/8{INCH} CSG Max WL% is 20.8% at 10184.5ft"
    assert m["{{ovl_ml1_1}}"] == ml
    assert m["{{ovl_ch1_1}}"] == f"Channel 54 is used to calculate {ml}."


def test_damage_mapping_no_channel_tag_when_absent():
    clusters = [[{"suffix": '7" LNR', "severity": "Moderate",
                  "loss": 12.0, "depth": 5000.0, "channel": None}]]
    m = overlays._damage_mapping(clusters)
    assert "{{ovl_ml1_1}}" in m
    assert "{{ovl_ch1_1}}" not in m   # channel omitted → no channel overlay


def test_damage_mapping_indices_increment_per_cluster_and_point():
    clusters = [
        [{"suffix": "a", "severity": "Intensive", "loss": 1.0, "depth": 1.0, "channel": "5"},
         {"suffix": "b", "severity": "Moderate", "loss": 2.0, "depth": 2.0, "channel": "6"}],
        [{"suffix": "c", "severity": "Intensive", "loss": 3.0, "depth": 3.0, "channel": "7"}],
    ]
    m = overlays._damage_mapping(clusters)
    assert {"{{ovl_ml1_1}}", "{{ovl_ml1_2}}", "{{ovl_ml2_1}}"} <= set(m)
    assert "{{ovl_ml1_3}}" not in m and "{{ovl_ml2_2}}" not in m


# ---- shoe / hanger callouts -------------------------------------------------
def _pipe(role, name, type_, shoe, hanger=None):
    return {"role": role, "name": name, "type": type_, "shoe": shoe, "hanger": hanger}


def test_shoe_hanger_mapping_rules():
    model = [
        _pipe("firstPipe", '4 1/2" Casing', "CSG", 4000),
        _pipe("secondPipe", '7" Liner', "LNR", 8000, hanger=6000),  # deepest → bottom string
        _pipe("thirdPipe", '9 5/8" Casing', "CSG", 3000),
    ]
    m = overlays._shoe_hanger_mapping(model, excel_path=None)

    # Shoe callouts for the non-bottom strings, with the typographic inch mark.
    assert m["{{ovl_shoe_firstPipe}}"] == f"4 1/2{INCH} Casing Shoe at 4000ft"
    assert m["{{ovl_shoe_thirdPipe}}"] == f"9 5/8{INCH} Casing Shoe at 3000ft"
    # The deepest (at/below TD) string's shoe is omitted.
    assert "{{ovl_shoe_secondPipe}}" not in m

    # Hanger only for the liner.
    assert m["{{ovl_hanger_secondPipe}}"] == f"7{INCH} Liner Hanger at 6000ft"
    assert "{{ovl_hanger_firstPipe}}" not in m
    assert "{{ovl_hanger_thirdPipe}}" not in m
