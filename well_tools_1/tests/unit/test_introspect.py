"""Template introspection (Epic C3): tag scan + per-template field selection."""

from docx import Document

from webapp.introspect import extract_tags, template_fields


def _make(tmp_path, body_runs=None, cell_text=None, header_text=None):
    doc = Document()
    if body_runs:
        p = doc.add_paragraph()
        for r in body_runs:           # multiple runs → tests split-across-runs joining
            p.add_run(r)
    if cell_text is not None:
        doc.add_table(rows=1, cols=1).rows[0].cells[0].text = cell_text
    if header_text is not None:
        doc.sections[0].header.paragraphs[0].text = header_text
    path = str(tmp_path / "t.docx")
    doc.save(path)
    return path


def test_extract_tags_body_table_header_and_split_runs(tmp_path):
    p = _make(
        tmp_path,
        body_runs=["Well {{well_name}} and ", "{{orig", "_comp}}"],   # split tag
        cell_text="Loss {{SUMMARY}}",
        header_text="{{COMPNAME}} report",
    )
    tags = extract_tags(p)
    assert "{{well_name}}" in tags
    assert "{{orig_comp}}" in tags        # reassembled across runs
    assert "{{SUMMARY}}" in tags          # from the table cell
    assert "{{COMPNAME}}" in tags         # from the header


def test_template_fields_filters_and_orders(tmp_path):
    # A template using: two user tags, engine/derived tags, and one unknown tag.
    p = _make(tmp_path, body_runs=[
        "{{log_date}} {{well_name}} {{SUMMARY}} {{pie_firstPipe}} "
        "{{firstPipe_name}} {{casings}} {{tool_type}} {{block}}"
    ])
    fields = template_fields(p)
    keys = [f["key"] for f in fields]
    # registry user fields present, in registry order (well_name before log_date),
    # then the unknown user tag as a generic text box.
    assert keys == ["well_name", "log_date", "block"]
    # engine/derived tags never become fields
    assert not any(k in keys for k in
                   ("SUMMARY", "pie_firstPipe", "firstPipe_name", "casings", "tool_type"))
    # the generic field is a plain text input labelled from the tag
    block = next(f for f in fields if f["key"] == "block")
    assert block["tag"] == "{{block}}" and block["type"] == "text" and block["label"] == "Block"


def test_template_with_no_metadata_tags_yields_no_fields(tmp_path):
    p = _make(tmp_path, body_runs=["{{SUMMARY}} {{pie_thirdPipe}} {{DMG1_1}} {{INTERVALS}}"])
    assert template_fields(p) == []


def test_saudi_style_template_shows_all_seven(tmp_path):
    p = _make(tmp_path, body_runs=[
        "{{well_name}} {{field}} {{well_type}} {{btm_depth}} "
        "{{log_date}} {{orig_comp}} {{last_wko}}"
    ])
    keys = [f["key"] for f in template_fields(p)]
    assert keys == ["well_name", "field", "well_type", "btm_depth",
                    "log_date", "orig_comp", "last_wko"]
