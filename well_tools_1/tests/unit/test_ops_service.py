"""Wiring the one-page summary into a report run.

The picture's last step needs Excel on Windows, so it cannot run here. What
*can* be pinned is everything around it — and the thing most worth pinning is
that none of it can fail a report. A missing schematic, a locked file, no Excel
at all: each leaves the run intact and says what happened.
"""

import os

import pytest

from webapp import ops_service
from well_tools.report import ops_export


def test_the_summary_is_only_built_when_the_template_asks():
    assert ops_service.wanted({"{{ops}}", "{{well_name}}"}) is True
    assert ops_service.wanted({"{{well_name}}"}) is False
    assert ops_service.wanted(None) is False


def test_defaults_come_from_the_field_registry():
    """The workbook and the Word document have to word a blank field the same,
    so neither side keeps its own copy of "RIGLESS"."""
    from webapp.field_registry import by_key

    assert ops_service.field_defaults()["RIG"] == by_key("rig").default


def test_the_tag_resolves_to_the_file_the_service_writes():
    from well_tools.report.images import TAG_TO_FILE

    assert TAG_TO_FILE[ops_service.OPS_TAG] == ops_service.OPS_IMAGE_NAME


# --------------------------------------------------------------------------
# Nothing here may fail a report
# --------------------------------------------------------------------------
def test_a_missing_schematic_is_a_note_not_a_failure(tmp_path):
    notes = []
    result = ops_service.build(
        working_dir=str(tmp_path), img_folder=str(tmp_path),
        xml_path=None, excel_path=None, pipe_model=[], fields={}, notes=notes)

    assert result == {"workbook": None, "image": None}
    assert any("schematic" in n for n in notes)


def test_unreadable_inputs_are_a_note_not_a_failure(tmp_path):
    """The XML exists but is nonsense — the report still generates."""
    xml = tmp_path / "schematic.xml"
    xml.write_text("not xml at all")

    notes = []
    result = ops_service.build(
        working_dir=str(tmp_path), img_folder=str(tmp_path), xml_path=str(xml),
        excel_path=str(tmp_path / "nope.xlsx"), pipe_model=[], fields={},
        notes=notes)

    assert result == {"workbook": None, "image": None}
    assert any("One-page summary not built" in n for n in notes)


def test_without_excel_the_workbook_is_still_handed_over(tmp_path, monkeypatch):
    """The picture needs Excel; the numbers don't. When the render is impossible
    the filled workbook is still written and the note says to paste it — which
    is the workflow that existed before any of this was automated."""
    calls = {}

    def fake_fill(template, dest, *a, **kw):
        calls["dest"] = dest
        open(dest, "wb").write(b"xlsx")
        return {"path": dest, "warnings": [], "stray_images": 0}

    monkeypatch.setattr(ops_service.ops_fill, "fill_ops", fake_fill)
    monkeypatch.setattr(ops_service, "collect_hotspots", lambda *a, **k: [])
    monkeypatch.setattr(
        ops_service.ops_export, "render",
        lambda *a, **k: (_ for _ in ()).throw(
            ops_export.OpsExportError("needs Microsoft Excel on Windows")))

    import types
    fake_xml = types.ModuleType("x")
    monkeypatch.setattr("well_tools.core.xml_parser.parse_wellschematic_xml",
                        lambda p: None)
    monkeypatch.setattr("well_tools.core.xml_parser.build_pipe_summary",
                        lambda d: types.SimpleNamespace(to_dict=lambda how: []))
    monkeypatch.setattr("well_tools.report._wbcache.load", lambda *a, **k: None)

    xml = tmp_path / "s.xml"
    xml.write_text("<x/>")
    notes = []
    result = ops_service.build(
        working_dir=str(tmp_path), img_folder=str(tmp_path), xml_path=str(xml),
        excel_path="whatever", pipe_model=[], fields={}, well_name="HRDH-1702",
        notes=notes)

    assert result["workbook"] == calls["dest"]
    assert result["workbook"].endswith("HRDH-1702_OPS.xlsx")
    assert result["image"] is None
    assert any("paste it into the report" in n for n in notes)


def test_fill_warnings_reach_the_run_notes(tmp_path, monkeypatch):
    import types

    monkeypatch.setattr(ops_service.ops_fill, "fill_ops",
                        lambda *a, **k: {"path": a[1], "warnings": ["something odd"],
                                         "stray_images": 0})
    monkeypatch.setattr(ops_service, "collect_hotspots", lambda *a, **k: [])
    monkeypatch.setattr(ops_service.ops_export, "render",
                        lambda *a, **k: (_ for _ in ()).throw(
                            ops_export.OpsExportError("no excel")))
    monkeypatch.setattr("well_tools.core.xml_parser.parse_wellschematic_xml",
                        lambda p: None)
    monkeypatch.setattr("well_tools.core.xml_parser.build_pipe_summary",
                        lambda d: types.SimpleNamespace(to_dict=lambda how: []))
    monkeypatch.setattr("well_tools.report._wbcache.load", lambda *a, **k: None)

    xml = tmp_path / "s.xml"
    xml.write_text("<x/>")
    notes = []
    ops_service.build(working_dir=str(tmp_path), img_folder=str(tmp_path),
                      xml_path=str(xml), excel_path="x", pipe_model=[],
                      fields={}, notes=notes)
    assert "something odd" in notes


# --------------------------------------------------------------------------
# The export step itself
# --------------------------------------------------------------------------
def test_export_refuses_clearly_off_windows():
    """`available()` gates the COM call so the failure is a sentence about Excel
    rather than an ImportError from deep inside pywin32."""
    if ops_export.available():
        pytest.skip("this machine can export")

    with pytest.raises(ops_export.OpsExportError) as excinfo:
        ops_export.render("book.xlsx", "out.png")
    assert "Excel" in str(excinfo.value)


def test_export_availability_matches_the_platform():
    assert ops_export.available() == (os.name == "nt" and _has_pywin32())


def _has_pywin32():
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True
