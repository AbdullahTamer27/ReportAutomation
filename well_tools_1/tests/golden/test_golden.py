"""Golden regression tests for the full report pipeline.

For each fixture set under ``tests/fixtures/`` that has an ``inputs.json``, this
generates a report through the real ``report_service.generate`` and diffs it,
part-by-part, against a committed ``golden.docx``.

- The **synthetic** set is always present and committed → always runs.
- The **real** set runs only if you've dropped your sanitized files in
  ``tests/fixtures/real/`` (see the README there); otherwise it's skipped.

Bootstrapping: if a set has inputs but no ``golden.docx`` yet, the test writes
one and fails with a message telling you to review and commit it. After that, the
same generation must stay byte/behaviour-identical or the test fails.

Regenerate a golden intentionally (after a deliberate change) by deleting the
set's ``golden.docx`` and re-running.
"""

import json
import os
import shutil
import tempfile

import pytest

from tests.util import diff_docx

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _fixture_sets():
    sets = []
    for name in sorted(os.listdir(FIXTURES)):
        d = os.path.join(FIXTURES, name)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "inputs.json")):
            sets.append(name)
    return sets


def _find(d, *candidates):
    for c in candidates:
        p = os.path.join(d, c)
        if os.path.isfile(p):
            return p
    return None


@pytest.mark.parametrize("set_name", _fixture_sets() or ["synthetic"])
def test_golden(set_name, frozen_now, tmp_path):
    import webapp.report_service as report_service

    src = os.path.join(FIXTURES, set_name)
    if not os.path.isfile(os.path.join(src, "inputs.json")):
        pytest.skip(f"no fixture set at {src} (drop files per its README to enable)")

    with open(os.path.join(src, "inputs.json")) as f:
        cfg = json.load(f)

    template = _find(src, "template.docx")
    excel = _find(src, "data.xlsm", "data.xlsx")
    xml = _find(src, "schematic.xml") if cfg.get("xml") is not False else None
    assert template and excel, f"{set_name}: needs template.docx and data.xls(x/m)"

    # Work in a temp copy so nothing in the repo is mutated (the pipeline writes a
    # RawData workbook and the report beside the inputs).
    work = os.path.join(tmp_path, "work")
    shutil.copytree(src, work)
    if os.path.isdir(os.path.join(src, "IMGS")):
        pass  # already copied by copytree

    result = report_service.generate(
        template_path=os.path.join(work, os.path.basename(template)),
        company_name=cfg.get("company_name"),
        company_logo_path=(os.path.join(work, cfg["company_logo"]) if cfg.get("company_logo") else None),
        excel_path=os.path.join(work, os.path.basename(excel)),
        working_dir=work,
        xml_path=(os.path.join(work, os.path.basename(xml)) if xml else None),
        config=cfg.get("config"),
        damage_count=cfg.get("damage_count", 0),
        include_disclaimer=cfg.get("include_disclaimer", False),
        wellhead_damage=cfg.get("wellhead_damage"),
        well_name=cfg.get("well_name"),
        well_type=cfg.get("well_type"),
        btm_depth=cfg.get("btm_depth"),
        field=cfg.get("field"),
        log_date=cfg.get("log_date"),
        orig_comp=cfg.get("orig_comp"),
        last_wko=cfg.get("last_wko"),
    )
    produced = result["output_path"]
    assert os.path.isfile(produced), f"{set_name}: no output produced"

    golden = os.path.join(src, "golden.docx")
    if not os.path.isfile(golden):
        shutil.copyfile(produced, golden)
        pytest.fail(f"{set_name}: no golden.docx — created one at {golden}. "
                    f"Review it, then commit it to lock the baseline.")

    diffs = diff_docx(golden, produced)
    assert not diffs, f"{set_name}: report differs from golden:\n" + "\n".join(diffs)
