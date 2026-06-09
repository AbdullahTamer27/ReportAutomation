"""Interval Generator service.

Mirrors the desktop Interval Generator's "update template in place" path, reusing
the same `well_tools.core` functions (unmodified): parse a WellSchematic XML,
build the interval + pipe-summary tables (with optional THICKNESS-based
Channel/Offset rows), and write/overwrite the 'Raw Data' sheet in the given Excel
template. The rest of the workbook is untouched.
"""

import os
import logging

logger = logging.getLogger("webapp.interval")


class IntervalInputError(Exception):
    """Raised when the XML or template inputs are missing or invalid."""


def _build_preview_text(interval_df, pipe_summary_df):
    """Recreate the desktop tool's text preview of the generated tables."""
    lines = ["===== TABLE 1 — INTERVALS =====", ""]
    for i, row in interval_df.iterrows():
        lines.append(f"Interval {i + 1}: {row['Start Depth (ft)']} – {row['End Depth (ft)']} ft")
        for cfg in row["Configurations"]:
            lines.append(f"   • {cfg}")
        if "Channels" in interval_df.columns:
            lines.append(f"   Channel: {'-'.join(str(v) for v in row['Channels'])}")
            lines.append(f"   Offset:  {'/'.join(str(v) for v in row['Offsets'])}")
        lines.append("")
    lines.append("===== TABLE 2 — PIPE SUMMARY =====")
    lines.append("")
    lines.append(pipe_summary_df.to_string(index=False))
    return "\n".join(lines)


def generate_raw_data(xml_path, template_path):
    """Parse the XML and update the 'Raw Data' sheet of the template in place.

    Returns a summary dict. Raises IntervalInputError for bad inputs and lets
    PermissionError propagate (file open in Excel).
    """
    from well_tools.core.xml_parser import parse_wellschematic_xml, build_pipe_summary
    from well_tools.core.intervals import build_intervals_from_xml
    from well_tools.core.thickness import parse_thickness_sections
    from well_tools.core.excel_output import write_raw_data_to_template

    if not xml_path or not os.path.isfile(xml_path):
        raise IntervalInputError("XML file not found. Please choose a WellSchematic .xml file.")
    if not xml_path.lower().endswith(".xml"):
        raise IntervalInputError("The schematic must be a .xml file.")
    if not template_path or not os.path.isfile(template_path):
        raise IntervalInputError("Excel template not found. Please choose a .xlsx/.xlsm template.")
    if not template_path.lower().endswith((".xlsx", ".xlsm")):
        raise IntervalInputError("The template must be a .xlsx or .xlsm file.")

    xml_data = parse_wellschematic_xml(xml_path)

    # Optional THICKNESS sheet → Channel/Offset rows (same handling as desktop).
    thickness_sections = None
    try:
        sections = parse_thickness_sections(template_path)
        if sections:
            thickness_sections = sections
            thickness_note = (f"THICKNESS sheet found ({len(sections)} sections) "
                              "— Channel/Offset rows added.")
        else:
            thickness_note = ("THICKNESS sheet present but unreadable "
                              "— Channel/Offset rows omitted.")
    except ValueError as te:
        if str(te) == "NO_THICKNESS_SHEET":
            thickness_note = "No THICKNESS sheet — Channel/Offset rows omitted."
        else:
            thickness_note = f"THICKNESS read issue: {te} — rows omitted."

    pipe_summary_df = build_pipe_summary(xml_data)
    interval_df = build_intervals_from_xml(xml_data, thickness_sections=thickness_sections)

    write_raw_data_to_template(template_path, pipe_summary_df, interval_df)

    pipe_types = {str(k): int(v) for k, v in xml_data["Type"].value_counts().to_dict().items()}
    logger.info("Interval: %d pipes, %d intervals -> %s",
                len(xml_data), len(interval_df), template_path)

    return {
        "template_path": template_path,
        "num_pipes": int(len(xml_data)),
        "pipe_types": pipe_types,
        "depth_min": float(xml_data["Start"].min()),
        "depth_max": float(xml_data["End"].max()),
        "num_intervals": int(len(interval_df)),
        "thickness_note": thickness_note,
        "preview": _build_preview_text(interval_df, pipe_summary_df),
    }
