"""Produce the one-page summary picture for a report run.

This is the seam between the web app and the OPS renderer. It sits here rather
than in ``well_tools/report`` because it needs things only the web app has: the
submitted form fields, and the field registry's defaults (which is where "a
blank rig means RIGLESS" is written down).

The picture is drawn from the bundled Excel template without Excel ever running
— see ``well_tools.report.ops_render``. Nothing here is allowed to fail a
report: every failure becomes a note and the run continues, because a report
without its summary is worth far more than no report at all.
"""

import os

from well_tools.report import ops_render
from well_tools.report.tables import (
    GRADE_IDX, MAX_LOSS_DEPTH_IDX, MAX_LOSS_IDX, fmt, worst_joint,
)

from . import config
from .field_registry import user_fields

# The image tag the report places, and the file the image pass looks for.
OPS_TAG = "{{ops}}"
OPS_IMAGE_NAME = "ops.png"


def wanted(template_tags):
    """True if the chosen Word template asks for the summary."""
    return OPS_TAG in (template_tags or ())


def field_defaults():
    """What each tag says when its field is left blank, from the registry — so
    the summary and the Word document word it identically."""
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


def build(*, img_folder, xml_path, excel_path, pipe_model, fields,
          proc_name="proc.jpg", notes=None, progress=None):
    """Draw the summary into `img_folder` as ``ops.png``, for the report's image
    pass to place against ``{{ops}}``.

    Returns the image path, or None. Anything that goes wrong is appended to
    `notes` rather than raised.
    """
    log = progress or (lambda m: None)
    notes = notes if notes is not None else []

    if not xml_path or not os.path.isfile(xml_path):
        notes.append("⚠ One-page summary not built — it needs the schematic XML.")
        return None

    try:
        from well_tools.core.xml_parser import build_pipe_summary, parse_wellschematic_xml
        from well_tools.report import _wbcache

        rows = build_pipe_summary(parse_wellschematic_xml(xml_path)).to_dict("records")
        workbook = _wbcache.load(excel_path, data_only=True)
        hotspots = collect_hotspots(pipe_model, workbook)
    except Exception as e:  # noqa: BLE001 — never fail a report for the summary
        notes.append(f"⚠ One-page summary not built — {e}")
        return None

    image_path = os.path.join(img_folder, OPS_IMAGE_NAME)
    proc_path = os.path.join(img_folder, proc_name)

    log("Drawing the one-page summary…")
    try:
        result = ops_render.render_ops(
            config.OPS_TEMPLATE_PATH, image_path, fields, rows, hotspots,
            proc_path=proc_path if os.path.isfile(proc_path) else None,
            defaults=field_defaults())
    except ops_render.OpsRenderError as e:
        notes.append(f"⚠ One-page summary not drawn — {e}")
        return None
    except Exception as e:  # noqa: BLE001
        notes.append(f"⚠ One-page summary not drawn — {e}")
        return None

    notes.extend(result.get("warnings") or [])
    if not os.path.isfile(proc_path):
        notes.append(f"⚠ One-page summary: no {proc_name} in the images folder — "
                     "the log half is blank.")
    log(f"OK one-page summary → {OPS_IMAGE_NAME} ({result['size'][0]}x{result['size'][1]})")
    return image_path
