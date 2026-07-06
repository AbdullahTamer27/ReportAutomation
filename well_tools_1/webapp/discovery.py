"""Discover a well's report inputs from a single folder.

Given one folder, find the data workbook, the WellSchematic XML, the schematic
PDF, and the IMGS/ image folder — so the UI can offer "open the well folder"
instead of four separate file picks. Pure file-system inspection, no I/O beyond
listing the directory, which keeps it unit-testable without the web app.
"""

import os

# (label, key) for the four things we look for, in report order.
_LABELS = (
    ("Excel data", "excel_path"),
    ("Schematic XML", "xml_path"),
    ("Schematic PDF", "schematic_pdf"),
    ("IMGS folder", "imgs_dir"),
)


def scan_well_folder(folder):
    """Return ``{working_dir, excel_path, xml_path, schematic_pdf, imgs_dir,
    found, missing}`` for `folder`. Missing pieces come back as ``None`` and are
    named in ``missing`` for the user to set manually.

    Selection rules when several files match:
      * data workbook — prefer ``.xlsm``; else an ``.xlsx`` that is NOT the
        generated ``*_RawData.xlsx`` (so the output is never taken for input);
      * schematic PDF — prefer a name hinting at a cross-section plot, else the
        first ``.pdf``;
      * ties break alphabetically (``entries`` is sorted).
    """
    entries = sorted(os.listdir(folder))
    files = [f for f in entries if os.path.isfile(os.path.join(folder, f))]

    def first(pred):
        for f in files:
            if pred(f.lower()):
                return os.path.join(folder, f)
        return None

    result = {
        "working_dir": folder,
        "excel_path": (first(lambda f: f.endswith(".xlsm"))
                       or first(lambda f: f.endswith(".xlsx")
                                and not f.endswith("_rawdata.xlsx"))),
        "xml_path": first(lambda f: f.endswith(".xml")),
        "schematic_pdf": (first(lambda f: f.endswith(".pdf")
                                and any(k in f for k in ("schem", "cross", "section", "plot")))
                          or first(lambda f: f.endswith(".pdf"))),
        "imgs_dir": next(
            (os.path.join(folder, d) for d in entries
             if d.lower() == "imgs" and os.path.isdir(os.path.join(folder, d))),
            None,
        ),
    }

    result["found"] = [label for label, key in _LABELS if result[key]]
    result["missing"] = [label for label, key in _LABELS if not result[key]]
    return result
