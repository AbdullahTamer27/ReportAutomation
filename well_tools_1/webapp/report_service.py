"""Report-generation orchestration — the transport-agnostic core.

This is the seam between *what a report is* and *how the request arrived*. It
takes already-resolved, plain inputs (file paths, well fields, flags) and drives
the engine: builds the text tags, parses the configuration into a pipe model,
computes the damage clusters, writes the Raw Data workbook, and calls the report
builder. It returns ``{output_path, notes}``.

It raises domain errors (``ConfigParseError`` from a bad configuration,
``ReportInputError`` from the builder) rather than HTTP errors, so the caller —
today ``webapp.main``, tomorrow possibly an upload endpoint or a CLI — decides how
to surface them. No FastAPI, no database, no request objects here.
"""

import os
from datetime import datetime

from well_tools.report.report_builder import build_automation_report  # noqa: F401
from well_tools.report.pipe_config import (
    build_pipe_model, ConfigParseError, sizes_with_label, pipe_config_phrase,  # noqa: F401
)

from .naming import normalize_date, safe_filename, report_filename
from .field_registry import user_fields
from .interval import generate_raw_data_file, IntervalInputError

OPTIONAL_DEFAULT = "N/A"


def generate(*, template_path, company_name, company_logo_path,
             excel_path, working_dir, xml_path,
             config, damage_count=0, include_disclaimer=False, wellhead_damage=None,
             fw16=False, fields=None,
             progress=None, review=None):
    """Generate a report and return ``{"output_path": str, "notes": [str, ...]}``.

    ``progress`` / ``review`` are optional callbacks used for streaming/logging;
    every review message is also captured in the returned ``notes`` list.
    Raises ``ConfigParseError`` for an unparseable configuration and
    ``ReportInputError`` (or other exceptions) from the builder.
    """
    notes: list[str] = []
    log = progress or (lambda m: None)

    def on_review(msg):
        # Engine review messages: capture for the caller AND forward for logging.
        notes.append(str(msg))
        if review:
            review(msg)

    # User-input metadata values, keyed by registry key ({well_name, log_date, …}).
    fields = fields or {}

    # Output filename: wellname_logdate_EPDT_RIGLESS_REPORT_companyname.docx
    output_path = os.path.join(
        working_dir,
        report_filename(fields.get("well_name"),
                        normalize_date(fields.get("log_date")), company_name),
    )

    # Plain-text tags replaced anywhere in the document (run-preserving). The
    # user-input metadata fields come from the field registry (single source of
    # truth) — each is OPTIONAL: a blank gets OPTIONAL_DEFAULT and a note; fields
    # marked normalize="date" are formatted DD-Mon-YYYY, non-dates ("N/A") pass
    # through. Adding a field is one registry entry — no change here.
    defaulted = []

    def _opt_field(f):
        raw = fields.get(f.key)
        if raw is None or not str(raw).strip():
            defaulted.append(f.label)
            return OPTIONAL_DEFAULT
        return normalize_date(raw) if f.normalize == "date" else str(raw)

    text_fields = {f.tag: _opt_field(f) for f in user_fields()}
    text_fields.update({
        # Delivery date = today's date, formatted like the other dates. Auto-filled.
        "{{delivery_date}}": datetime.now().strftime("%d-%b-%Y"),
        # Damage present ⇒ " and Hotspots" (place the tag right after the word,
        # e.g. "Metal Loss{{hotspot}}"); no damage ⇒ nothing.
        "{{hotspot}}": " and Hotspots" if damage_count else "",
        # Tool-type K-factors: FW16 uses a flat 1.2 set; the default otherwise.
        "{{tool_type}}": ("(K1=1.2, K2=1.2, K3=1.2, K4=1.2)" if fw16
                          else "(K1=0.45, K2=0.55, K3=0.7, K4=0.9)"),
    })
    if defaulted:
        notes.append(
            f"⚠ Left blank — defaulted to '{OPTIONAL_DEFAULT}': " + ", ".join(defaulted) + "."
        )
    # Auto-derived tags never nag if a template doesn't use them.
    text_fields_quiet = {"{{delivery_date}}", "{{hotspot}}", "{{tool_type}}"}

    # Company-conditional lines: kept only when that company is chosen.
    is_weatherford = (company_name or "").strip().lower() == "weatherford"
    conditional_lines = {"{{weatherford_corr}}": is_weatherford}

    # Universal master template: parse the configuration into the pipe model and
    # add each pipe's metadata tags. Absent here ⇒ legacy per-config template.
    pipe_model = None
    if config and config.strip():
        pm = build_pipe_model(config, excel_path, review=on_review, xml_path=xml_path)
        pipe_model = pm["pipes"]
        for p in pipe_model:
            role = p["role"]
            for key, val in (("name", p["name"]), ("suffix", p["suffix"]),
                             ("shoe", p["shoe_text"]), ("highest_grade", p["highest_severity"])):
                tag = f"{{{{{role}_{key}}}}}"
                text_fields[tag] = val
                text_fields_quiet.add(tag)
        # Casing / liner / tubing lists, largest first, ending with the type word
        # (e.g. '18 5/8", 13 3/8", 9 5/8" casing strings'). Tubings lead with
        # "and " so they read as the last clause after the casing/liner lists.
        for tag, code in (("{{casings}}", "CSG"), ("{{liners}}", "LNR"), ("{{tubings}}", "TBG")):
            val = sizes_with_label(pipe_model, code)
            if code == "TBG" and val:
                val = f"and {val}"
            text_fields[tag] = val
            text_fields_quiet.add(tag)
        # Natural-language list of pipe types present, e.g. "tubing, liner and casing".
        text_fields["{{pipe_config}}"] = pipe_config_phrase(pipe_model)
        text_fields_quiet.add("{{pipe_config}}")

    # Damage-section overlays: the picture clusters (worst C/D per pipe per
    # interval), enriched with severity + THICKNESS channel. Needs the XML.
    damage_clusters = None
    if pipe_model is not None and xml_path and os.path.isfile(xml_path):
        try:
            from well_tools.report.damage_select import compute_damage_pictures
            damage_clusters = compute_damage_pictures(
                xml_path, excel_path, pipe_model)["pictures"]
        except Exception as e:  # noqa: BLE001 — overlays are best-effort
            log(f"Damage-cluster computation failed: {e}")
            notes.append(f"⚠ Damage overlays skipped — {e}")

    # Interval table (the {{INTERVALS}} block): compute the same interval rows the
    # RawData workbook is built from, so the in-report table matches the Excel.
    # Best-effort; templates without the tag ignore it.
    interval_records = None
    if xml_path and os.path.isfile(xml_path):
        try:
            from well_tools.report.interval_table import build_interval_records
            interval_records = build_interval_records(xml_path, excel_path)
        except Exception as e:  # noqa: BLE001 — non-fatal, table just stays empty
            log(f"Interval-table data failed: {e}")
            notes.append(f"⚠ Interval table skipped — {e}")

    # Fold in the Interval Generator: build the Raw Data table from the XML into a
    # SEPARATE workbook beside the report — the data Excel is never opened for
    # writing, so its macro-computed grades/bars stay intact. Non-fatal.
    if xml_path:
        _wn = fields.get("well_name")
        stem = safe_filename(_wn) if _wn else "well"
        rawdata_path = os.path.join(working_dir, f"{stem}_RawData.xlsx")
        try:
            rd = generate_raw_data_file(xml_path, rawdata_path, data_excel=excel_path)
            note = f"Raw Data written to {os.path.basename(rawdata_path)}"
            note += " (with 'intervals MAIN')." if rd.get("intervals_main") \
                else " — note: no 'intervals MAIN' sheet found in the data Excel."
            notes.append(note)
        except PermissionError:
            notes.append(f"⚠ Raw Data not written — {os.path.basename(rawdata_path)} "
                         "is open. Close it and regenerate.")
        except IntervalInputError as e:
            notes.append(f"⚠ Raw Data not written — {e}")
        except Exception as e:  # noqa: BLE001
            log(f"Raw Data write failed: {e}")
            notes.append(f"⚠ Raw Data not written — {e}")

    output_path = build_automation_report(
        word_template_path=template_path,
        excel_data_path=excel_path,
        working_dir=working_dir,
        output_path=output_path,
        damage_count=damage_count,
        include_disclaimer=include_disclaimer,
        company_logo_path=company_logo_path,
        company_name=company_name,
        text_fields=text_fields,
        conditional_lines=conditional_lines,
        pipe_model=pipe_model,
        text_fields_quiet=text_fields_quiet,
        wellhead_damage=wellhead_damage,
        damage_clusters=damage_clusters,
        interval_records=interval_records,
        single_doc_io=True,   # open the Word file once, save once (verified identical)
        progress=log,
        review=on_review,
    )
    return {"output_path": output_path, "notes": notes}
