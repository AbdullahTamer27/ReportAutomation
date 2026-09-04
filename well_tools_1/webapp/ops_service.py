"""Produce the one-page summary picture for a report run.

This is the seam between the web app and the OPS engine modules. It sits here
rather than in ``well_tools/report`` because it needs things only the web app
has: the submitted form fields, and the field registry's defaults (which is
where "a blank rig means RIGLESS" is written down).

The picture is made in two steps — fill the bundled Excel template, then have
Excel render its print area — and **neither is allowed to fail a report**. Every
failure path leaves the filled ``.xlsx`` beside the report and adds a note
saying what to do, because a summary that has to be pasted by hand is still far
better than a run that died producing one.
"""

import os

from well_tools.report import ops_export, ops_fill
from well_tools.report.tables import (
    GRADE_IDX, MAX_LOSS_DEPTH_IDX, MAX_LOSS_IDX, fmt, worst_joint,
)

from . import config
from .field_registry import user_fields
from .naming import safe_filename

# The image tag the report places, and the file the image pass looks for.
OPS_TAG = "{{ops}}"
OPS_IMAGE_NAME = "ops.png"


def wanted(template_tags):
    """True if the chosen Word template asks for the summary."""
    return OPS_TAG in (template_tags or ())


def field_defaults():
    """What each tag says when its field is left blank, from the registry — so
    the workbook and the Word document word it identically."""
    return {f.tag.strip("{}"): f.default for f in user_fields() if f.default}


def collect_hotspots(pipe_model, workbook, top_n=4, review=None):
    """The worst joint per pipe: the same row, and the same corrected grade, the
    ``{{SUMMARY}}`` table in the Word report is built from."""
    hotspots = []
    for pipe in pipe_model or ():
        sheet = pipe.get("sheet")
        if not sheet or sheet not in workbook.sheetnames:
            continue
        vals = worst_joint(workbook[sheet], top_n,
                           table_name=f"ops[{sheet}]", review=review)
        if vals is None:
            continue
        hotspots.append({
            "pipe": pipe,
            "max_loss": fmt(vals[MAX_LOSS_IDX], MAX_LOSS_IDX),
            "grade": str(vals[GRADE_IDX]).strip(),
            "depth": fmt(vals[MAX_LOSS_DEPTH_IDX], MAX_LOSS_DEPTH_IDX),
        })
    return hotspots


def build(*, working_dir, img_folder, xml_path, excel_path, pipe_model, fields,
          well_name=None, proc_name="proc.jpg", notes=None, progress=None):
    """Write the filled workbook and, if Excel can, the picture beside it.

    Returns ``{"workbook": path|None, "image": path|None}``. Anything that goes
    wrong is appended to `notes` rather than raised: the report still generates.
    """
    log = progress or (lambda m: None)
    notes = notes if notes is not None else []

    if not xml_path or not os.path.isfile(xml_path):
        notes.append("⚠ One-page summary not built — it needs the schematic XML.")
        return {"workbook": None, "image": None}

    try:
        from well_tools.core.xml_parser import build_pipe_summary, parse_wellschematic_xml
        from well_tools.report import _wbcache

        rows = build_pipe_summary(parse_wellschematic_xml(xml_path)).to_dict("records")
        workbook = _wbcache.load(excel_path, data_only=True)
        hotspots = collect_hotspots(pipe_model, workbook)
    except Exception as e:  # noqa: BLE001 — never fail a report for the summary
        notes.append(f"⚠ One-page summary not built — {e}")
        return {"workbook": None, "image": None}

    stem = safe_filename(well_name) if well_name else "well"
    xlsx_path = os.path.join(working_dir, f"{stem}_OPS.xlsx")
    proc_path = os.path.join(img_folder, proc_name)

    log("Building the one-page summary…")
    try:
        result = ops_fill.fill_ops(
            config.OPS_TEMPLATE_PATH, xlsx_path, fields, rows, hotspots,
            proc_path=proc_path if os.path.isfile(proc_path) else None,
            defaults=field_defaults())
    except PermissionError:
        notes.append(f"⚠ One-page summary not written — {os.path.basename(xlsx_path)} "
                     "is open. Close it and regenerate.")
        return {"workbook": None, "image": None}
    except Exception as e:  # noqa: BLE001
        notes.append(f"⚠ One-page summary not written — {e}")
        return {"workbook": None, "image": None}

    notes.extend(result.get("warnings") or [])
    log(f"OK one-page summary → {os.path.basename(xlsx_path)}")

    # The picture. Excel is the only thing that lays out an Excel sheet properly,
    # so without it the workbook is handed over to be pasted by hand.
    image_path = os.path.join(img_folder, OPS_IMAGE_NAME)
    try:
        ops_export.render(xlsx_path, image_path)
    except ops_export.OpsExportError as e:
        notes.append(
            f"⚠ One-page summary picture not made — {e}. Open "
            f"{os.path.basename(xlsx_path)} and paste it into the report.")
        return {"workbook": xlsx_path, "image": None}

    log(f"OK one-page summary picture → {OPS_IMAGE_NAME}")
    return {"workbook": xlsx_path, "image": image_path}
