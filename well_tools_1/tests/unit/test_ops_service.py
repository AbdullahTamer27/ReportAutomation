"""Wiring the one-page summary into a report run.

What matters here is that none of it can fail a report. A missing schematic, an
unreadable workbook, a template that won't parse: each becomes a note, and the
report is still produced. The summary is worth having; it is not worth losing a
report over.
"""

import os

from webapp import ops_service


def test_the_summary_is_only_built_when_the_template_asks():
    assert ops_service.wanted({"{{ops}}", "{{well_name}}"}) is True
    assert ops_service.wanted({"{{well_name}}"}) is False
    assert ops_service.wanted(None) is False


def test_defaults_come_from_the_field_registry():
    """The summary and the Word document have to word a blank field the same,
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
        img_folder=str(tmp_path), xml_path=None, excel_path=None,
        pipe_model=[], fields={}, notes=notes)

    assert result is None
    assert any("schematic" in n for n in notes)


def test_unreadable_inputs_are_a_note_not_a_failure(tmp_path):
    """The XML exists but is nonsense — the report still generates."""
    xml = tmp_path / "schematic.xml"
    xml.write_text("not xml at all")

    notes = []
    result = ops_service.build(
        img_folder=str(tmp_path), xml_path=str(xml),
        excel_path=str(tmp_path / "nope.xlsx"), pipe_model=[], fields={},
        notes=notes)

    assert result is None
    assert any("One-page summary not built" in n for n in notes)


def test_a_broken_template_is_a_note_not_a_failure(tmp_path, monkeypatch):
    """The renderer refusing the template must not take the report with it."""
    import types

    from well_tools.report import ops_render

    monkeypatch.setattr("well_tools.core.xml_parser.parse_wellschematic_xml",
                        lambda p: None)
    monkeypatch.setattr("well_tools.core.xml_parser.build_pipe_summary",
                        lambda d: types.SimpleNamespace(to_dict=lambda how: []))
    monkeypatch.setattr("well_tools.report._wbcache.load", lambda *a, **k: None)
    monkeypatch.setattr(ops_service, "collect_hotspots", lambda *a, **k: [])
    monkeypatch.setattr(
        ops_render, "render_ops",
        lambda *a, **k: (_ for _ in ()).throw(
            ops_render.OpsRenderError("the OPS template is empty")))

    xml = tmp_path / "s.xml"
    xml.write_text("<x/>")
    notes = []
    assert ops_service.build(img_folder=str(tmp_path), xml_path=str(xml),
                             excel_path="x", pipe_model=[], fields={},
                             notes=notes) is None
    assert any("not drawn" in n for n in notes)


def test_a_missing_log_image_is_reported_but_still_draws(tmp_path, monkeypatch):
    """Without proc.jpg the right-hand half is blank — worth saying, but the
    panel is still useful, so the picture is still produced."""
    import types

    from well_tools.report import ops_render

    monkeypatch.setattr("well_tools.core.xml_parser.parse_wellschematic_xml",
                        lambda p: None)
    monkeypatch.setattr("well_tools.core.xml_parser.build_pipe_summary",
                        lambda d: types.SimpleNamespace(to_dict=lambda how: []))
    monkeypatch.setattr("well_tools.report._wbcache.load", lambda *a, **k: None)
    monkeypatch.setattr(ops_service, "collect_hotspots", lambda *a, **k: [])

    drawn = {}

    def fake_render(template, dest, *a, **kw):
        drawn["proc"] = kw.get("proc_path")
        open(dest, "wb").write(b"png")
        return {"path": dest, "size": (100, 200), "warnings": []}

    monkeypatch.setattr(ops_render, "render_ops", fake_render)

    xml = tmp_path / "s.xml"
    xml.write_text("<x/>")
    notes = []
    result = ops_service.build(img_folder=str(tmp_path), xml_path=str(xml),
                               excel_path="x", pipe_model=[], fields={},
                               notes=notes)

    assert result == os.path.join(str(tmp_path), ops_service.OPS_IMAGE_NAME)
    assert drawn["proc"] is None                    # not passed when absent
    assert any("log half is blank" in n for n in notes)
