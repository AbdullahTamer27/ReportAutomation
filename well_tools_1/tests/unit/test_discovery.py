"""Unit tests for the one-folder well-input discovery."""

import os

from webapp.discovery import scan_well_folder


def _touch(folder, *names):
    for n in names:
        open(os.path.join(folder, n), "w").close()


def test_finds_all_four(tmp_path):
    d = str(tmp_path)
    _touch(d, "TBG_7.xlsm", "schematic.xml", "well_cross_section_plot.pdf")
    os.mkdir(os.path.join(d, "IMGS"))

    r = scan_well_folder(d)
    assert r["working_dir"] == d
    assert r["excel_path"].endswith("TBG_7.xlsm")
    assert r["xml_path"].endswith("schematic.xml")
    assert r["schematic_pdf"].endswith("well_cross_section_plot.pdf")
    assert r["imgs_dir"].endswith("IMGS")
    assert r["found"] == ["Excel data", "Schematic XML", "Schematic PDF", "IMGS folder"]
    assert r["missing"] == []


def test_excludes_generated_rawdata_and_prefers_xlsm(tmp_path):
    d = str(tmp_path)
    # Only the generated RawData workbook + a real .xlsm are present.
    _touch(d, "WELL_65_0_RawData.xlsx", "data.xlsm")
    r = scan_well_folder(d)
    assert r["excel_path"].endswith("data.xlsm")     # .xlsm preferred over any .xlsx


def test_ignores_rawdata_when_no_xlsm(tmp_path):
    d = str(tmp_path)
    _touch(d, "WELL_65_0_RawData.xlsx")               # only the generated output
    r = scan_well_folder(d)
    assert r["excel_path"] is None                    # never taken for source input


def test_reports_missing(tmp_path):
    d = str(tmp_path)
    _touch(d, "data.xlsm")                             # no xml, pdf, or IMGS
    r = scan_well_folder(d)
    assert r["found"] == ["Excel data"]
    assert r["missing"] == ["Schematic XML", "Schematic PDF", "IMGS folder"]


def test_empty_folder(tmp_path):
    r = scan_well_folder(str(tmp_path))
    assert all(r[k] is None for k in ("excel_path", "xml_path", "schematic_pdf", "imgs_dir"))
    assert r["found"] == []
