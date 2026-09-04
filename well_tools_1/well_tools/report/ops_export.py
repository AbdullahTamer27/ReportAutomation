"""Turn the filled OPS workbook into the picture the report places.

Excel is the only thing that can lay out an Excel sheet faithfully, so it does
the work: the sheet's **print area** is exported to a one-page PDF, and PyMuPDF
(already bundled for the report preview) renders that page to a PNG. Going via
PDF rather than the usual copy-the-range-to-the-clipboard trick keeps it vector
until the final raster, and avoids the clipboard entirely — which is where that
approach normally breaks.

This is the one step that cannot run anywhere but Windows with Excel installed,
and so the one step the test suite cannot cover. It is therefore written to fail
softly in every direction: if Excel is missing, refuses, or dies halfway, the
filled ``.xlsx`` is still sitting beside the report and the run says so. The
report is produced either way; only the picture is missing.
"""

import os

DEFAULT_DPI = 200


class OpsExportError(Exception):
    """Excel could not turn the workbook into a picture."""


def available():
    """True if this machine can do the export at all (Windows + pywin32)."""
    if os.name != "nt":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def _export_pdf(xlsx_path, pdf_path):
    """Drive Excel to write the sheet's print area out as a PDF.

    Excel is asked to stay silent — no alerts, no dialogs — because a modal
    prompt on a machine nobody is watching would hang the report."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.AskToUpdateLinks = False
        workbook = excel.Workbooks.Open(os.path.abspath(xlsx_path),
                                        UpdateLinks=0, ReadOnly=True)
        workbook.Worksheets(1).ExportAsFixedFormat(0, os.path.abspath(pdf_path))
    finally:
        # Close in order and always: a leaked EXCEL.EXE holds the file open and
        # the next run cannot write it.
        try:
            if workbook is not None:
                workbook.Close(SaveChanges=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:  # noqa: BLE001
            pass
        pythoncom.CoUninitialize()


def render(xlsx_path, png_path, dpi=DEFAULT_DPI):
    """Render the workbook's print area to `png_path`. Returns the path.

    Raises OpsExportError if this machine cannot do it, or Excel failed."""
    if not available():
        raise OpsExportError(
            "the one-page summary picture needs Microsoft Excel on Windows")

    pdf_path = os.path.splitext(png_path)[0] + "_ops.pdf"
    try:
        _export_pdf(xlsx_path, pdf_path)
        if not os.path.isfile(pdf_path):
            raise OpsExportError("Excel produced no PDF — is a print area set?")

        import fitz

        doc = fitz.open(pdf_path)
        try:
            if not doc.page_count:
                raise OpsExportError("Excel produced an empty PDF")
            doc[0].get_pixmap(dpi=dpi).save(png_path)
        finally:
            doc.close()
    except OpsExportError:
        raise
    except Exception as e:  # noqa: BLE001 — COM raises anything
        # Name the file we handed Excel. A COM error quotes whatever file Excel
        # was unhappy about, which is not necessarily this one, and telling them
        # apart is the difference between a bad workbook and a bad template.
        raise OpsExportError(f"{os.path.abspath(xlsx_path)}: {e}") from e
    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
    return png_path
