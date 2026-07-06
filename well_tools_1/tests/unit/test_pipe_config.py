"""Unit tests for configuration parsing and XML-derived pipe layout.

Covers the config-string grammar (taper, default type, roles, errors), the
size/depth formatting, and — importantly — the two XML edge cases we flagged:
weight-change consolidation and a taper kept within one PipeSet, plus the
inner→outer ordering.
"""

import os

import pytest

from well_tools.report import pipe_config as pc


# ---- config-string parsing --------------------------------------------------
def test_parse_taper_type_and_roles():
    pipes = pc.parse_config("4.5x3.5TBG-7LNR-9.625")
    assert [p["role"] for p in pipes] == ["firstPipe", "secondPipe", "thirdPipe"]
    # innermost first
    assert pipes[0]["sizes"] == [4.5, 3.5] and pipes[0]["tapered"] is True
    assert pipes[0]["type"] == "TBG"
    assert pipes[1]["type"] == "LNR" and pipes[1]["sizes"] == [7.0]
    # default type is CSG when omitted
    assert pipes[2]["type"] == "CSG"


def test_parse_labels_and_suffix():
    p = pc.parse_config("9.625")[0]
    assert p["suffix"] == '9 5/8" CSG'
    assert p["name"] == '9 5/8" Casing'


@pytest.mark.parametrize("bad", ["", "   ", "7--9", "7-banana", "3.5-4.5-5-6-7-8-9-10"])
def test_parse_errors(bad):
    with pytest.raises(pc.ConfigParseError):
        pc.parse_config(bad)


# ---- pure formatters --------------------------------------------------------
@pytest.mark.parametrize("size,label", [
    (7, '7"'), (4.5, '4 1/2"'), (9.625, '9 5/8"'), (18.625, '18 5/8"'), (13.375, '13 3/8"'),
])
def test_fraction_inches(size, label):
    assert pc.fraction_inches(size) == label


@pytest.mark.parametrize("value,text", [(4435.0, "4435"), (7654.5, "7654.5"), (None, "")])
def test_format_depth(value, text):
    assert pc.format_depth(value) == text


# ---- XML derivation ---------------------------------------------------------
def _section(item_id, pipeset, top, bottom, od):
    return (f"<EMDSPipeSection><ItemID>{item_id}</ItemID><PipeSet>{pipeset}</PipeSet>"
            f"<TopDepth>{top}</TopDepth><BottomDepth>{bottom}</BottomDepth>"
            f"<NomOD>{od}</NomOD><LBPerFt>20</LBPerFt><NomID>{od - 0.5}</NomID>"
            f"<NomThickness>0.4</NomThickness><Drift>{od - 0.6}</Drift></EMDSPipeSection>")


def _write_xml(path, sections):
    body = "".join(_section(*s) for s in sections)
    with open(path, "w") as f:
        f.write(f"<Root><sectionList>{body}</sectionList></Root>")
    return path


def test_pipes_from_xml_weight_change_consolidates_and_orders(tmp_path):
    xml = _write_xml(str(tmp_path / "ws.xml"), [
        # (item, pipeset, top, bottom, od)
        (1, 1, 0, 6000, 4.5),      # tubing
        (2, 2, 0, 5000, 9.625),    # 9-5/8 upper section
        (3, 3, 5000, 8000, 9.625),  # 9-5/8 lower (weight change → different PipeSet)
        (4, 4, 0, 3000, 13.375),   # 13-3/8 casing
    ])
    pipes = pc.pipes_from_xml(xml)

    # The two 9-5/8 sections merge into ONE pipe spanning both depths.
    ninebng = [p for p in pipes if p["sizes"] == [9.625]]
    assert len(ninebng) == 1
    assert ninebng[0]["top"] == 0 and ninebng[0]["bottom"] == 8000

    # Inner → outer ordering, tubing innermost.
    assert [p["sizes"][0] for p in pipes] == [4.5, 9.625, 13.375]
    assert pipes[0]["type"] == "TBG"
    assert [p["role"] for p in pipes][:3] == ["firstPipe", "secondPipe", "thirdPipe"]

    assert pc.config_string_from_pipes(pipes) == "4.5TBG-9.625-13.375"
    assert pc.deepest_point_from_xml(xml) == 8000


def test_pipes_from_xml_taper_in_one_pipeset_stays_one_pipe(tmp_path):
    xml = _write_xml(str(tmp_path / "ws.xml"), [
        (1, 1, 0, 3000, 4.5),     # tubing upper OD
        (2, 1, 3000, 6000, 3.5),  # tubing lower OD — same PipeSet ⇒ tapered string
        (3, 2, 0, 5000, 7.0),
    ])
    pipes = pc.pipes_from_xml(xml)
    tbg = [p for p in pipes if p["type"] == "TBG"][0]
    assert sorted(tbg["sizes"], reverse=True) == [4.5, 3.5]   # both ODs, one pipe
    assert tbg["role"] == "firstPipe"


@pytest.mark.parametrize("types, expected", [
    (["TBG", "CSG"], "tubing and casing"),
    (["TBG", "LNR", "CSG"], "tubing, liner and casing"),
    (["CSG", "CSG", "CSG"], "casing"),               # de-duplicated by type
    (["CSG", "TBG"], "tubing and casing"),           # ordered inside-out, not input order
    (["TBG"], "tubing"),
    ([], ""),
])
def test_pipe_config_phrase(types, expected):
    assert pc.pipe_config_phrase([{"type": t} for t in types]) == expected
