"""Automation report builder (Tab 2).

Independent of the Interval Generator. Inputs:
  - word_template_path : a .docx template with tagged tables and image tags
                         ({{joints_<sheet>}} / {{highest_<sheet>}} / {{proc}} ...)
  - excel_data_path    : the Excel workbook (sheets named <...>Pipe, etc.)
  - working_dir        : holds the images AND is where the report is saved.
                         Images are looked for in <working_dir>/IMGS if that
                         subfolder exists, otherwise in <working_dir> itself.

Output: a single .docx report with images and tables.

Pipeline: tables (report.tables) -> images (report.images), both on one doc.
"""

import os
from datetime import datetime


class ReportInputError(Exception):
    """Raised when the three inputs are missing or invalid."""


def _require_docx():
    try:
        import docx  # python-docx  # noqa: F401
    except ImportError as e:
        raise ReportInputError(
            "python-docx is not installed.\n\nRun:  pip install python-docx"
        ) from e


def validate_inputs(word_template_path, excel_data_path, working_dir):
    if not word_template_path or not os.path.isfile(word_template_path):
        raise ReportInputError("Word template not found. Please select a .docx template.")
    if not word_template_path.lower().endswith(".docx"):
        raise ReportInputError("Word template must be a .docx file.")
    if not excel_data_path or not os.path.isfile(excel_data_path):
        raise ReportInputError("Excel data file not found. Please select a .xlsx/.xlsm file.")
    if not excel_data_path.lower().endswith((".xlsx", ".xlsm")):
        raise ReportInputError("Excel data must be a .xlsx or .xlsm file.")
    if not working_dir or not os.path.isdir(working_dir):
        raise ReportInputError("Working directory not found. Please select a folder.")


def resolve_image_folder(working_dir):
    """Use <working_dir>/IMGS if it exists, else the working dir itself."""
    imgs = os.path.join(working_dir, "IMGS")
    return imgs if os.path.isdir(imgs) else working_dir


def build_automation_report(word_template_path, excel_data_path, working_dir,
                            output_path=None, highest_top_n=4, progress=None,
                            review=None, damage_count=0,
                            include_disclaimer=False, company_logo_path=None,
                            company_name=None, text_fields=None,
                            conditional_lines=None, pipe_model=None,
                            text_fields_quiet=None, wellhead_damage=None):
    """Build the report and return the output .docx path.

    `progress(msg)` streams verbose status; `review(msg)` streams only the
    curated review items (failures, warnings, data-sanity flags) to the UI.
    `damage_count` is N: the marked damage block in the template is repeated N
    times (each = 3 images), with N=0 producing no damage pictures.
    `include_disclaimer` keeps the {{DISC}} table (else it is removed).
    `company_logo_path` is the chosen company's logo: placed into the {{COMP}}
    body table and swapped into every header picture tagged {{COMP}}.
    `company_name` replaces the {{COMPNAME}} text tag (footers/body/headers).
    `text_fields` is a {tag: value} map of plain-text tags to replace anywhere
    in the document (e.g. {{well_name}}, {{log_date}}, {{orig_comp}}, {{last_wko}}).
    `conditional_lines` is a {tag: keep?} map: paragraphs containing the tag are
    kept (tag stripped) when keep is True, else removed (e.g. {{weatherford_corr}}).
    `pipe_model` (universal master template) is the ordered list of present pipes;
    when given, per-pipe sections for absent pipes are removed and the summary is
    filled from the model. When None, behaves as the legacy per-config template.
    """
    def log(msg):
        if progress:
            progress(msg)

    validate_inputs(word_template_path, excel_data_path, working_dir)
    _require_docx()

    if output_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(working_dir, f"Automation_Report_{stamp}.docx")

    # ---- 0) Universal master template: keep present pipe sections, drop the rest ----
    if pipe_model is not None:
        from .pipe_config import ROLE_NAMES
        present_roles = [p["role"] for p in pipe_model]
        log(f"Preparing pipe sections (present: {', '.join(present_roles)})…")
        from . import pipe_sections
        pipe_sections.apply_pipe_sections(
            word_template_path, output_path, present_roles, ROLE_NAMES,
            progress=log, review=review,
        )
        tables_src = output_path   # subsequent passes operate on the prepared output
    else:
        tables_src = word_template_path

    # ---- 1) Tables: tables_src -> output ----
    log("Filling tables from workbook…")
    from . import tables
    tables.fill_report_tables(
        tables_src, excel_data_path, output_path,
        highest_top_n=highest_top_n, pipe_model=pipe_model,
        progress=log, review=review,
    )

    # ---- 1.5) Expand damage blocks (N image-sections) on the output ----
    log(f"Expanding damage sections (N={damage_count})…")
    from . import damage_blocks
    damage_blocks.expand_in_file(output_path, damage_count, progress=log, review=review)

    # ---- 1.6) Disclaimer: keep or remove the {{DISC}} table ----
    log(f"Applying disclaimer choice (include={bool(include_disclaimer)})…")
    from . import disclaimer
    disclaimer.apply_in_file(output_path, bool(include_disclaimer),
                             progress=log, review=review)

    # ---- 2) Images: output -> output (in place) ----
    img_folder = resolve_image_folder(working_dir)
    log(f"Placing images from: {img_folder}")
    from . import images
    images.place_report_images(output_path, img_folder, output_path,
                               progress=log, review=review)

    # ---- 2.5) Company logo: body {{COMP}} table + tagged header pictures ----
    if company_logo_path:
        log(f"Placing company logo: {company_logo_path}")
        from . import company
        company.place_company_logo(output_path, company_logo_path,
                                   company_name=company_name,
                                   progress=log, review=review)

    # ---- 2.6) Well-metadata text tags ({{well_name}}, {{log_date}}, …) ----
    if text_fields:
        log("Filling well-metadata text tags…")
        from . import text_fields as tf
        tf.apply_text_fields(output_path, text_fields, progress=log, review=review,
                             quiet_tags=text_fields_quiet)

    # ---- 2.7) Company-conditional lines ({{weatherford_corr}}, …) ----
    if conditional_lines:
        log("Applying company-conditional lines…")
        from . import conditional
        conditional.apply_conditional_lines(output_path, conditional_lines,
                                            progress=log, review=review)

    # ---- 2.8) Per-pipe metal-loss pie charts ({{pie_<role>}}) ----
    if pipe_model is not None:
        log("Rendering per-pipe pie charts…")
        from . import charts
        charts.place_pie_charts(output_path, pipe_model, excel_data_path,
                                progress=log, review=review)

    # ---- 2.9) Floating overlays ({{ovl_*}}) — self-contained pass ----
    if wellhead_damage is not None or pipe_model is not None:
        log("Filling overlay text boxes…")
        from . import overlays
        overlays.apply_overlays(output_path, wellhead_damage=wellhead_damage,
                                pipe_model=pipe_model, excel_path=excel_data_path,
                                progress=log, review=review)

    log(f"Done → {output_path}")
    return output_path
