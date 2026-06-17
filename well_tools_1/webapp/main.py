"""FastAPI app — Phases 1–2.

Wraps the existing report engine (`well_tools.report.report_builder`) behind a
small JSON API, and adds the storage layer: a SQLite DB (templates registry +
report-run history) seeded from TEMPLATES_DIR/manifest.json on startup.

Run (from the `well_tools_1/` directory):

    uvicorn webapp.main:app --reload

Then open http://127.0.0.1:8000/docs to try the endpoints.
"""

import os
import re
import sys
import base64
import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# --- Make the sibling `well_tools` package importable regardless of CWD -------
# webapp/main.py -> webapp/ -> well_tools_1/  (which contains `well_tools`)
# In dev mode, make well_tools importable from well_tools_1/.
# When frozen by PyInstaller, sys.path is already managed — skip this.
if not getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)

from well_tools.report.report_builder import (  # noqa: E402
    build_automation_report,
    ReportInputError,
)

from .db import init_db, get_db, SessionLocal  # noqa: E402
from .models import Template, ReportRun, Company  # noqa: E402
from .registry import (  # noqa: E402
    seed_templates_from_manifest,
    register_template,
    delete_template,
    seed_companies_from_manifest,
    register_company,
    delete_company,
)
from .config import TEMPLATES_DIR, ensure_user_data  # noqa: E402
from .preview import generate_preview, PreviewError, OUTPUTS_DIR, PREVIEW_DPI  # noqa: E402
from .interval import generate_raw_data, IntervalInputError  # noqa: E402
from .ghost import merge_ghost_collars, GhostInputError  # noqa: E402

from well_tools.report.pipe_config import build_pipe_model, ConfigParseError  # noqa: E402

# --- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("webapp.report")


# --- API models --------------------------------------------------------------
class TemplateOut(BaseModel):
    id: int
    name: str
    damage_count: int
    config_key: str
    file_path: str
    placeholders: list | None = None
    created_at: datetime
    updated_at: datetime


class GenerateRequest(BaseModel):
    template_id: int = Field(..., description="ID of a registered template (chosen by configuration)")
    excel_path: str = Field(..., description="Absolute path to the .xlsx/.xlsm data workbook")
    working_dir: str = Field(..., description="Folder holding images (IMGS/ or itself); the report is saved here")
    well_name: str | None = Field(None, description="Well name; used for the output filename and recorded in history")
    damage_count: int = Field(0, ge=0, description="N: number of damage points (each = 3 pictures). 0 = none.")
    company_id: int = Field(..., description="ID of the registered company whose logo goes in {{COMP}} + headers")
    include_disclaimer: bool = Field(False, description="Keep the {{DISC}} disclaimer table (else remove it)")
    config: str | None = Field(None, description="Configuration string for the universal master template, e.g. 4.5x3.5TBG-7LNR-9.625")
    log_date: str | None = Field(None, description="Replaces the {{log_date}} text tag (normalized to DD-Mon-YYYY)")
    orig_comp: str | None = Field(None, description="Original completion — replaces {{orig_comp}} (DD-Mon-YYYY)")
    last_wko: str | None = Field(None, description="Last workover — replaces {{last_wko}} (DD-Mon-YYYY)")
    well_type: str | None = Field(None, description="Replaces the {{well_type}} text tag")
    btm_depth: str | None = Field(None, description="Bottom depth — replaces {{btm_depth}}")


class GenerateResponse(BaseModel):
    run_id: int
    template_id: int
    well_name: str | None = None
    status: str
    output_path: str
    filename: str
    notes: list[str] = []   # curated engine review items (warnings, corrections, info)


class PreviewResponse(BaseModel):
    run_id: int
    page_count: int
    pages: list[str]   # PNG data URIs, one per page
    pdf_path: str


class TemplateRegisterRequest(BaseModel):
    file_path: str = Field(..., description="Absolute path to the .docx file (from native picker)")
    name: str = Field(..., description="Human-readable label shown in the dropdown")
    config_key: str = Field(..., description="Configuration key, e.g. '4.5-7-9-13'")


class TemplateRegisterResponse(BaseModel):
    id: int
    name: str
    config_key: str
    file_path: str
    created: bool   # True = new, False = updated existing


class CompanyOut(BaseModel):
    id: int
    name: str
    logo_path: str
    created_at: datetime
    updated_at: datetime


class CompanyRegisterRequest(BaseModel):
    file_path: str = Field(..., description="Absolute path to the logo image (from native picker)")
    name: str = Field(..., description="Company name shown in the dropdown")


class CompanyRegisterResponse(BaseModel):
    id: int
    name: str
    logo_path: str
    created: bool   # True = new, False = updated existing


class ConfigPreviewRequest(BaseModel):
    config: str = Field(..., description="Configuration string, e.g. 4.5x3.5TBG-7LNR-9.625")
    excel_path: str | None = Field(None, description="Optional workbook to read shoe depth / joint counts")


class PipeOut(BaseModel):
    index: int
    role: str
    sizes: list[float]
    tapered: bool
    type: str
    name: str
    suffix: str
    sheet: str
    joint_count: int | None = None
    shoe: float | None = None
    shoe_text: str = ""


class ConfigPreviewResponse(BaseModel):
    pipes: list[PipeOut]
    warnings: list[str]


class IntervalRequest(BaseModel):
    xml_path: str = Field(..., description="Absolute path to the WellSchematic .xml file")
    template_path: str = Field(..., description="Absolute path to the .xlsx/.xlsm template to update in place")


class GhostRequest(BaseModel):
    csv_path: str = Field(..., description="Absolute path to the SmartLog Joint-Analysis .csv")
    ghost_collar_length: float = Field(3.0, gt=0, description="Merge collars >= this length (ft)")
    output_path: str | None = Field(None, description="Optional .xlsx output path; defaults beside the CSV")


class GhostResponse(BaseModel):
    csv_path: str
    output_path: str
    threshold: float
    input_rows: int
    output_rows: int
    merged_chains: int
    preview: str


class IntervalResponse(BaseModel):
    template_path: str
    num_pipes: int
    pipe_types: dict
    depth_min: float
    depth_max: float
    num_intervals: int
    thickness_note: str
    preview: str


# --- App ---------------------------------------------------------------------
app = FastAPI(title="Report Automation — Web API", version="0.3.0")

# Serve the vanilla frontend from webapp/static/.
# When frozen, __file__ is inside sys._MEIPASS (the bundled tree).
# In dev, it is next to this source file.  Both resolve the same relative path.
_HERE = (
    sys._MEIPASS
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
STATIC_DIR = os.path.join(_HERE, "webapp", "static") if getattr(sys, "frozen", False) \
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    """Serve the single-page frontend."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.on_event("startup")
def _startup():
    """Create tables and seed the registry from the manifest."""
    # On a frozen build, copy bundled templates into the persistent data dir
    # (%APPDATA%\WellTools) on first run before anything reads the manifest.
    ensure_user_data()
    init_db()
    db = SessionLocal()
    try:
        logger.info("Templates dir: %s", TEMPLATES_DIR)
        seed_templates_from_manifest(db)
        seed_companies_from_manifest(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/interval/generate", response_model=IntervalResponse)
def interval_generate(req: IntervalRequest):
    """Interval Generator: parse the XML and update the template's 'Raw Data'
    sheet in place (same behavior as the desktop tool's template path)."""
    logger.info("Interval generate | xml=%s | template=%s", req.xml_path, req.template_path)
    try:
        result = generate_raw_data(req.xml_path, req.template_path)
    except IntervalInputError as e:
        logger.warning("Interval input error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError:
        raise HTTPException(
            status_code=423,
            detail="Can't write to the template — it may be open in Excel. Close it and retry.",
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Interval generation failed")
        raise HTTPException(status_code=500, detail=f"Interval generation failed: {e}")
    return IntervalResponse(**result)


@app.post("/api/config/preview", response_model=ConfigPreviewResponse)
def config_preview(req: ConfigPreviewRequest):
    """Parse a configuration string into the pipe model (and, if an Excel path is
    given, each pipe's shoe depth + joint count) so the UI can show the mapping
    before generating. Read-only."""
    try:
        result = build_pipe_model(req.config, req.excel_path)
    except ConfigParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Config preview failed")
        raise HTTPException(status_code=500, detail=f"Config preview failed: {e}")
    return ConfigPreviewResponse(**result)


@app.post("/api/ghost/merge", response_model=GhostResponse)
def ghost_merge(req: GhostRequest):
    """Ghost Collar Merger: merge ghost-collar chains in a Joint-Analysis CSV and
    write a cleaned .xlsx next to it (or to output_path)."""
    logger.info("Ghost merge | csv=%s | threshold=%s", req.csv_path, req.ghost_collar_length)
    try:
        result = merge_ghost_collars(req.csv_path, req.ghost_collar_length, req.output_path)
    except GhostInputError as e:
        logger.warning("Ghost input error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Ghost merge failed")
        raise HTTPException(status_code=500, detail=f"Ghost merge failed: {e}")
    return GhostResponse(**result)


def _template_to_dict(t: Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "damage_count": t.damage_count,
        "config_key": t.config_key,
        "file_path": t.file_path,
        "placeholders": t.placeholders,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@app.get("/api/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    """Registry rows for populating the template dropdown."""
    rows = db.query(Template).order_by(Template.damage_count, Template.config_key).all()
    return [_template_to_dict(t) for t in rows]


@app.post("/api/templates/register", response_model=TemplateRegisterResponse)
def template_register(req: TemplateRegisterRequest, db: Session = Depends(get_db)):
    """Copy a .docx into the templates directory and register it.
    If a template with the same config_key already exists it is updated."""
    req.name = req.name.strip()
    req.config_key = req.config_key.strip()
    if not req.name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if not req.config_key:
        raise HTTPException(status_code=400, detail="Configuration key is required.")

    # Was there an existing entry for this config_key before registering?
    existing_before = (
        db.query(Template).filter_by(config_key=req.config_key, damage_count=0).one_or_none()
    )
    try:
        t = register_template(db, req.name, req.config_key, req.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Template registration failed")
        raise HTTPException(status_code=500, detail=f"Registration failed: {e}")

    return TemplateRegisterResponse(
        id=t.id,
        name=t.name,
        config_key=t.config_key,
        file_path=t.file_path,
        created=existing_before is None,
    )


@app.delete("/api/templates/{template_id}")
def template_delete(template_id: int, db: Session = Depends(get_db)):
    """Remove a template from the registry (does not delete the .docx file)."""
    found = delete_template(db, template_id, remove_file=False)
    if not found:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found.")
    return {"ok": True, "deleted_id": template_id}


def _company_to_dict(c: Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "logo_path": c.logo_path,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


@app.get("/api/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    """Registry rows for populating the company dropdown."""
    rows = db.query(Company).order_by(Company.name).all()
    return [_company_to_dict(c) for c in rows]


@app.post("/api/companies/register", response_model=CompanyRegisterResponse)
def company_register(req: CompanyRegisterRequest, db: Session = Depends(get_db)):
    """Copy a logo image into the companies directory and register it.
    If a company with the same name already exists it is updated."""
    req.name = req.name.strip()
    if not req.name:
        raise HTTPException(status_code=400, detail="Company name is required.")

    existing_before = db.query(Company).filter_by(name=req.name).one_or_none()
    try:
        c = register_company(db, req.name, req.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Company registration failed")
        raise HTTPException(status_code=500, detail=f"Registration failed: {e}")

    return CompanyRegisterResponse(
        id=c.id,
        name=c.name,
        logo_path=c.logo_path,
        created=existing_before is None,
    )


@app.delete("/api/companies/{company_id}")
def company_delete(company_id: int, db: Session = Depends(get_db)):
    """Remove a company from the registry and delete its logo file from disk."""
    found = delete_company(db, company_id, remove_file=True)
    if not found:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found.")
    return {"ok": True, "deleted_id": company_id}


@app.post("/api/report/generate", response_model=GenerateResponse)
def generate_report(req: GenerateRequest, db: Session = Depends(get_db)):
    """Generate a report from a registered template, and record the run.

    Looks up the template's file_path, calls the engine, then inserts a
    report_runs row capturing success/failure. Engine progress/review callbacks
    are routed to the server log.
    """
    template = db.get(Template, req.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template id {req.template_id} not found.")

    company = db.get(Company, req.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company id {req.company_id} not found.")
    if not company.logo_path or not os.path.isfile(company.logo_path):
        raise HTTPException(
            status_code=400,
            detail=f"Logo file for company '{company.name}' is missing on disk.",
        )

    logger.info(
        "Generate | template_id=%s (%s) | company=%s | N=%s | disc=%s | excel=%s | working_dir=%s",
        template.id, template.name, company.name, req.damage_count,
        req.include_disclaimer, req.excel_path, req.working_dir,
    )

    review_notes: list[str] = []

    def on_progress(msg):
        logger.info("[progress] %s", msg)

    def on_review(msg):
        logger.info("[review]   %s", msg)
        review_notes.append(str(msg))

    # Use the well name for the output filename if provided (engine output_path).
    output_path = _output_path_for(req.working_dir, req.well_name)

    # Plain-text tags replaced anywhere in the document (run-preserving). These
    # fields are OPTIONAL (only configuration, company, and number of damages are
    # required): a blank gets a default value and a warning in the report notes.
    # Date fields are normalized to DD-Mon-YYYY; non-dates ("N/A") pass through.
    OPTIONAL_DEFAULT = "N/A"
    defaulted = []

    def _opt(value, label):
        if value is None or not str(value).strip():
            defaulted.append(label)
            return OPTIONAL_DEFAULT
        return str(value)

    def _opt_date(value, label):
        if value is None or not str(value).strip():
            defaulted.append(label)
            return OPTIONAL_DEFAULT
        return _normalize_date(value)

    text_fields = {
        "{{well_name}}": _opt(req.well_name, "Well name"),
        "{{well_type}}": _opt(req.well_type, "Well type"),
        "{{btm_depth}}": _opt(req.btm_depth, "Bottom depth"),
        "{{log_date}}": _opt_date(req.log_date, "Log date"),
        "{{orig_comp}}": _opt_date(req.orig_comp, "Original completion"),
        "{{last_wko}}": _opt_date(req.last_wko, "Last workover"),
    }
    if defaulted:
        review_notes.append(
            f"⚠ Left blank — defaulted to '{OPTIONAL_DEFAULT}': " + ", ".join(defaulted) + "."
        )

    # Company-conditional lines: kept only when that company is chosen.
    is_weatherford = (company.name or "").strip().lower() == "weatherford"
    conditional_lines = {"{{weatherford_corr}}": is_weatherford}

    # Universal master template: parse the configuration into the pipe model and
    # add each pipe's metadata tags. Absent here ⇒ legacy per-config template.
    pipe_model = None
    text_fields_quiet = None
    if req.config and req.config.strip():
        try:
            pm = build_pipe_model(req.config, req.excel_path, review=on_review)
        except ConfigParseError as e:
            raise HTTPException(status_code=400, detail=f"Configuration: {e}")
        pipe_model = pm["pipes"]
        pipe_tags = set()
        for p in pipe_model:
            role = p["role"]
            for key, val in (("name", p["name"]), ("suffix", p["suffix"]), ("shoe", p["shoe_text"])):
                tag = f"{{{{{role}_{key}}}}}"
                text_fields[tag] = val
                pipe_tags.add(tag)
        # Auto-derived pipe tags: don't warn if a template doesn't use every variant.
        text_fields_quiet = pipe_tags

    try:
        output_path = build_automation_report(
            word_template_path=template.file_path,
            excel_data_path=req.excel_path,
            working_dir=req.working_dir,
            output_path=output_path,
            damage_count=req.damage_count,
            include_disclaimer=req.include_disclaimer,
            company_logo_path=company.logo_path,
            company_name=company.name,
            text_fields=text_fields,
            conditional_lines=conditional_lines,
            pipe_model=pipe_model,
            text_fields_quiet=text_fields_quiet,
            progress=on_progress,
            review=on_review,
        )
    except ReportInputError as e:
        logger.warning("Input error: %s", e)
        _record_run(db, template.id, req, None, "failed")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — surface anything else cleanly
        logger.exception("Report generation failed")
        _record_run(db, template.id, req, None, "failed")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")

    run = _record_run(db, template.id, req, output_path, "success")
    logger.info("Report generated: %s (run_id=%s)", output_path, run.id)
    return GenerateResponse(
        run_id=run.id,
        template_id=template.id,
        well_name=req.well_name,
        status=run.status,
        output_path=output_path,
        filename=os.path.basename(output_path),
        notes=review_notes,
    )


# Accepted date inputs, parsed in order and reformatted to DD-Mon-YYYY.
# Ambiguous numeric forms are read day-first (regional convention).
_DATE_INPUT_FORMATS = (
    "%d-%b-%Y", "%d-%B-%Y",          # 09-Sep-2020 / 09-September-2020 (target-ish)
    "%Y-%m-%d", "%Y/%m/%d",          # ISO (also what a date picker yields)
    "%d %b %Y", "%d %B %Y",          # 09 Sep 2020 / 09 September 2020
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",   # day-first numeric
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y",  # Sep 9, 2020
)
_DATE_OUTPUT_FORMAT = "%d-%b-%Y"     # -> 09-Sep-2020


def _normalize_date(value):
    """Reformat a date-like string to DD-Mon-YYYY (e.g. 09-Sep-2020).

    Tries a fixed set of common formats; if none match (e.g. "N/A", "", or free
    text), the original value is returned unchanged so the report still fills it.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    for fmt in _DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime(_DATE_OUTPUT_FORMAT)
        except ValueError:
            continue
    return s


def _safe_filename(name: str) -> str:
    """Make a filesystem-safe stem from a well name."""
    s = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip().strip(".")
    return s


def _output_path_for(working_dir: str, well_name):
    """Build an output .docx path from the well name, or None to let the engine
    use its timestamped default."""
    if not well_name:
        return None
    stem = _safe_filename(well_name)
    if not stem:
        return None
    return os.path.join(working_dir, f"{stem}_report.docx")


@app.post("/api/preview/{run_id}", response_model=PreviewResponse)
def preview_run(run_id: int, db: Session = Depends(get_db)):
    """Render the run's .docx to PDF then to PNG page images.

    Sync endpoint (runs in the threadpool) so the blocking Word conversion stays
    off the event loop. COM is initialized per-call on Windows. If Word/preview
    isn't available, returns 503 with a clear message — the .docx is unaffected.
    """
    run = db.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run id {run_id} not found.")
    if run.status != "success" or not run.output_docx_path:
        raise HTTPException(status_code=400, detail="This run has no generated document to preview.")

    pdf_path = os.path.join(OUTPUTS_DIR, f"run_{run_id}.pdf")
    try:
        page_pngs = generate_preview(run.output_docx_path, pdf_path, dpi=PREVIEW_DPI)
    except PreviewError as e:
        logger.warning("Preview unavailable for run %s: %s", run_id, e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Preview failed for run %s", run_id)
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")

    pages = [
        "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        for png in page_pngs
    ]
    return PreviewResponse(
        run_id=run_id,
        page_count=len(pages),
        pages=pages,
        pdf_path=pdf_path,
    )


def _record_run(db: Session, template_id: int, req: GenerateRequest,
                output_path, status: str) -> ReportRun:
    run = ReportRun(
        template_id=template_id,
        well_name=req.well_name,
        excel_path=req.excel_path,
        working_dir=req.working_dir,
        output_docx_path=output_path,
        status=status,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
