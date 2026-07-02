"""Golden regression tests for the full report pipeline.

For each fixture set under ``tests/fixtures/`` that has an ``inputs.json``, this
generates a report through the real ``report_service.generate`` and diffs it,
part-by-part, against a committed golden ``.docx``.

`inputs.json` may be either:

- a single dict of inputs (one scenario → ``golden.docx``), or
- ``{"base": {...}, "scenarios": [{"name": "...", <overrides>}, ...]}`` — each
  scenario is ``base`` merged with its overrides and compared to its own
  ``golden__<name>.docx``. This is how one template/data set pins several input
  combinations (0 vs N damages, disclaimer on/off, …) — coverage a single fixed
  input could never give.

Sets:
- **synthetic** is always present and committed → always runs.
- **real** runs only if you've dropped your sanitized files in
  ``tests/fixtures/real/`` (see the README there); otherwise it's skipped.

Bootstrapping: a scenario with no golden yet writes one and fails, telling you to
review and commit it. Regenerate intentionally by deleting the golden and re-running.
"""

import json
import os
import shutil

import pytest

from tests.util import diff_docx

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _load_cfg(set_dir):
    with open(os.path.join(set_dir, "inputs.json")) as f:
        return json.load(f)


def _scenarios(cfg):
    """[(scenario_name_or_None, merged_inputs), ...] for a fixture config."""
    if isinstance(cfg, dict) and "scenarios" in cfg:
        base = cfg.get("base", {})
        return [(s["name"], {**base, **s}) for s in cfg["scenarios"]]
    return [(None, cfg)]   # single scenario → golden.docx


def _fixture_sets():
    return [
        name for name in sorted(os.listdir(FIXTURES))
        if os.path.isfile(os.path.join(FIXTURES, name, "inputs.json"))
    ]


def _all_cases():
    cases = []
    for name in _fixture_sets():
        for scen_name, _ in _scenarios(_load_cfg(os.path.join(FIXTURES, name))):
            cases.append((name, scen_name))
    return cases


def _golden_name(scenario):
    return "golden.docx" if scenario is None else f"golden__{scenario}.docx"


def _find(d, *candidates):
    for c in candidates:
        p = os.path.join(d, c)
        if os.path.isfile(p):
            return p
    return None


@pytest.mark.parametrize("set_name,scenario", _all_cases() or [("synthetic", None)])
def test_golden(set_name, scenario, frozen_now, tmp_path):
    import webapp.report_service as report_service

    src = os.path.join(FIXTURES, set_name)
    if not os.path.isfile(os.path.join(src, "inputs.json")):
        pytest.skip(f"no fixture set at {src} (drop files per its README to enable)")

    cfg = _load_cfg(src)
    inputs = dict(_scenarios(cfg))[scenario]

    template = _find(src, "template.docx")
    excel = _find(src, "data.xlsm", "data.xlsx")
    xml = _find(src, "schematic.xml") if inputs.get("xml") is not False else None
    if not (template and excel):
        pytest.skip(f"{set_name}: template/data files not present locally "
                    f"(large real fixtures are git-ignored) — skipping")

    # Work in a temp copy so nothing in the repo is mutated (the pipeline writes a
    # RawData workbook and the report beside the inputs).
    work = os.path.join(tmp_path, "work")
    shutil.copytree(src, work)

    result = report_service.generate(
        template_path=os.path.join(work, os.path.basename(template)),
        company_name=inputs.get("company_name"),
        company_logo_path=(os.path.join(work, inputs["company_logo"]) if inputs.get("company_logo") else None),
        excel_path=os.path.join(work, os.path.basename(excel)),
        working_dir=work,
        xml_path=(os.path.join(work, os.path.basename(xml)) if xml else None),
        config=inputs.get("config"),
        damage_count=inputs.get("damage_count", 0),
        include_disclaimer=inputs.get("include_disclaimer", False),
        wellhead_damage=inputs.get("wellhead_damage"),
        well_name=inputs.get("well_name"),
        well_type=inputs.get("well_type"),
        btm_depth=inputs.get("btm_depth"),
        field=inputs.get("field"),
        log_date=inputs.get("log_date"),
        orig_comp=inputs.get("orig_comp"),
        last_wko=inputs.get("last_wko"),
    )
    produced = result["output_path"]
    assert os.path.isfile(produced), f"{set_name}/{scenario}: no output produced"

    golden = os.path.join(src, _golden_name(scenario))
    if not os.path.isfile(golden):
        shutil.copyfile(produced, golden)
        pytest.fail(f"{set_name}/{scenario}: no {os.path.basename(golden)} — created one. "
                    f"Review it, then commit it to lock the baseline.")

    diffs = diff_docx(golden, produced)
    assert not diffs, (f"{set_name}/{scenario}: report differs from golden:\n"
                       + "\n".join(diffs))
