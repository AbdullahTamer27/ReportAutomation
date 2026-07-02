"""Unit tests for the workbook and XML parse caches — the speedups must be
transparent: same file → reused, changed file → reloaded, and callers never see
each other's mutations."""

import time

import openpyxl

from well_tools.report import _wbcache
from well_tools.core.xml_parser import parse_wellschematic_xml


def _bump(path):
    """Ensure the next write lands with a newer mtime (stat granularity)."""
    time.sleep(0.01)


# ---- workbook cache ---------------------------------------------------------
def test_wbcache_reuses_then_invalidates(tmp_path):
    p = str(tmp_path / "wb.xlsx")
    wb = openpyxl.Workbook(); wb.active["A1"] = 1; wb.save(p)

    a = _wbcache.load(p, data_only=True)
    b = _wbcache.load(p, data_only=True)
    assert a is b                                   # warm cache → same object

    _bump(p)
    wb2 = openpyxl.Workbook(); wb2.active["A1"] = 999; wb2.save(p)
    c = _wbcache.load(p, data_only=True)
    assert c is not a                               # file changed → reloaded
    assert c.active["A1"].value == 999


# ---- XML cache --------------------------------------------------------------
_XML = ("<Root><sectionList>"
        "<EMDSPipeSection><ItemID>1</ItemID><PipeSet>1</PipeSet><TopDepth>0</TopDepth>"
        "<BottomDepth>5000</BottomDepth><NomOD>4.5</NomOD><LBPerFt>12</LBPerFt>"
        "<NomID>3.9</NomID><NomThickness>0.3</NomThickness><Drift>3.8</Drift></EMDSPipeSection>"
        "<EMDSPipeSection><ItemID>2</ItemID><PipeSet>2</PipeSet><TopDepth>0</TopDepth>"
        "<BottomDepth>8000</BottomDepth><NomOD>7</NomOD><LBPerFt>26</LBPerFt>"
        "<NomID>6.1</NomID><NomThickness>0.4</NomThickness><Drift>6.0</Drift></EMDSPipeSection>"
        "</sectionList></Root>")


def test_xml_cache_hands_out_independent_copies(tmp_path):
    p = str(tmp_path / "ws.xml")
    with open(p, "w") as f:
        f.write(_XML)

    a = parse_wellschematic_xml(p)
    b = parse_wellschematic_xml(p)
    assert a is not b and a.equals(b)               # cached, but distinct copies

    # A caller mutating its copy must not corrupt the cache.
    a.drop(a.index[0], inplace=True)
    c = parse_wellschematic_xml(p)
    assert c.equals(b) and len(c) == 2


def test_xml_cache_reparses_after_change(tmp_path):
    p = str(tmp_path / "ws.xml")
    with open(p, "w") as f:
        f.write(_XML)
    first = parse_wellschematic_xml(p)
    assert len(first) == 2

    _bump(p)
    with open(p, "w") as f:                          # shrink to one section
        f.write(_XML.replace(
            "<EMDSPipeSection><ItemID>2</ItemID>", "<X><ItemID>2</ItemID>", 1)
            .replace("</EMDSPipeSection></sectionList>", "</X></sectionList>", 1))
    second = parse_wellschematic_xml(p)
    assert len(second) == 1
