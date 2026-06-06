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
                            output_path=None, highest_top_n=4, progress=None):
    """Build the report and return the output .docx path.

    `progress(msg)` is an optional callback used to stream status to the UI.
    """
    def log(msg):
        if progress:
            progress(msg)

    validate_inputs(word_template_path, excel_data_path, working_dir)
    _require_docx()

    if output_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(working_dir, f"Automation_Report_{stamp}.docx")

    # ---- 1) Tables: template -> output ----
    log("Filling tables from workbook…")
    from . import tables
    tables.fill_report_tables(
        word_template_path, excel_data_path, output_path,
        highest_top_n=highest_top_n, progress=log,
    )

    # ---- 2) Images: output -> output (in place) ----
    img_folder = resolve_image_folder(working_dir)
    log(f"Placing images from: {img_folder}")
    from . import images
    images.place_report_images(output_path, img_folder, output_path, progress=log)

    log(f"Done → {output_path}")
    return output_path
