"""Preview service — DOCX → PDF → PNG pages.

docx2pdf drives Microsoft Word. On Windows, Word is automated via COM, which must
be initialized on the thread that calls it (FastAPI runs sync endpoints in a
threadpool worker, not the main thread) — so we CoInitialize/CoUninitialize
around the conversion. On macOS docx2pdf uses AppleScript and needs no COM.

If Word isn't available, `PreviewError` is raised with a clear message. The
report .docx itself is produced earlier by the engine, so a failed preview never
blocks document generation.
"""

import os
import logging

from .config import DATA_DIR

logger = logging.getLogger("webapp.preview")

OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")

PREVIEW_DPI = 120


class PreviewError(Exception):
    """Raised when the preview (PDF conversion or rasterization) can't run."""


def _convert_docx_to_pdf(docx_path, pdf_path):
    """Convert a .docx to .pdf via docx2pdf (Microsoft Word).

    Initializes COM on Windows so this is safe to call from a server worker
    thread. Raises PreviewError with a clear message if Word/docx2pdf is missing
    or the conversion fails.
    """
    need_com = (os.name == "nt")
    if need_com:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001 — COM init is best-effort
            need_com = False

    try:
        try:
            from docx2pdf import convert
        except ImportError as e:
            raise PreviewError(
                "PDF preview needs the 'docx2pdf' package (and Microsoft Word). "
                f"The .docx was still generated. Details: {e}"
            ) from e

        try:
            convert(docx_path, pdf_path)
        except Exception as e:  # noqa: BLE001 — Word missing / automation failure
            raise PreviewError(
                "Couldn't convert to PDF — Microsoft Word may not be installed or "
                "available. The .docx was still generated. "
                f"Details: {e}"
            ) from e
    finally:
        if need_com:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass


def _render_pdf_to_pngs(pdf_path, dpi=PREVIEW_DPI):
    """Rasterize each PDF page to PNG bytes at the given DPI using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise PreviewError(f"PDF preview needs PyMuPDF. Details: {e}") from e

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            pages.append(pix.tobytes("png"))
    return pages


def generate_preview(docx_path, pdf_path, dpi=PREVIEW_DPI):
    """Full pipeline: .docx -> .pdf (under outputs/) -> list of PNG bytes.

    Returns a list of PNG byte strings, one per page. Raises PreviewError on any
    failure (caller decides how to surface it without losing the .docx).
    """
    if not docx_path or not os.path.isfile(docx_path):
        raise PreviewError("Source .docx not found for preview.")

    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    _convert_docx_to_pdf(docx_path, pdf_path)

    if not os.path.isfile(pdf_path):
        raise PreviewError("PDF was not produced by the Word conversion.")

    pages = _render_pdf_to_pngs(pdf_path, dpi)
    logger.info("Preview rendered: %d page(s) from %s", len(pages), os.path.basename(pdf_path))
    return pages
