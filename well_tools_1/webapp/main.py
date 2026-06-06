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
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from well_tools.report.report_builder import (  # noqa: E402
    build_automation_report,
    ReportInputError,
)

from .db import init_db, get_db, SessionLocal  # noqa: E402
from .models import Template, ReportRun  # noqa: E402
from .registry import (  # noqa: E402
    seed_templates_from_manifest,
    register_template,
    delete_template,
)
from .config import TEMPLATES_DIR  # noqa: E402
from .preview import generate_preview, PreviewError, OUTPUTS_DIR, PREVIEW_DPI  # noqa: E402
from .interval import generate_raw_data, IntervalInputError  # noqa: E402

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


class GenerateResponse(BaseModel):
    run_id: int
    template_id: int
    well_name: str | None = None
    status: str
    output_path: str
    filename: str


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


class IntervalRequest(BaseModel):
    xml_path: str = Field(..., description="Absolute path to the WellSchematic .xml file")
    template_path: str = Field(..., description="Absolute path to the .xlsx/.xlsm template to update in place")


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
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    """Serve the single-page frontend."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.on_event("startup")
def _startup():
    """Create tables and seed the registry from the manifest."""
    init_db()
    db = SessionLocal()
    try:
        logger.info("Templates dir: %s", TEMPLATES_DIR)
        seed_templates_from_manifest(db)
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

    logger.info(
        "Generate | template_id=%s (%s) | N=%s | excel=%s | working_dir=%s",
        template.id, template.name, req.damage_count, req.excel_path, req.working_dir,
    )

    def on_progress(msg):
        logger.info("[progress] %s", msg)

    def on_review(msg):
        logger.info("[review]   %s", msg)

    # Use the well name for the output filename if provided (engine output_path).
    output_path = _output_path_for(req.working_dir, req.well_name)

    try:
        output_path = build_automation_report(
            word_template_path=template.file_path,
            excel_data_path=req.excel_path,
            working_dir=req.working_dir,
            output_path=output_path,
            damage_count=req.damage_count,
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
    )


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
