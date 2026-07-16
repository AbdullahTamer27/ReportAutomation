"""Ghost Collar Merger service.

Ported from the standalone GHOST_APP desktop tool (ghostMerge.py) — the tkinter
GUI is dropped and the core merge logic is exposed as a callable for the web API.
It reads a SmartLog Joint-Analysis CSV, merges consecutive joints separated by a
"ghost collar" gap (>= the chosen length), keeps the worst joint's metal-loss per
chain, and writes a cleaned .xlsx with a Source column (original vs. merged).

The merge algorithm is unchanged from the original so results match the desktop
tool exactly.
"""

import os
import logging

import pandas as pd

logger = logging.getLogger("webapp.ghost")

# Columns the merge needs from the CSV (after the 2 banner rows are skipped and
# the header row is stripped). 'Comment' is optional.
REQUIRED_COLUMNS = ("Top", "Bottom", "TNom", "TMin", "DptMxLos", "MaxLoss%")
OUTPUT_COLUMNS = ["Top", "Bottom", "Length", "TNom", "TMin", "DptMxLos", "MaxLoss%", "Source"]


class GhostInputError(Exception):
    """Raised when the CSV input or threshold is missing or invalid."""


def _get_max_loss(row):
    """Display value for MaxLoss%: the Comment text if present, else the number.
    (Ranking always uses the numeric MaxLoss%; this only affects what is shown.)"""
    comment = row.get("Comment", None)
    if comment is not None and str(comment).strip() not in ("", "nan", "None", "NaN"):
        return comment
    return row["MaxLoss%"]


def merge_ghost_by_single_file(df, ghost_collar_length):
    """Merge consecutive joints whose collar gap is >= ghost_collar_length.

    Unchanged from the original GHOST_APP logic. Returns a DataFrame with the
    OUTPUT_COLUMNS layout. Also returns nothing about chains — see merge_ghost_collars."""
    merged_rows = []
    i = 0
    while i < len(df):
        current = df.iloc[i]

        j = i
        merged = False
        while j < len(df) - 1:
            next_row = df.iloc[j + 1]
            collar_len = round(next_row["Top"] - df.iloc[j]["Bottom"], 2)

            if collar_len >= ghost_collar_length:
                j += 1
                merged = True
            else:
                break

        if merged:
            merge_group = df.iloc[i:j + 1]
            best_row = merge_group.loc[merge_group["MaxLoss%"].idxmax()]
            max_loss_val = _get_max_loss(best_row)

            merged_rows.append({
                "Top": merge_group.iloc[0]["Top"],
                "Bottom": merge_group.iloc[-1]["Bottom"],
                "Length": merge_group.iloc[-1]["Bottom"] - merge_group.iloc[0]["Top"],
                "TNom": merge_group.iloc[0]["TNom"],
                "TMin": merge_group["TMin"].min(),
                "DptMxLos": best_row["DptMxLos"],
                "MaxLoss%": max_loss_val,
                "Source": "merged (ghost collar chain)",
            })
            i = j + 1
        else:
            max_loss_val = _get_max_loss(current)
            merged_rows.append({
                "Top": current["Top"],
                "Bottom": current["Bottom"],
                "Length": current["Bottom"] - current["Top"],
                "TNom": current["TNom"],
                "TMin": current["TMin"],
                "DptMxLos": current["DptMxLos"],
                "MaxLoss%": max_loss_val,
                "Source": "original",
            })
            i += 1

    return pd.DataFrame(merged_rows)[OUTPUT_COLUMNS]


def _load_csv(csv_path):
    """Read the CSV the way the desktop tool did: skip the 2 banner rows, strip
    column names, sort by Top. Raises GhostInputError on bad input."""
    try:
        df = pd.read_csv(csv_path, skiprows=2)
    except Exception as e:  # noqa: BLE001
        raise GhostInputError(f"Could not read the CSV: {e}") from e

    df.columns = df.columns.str.strip()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise GhostInputError(
            "CSV is missing required column(s): " + ", ".join(missing)
            + ". Expected a SmartLog Joint-Analysis export."
        )
    if df.empty:
        raise GhostInputError("CSV has no joint rows after the 2 header lines.")

    df = df.sort_values(by="Top").reset_index(drop=True)
    return df


def merge_ghost_folder(folder, ghost_collar_length):
    """Run the ghost-collar merge on every Joint-Analysis ``.csv`` in `folder`,
    writing a ``merged_*.xlsx`` beside each. One bad CSV is captured and never
    aborts the batch. Returns a summary dict with a per-file ``results`` list.
    Raises :class:`GhostInputError` for a missing folder or when it holds no CSVs."""
    if not folder or not os.path.isdir(folder):
        raise GhostInputError("Folder not found at that path.")
    try:
        ghost_collar_length = float(ghost_collar_length)
    except (TypeError, ValueError):
        raise GhostInputError("Ghost collar length must be a number.")
    if ghost_collar_length <= 0:
        raise GhostInputError("Ghost collar length must be greater than 0.")
    try:
        names = sorted(os.listdir(folder))
    except OSError as e:
        raise GhostInputError(f"Cannot read the folder: {e}") from e

    csvs = [n for n in names
            if n.lower().endswith(".csv") and os.path.isfile(os.path.join(folder, n))]
    if not csvs:
        raise GhostInputError("No .csv files found in that folder.")

    results = []
    for name in csvs:
        path = os.path.join(folder, name)
        try:
            r = merge_ghost_collars(path, ghost_collar_length)
            results.append({"file": name, "ok": True, "output_path": r["output_path"],
                            "input_rows": r["input_rows"], "output_rows": r["output_rows"],
                            "merged_chains": r["merged_chains"], "error": None})
        except Exception as e:  # noqa: BLE001 — capture per file, keep going
            results.append({"file": name, "ok": False, "output_path": None,
                            "input_rows": None, "output_rows": None,
                            "merged_chains": None, "error": str(e)})

    succeeded = sum(1 for r in results if r["ok"])
    logger.info("Ghost folder merge: %s/%s ok in %s", succeeded, len(results), folder)
    return {"folder": folder, "threshold": ghost_collar_length,
            "succeeded": succeeded, "failed": len(results) - succeeded, "results": results}


def _default_output_path(csv_path):
    base = os.path.basename(csv_path)
    stem = base[:-4] if base.lower().endswith(".csv") else base
    return os.path.join(os.path.dirname(csv_path), f"merged_{stem}.xlsx")


def _preview_text(merged, input_rows, threshold):
    """Short text summary of the result for the UI."""
    chains = int((merged["Source"] != "original").sum())
    lines = [
        f"Threshold: collars >= {threshold} ft are merged",
        f"Input joints:  {input_rows}",
        f"Output rows:   {len(merged)}   (merged chains: {chains})",
        "",
        merged.head(15).to_string(index=False),
    ]
    if len(merged) > 15:
        lines.append(f"… and {len(merged) - 15} more row(s).")
    return "\n".join(lines)


def merge_ghost_collars(csv_path, ghost_collar_length, output_path=None):
    """Merge ghost-collar chains in `csv_path` and write a cleaned .xlsx.

    Returns a summary dict. Raises GhostInputError for bad inputs; lets unexpected
    errors propagate (the API maps them to 500)."""
    if not csv_path or not os.path.isfile(csv_path):
        raise GhostInputError("CSV file not found. Please choose a .csv file.")
    if not csv_path.lower().endswith(".csv"):
        raise GhostInputError("Input must be a .csv file.")
    try:
        threshold = float(ghost_collar_length)
    except (TypeError, ValueError) as e:
        raise GhostInputError("Ghost collar length must be a number.") from e
    if threshold <= 0:
        raise GhostInputError("Ghost collar length must be greater than 0.")

    df = _load_csv(csv_path)
    input_rows = len(df)
    merged = merge_ghost_by_single_file(df, ghost_collar_length=threshold)

    out_path = output_path or _default_output_path(csv_path)
    try:
        merged.to_excel(out_path, index=False)
    except PermissionError as e:
        raise GhostInputError(
            "Can't write the output — it may be open in Excel. Close it and retry."
        ) from e

    chains = int((merged["Source"] != "original").sum())
    logger.info("Ghost merge: %s rows -> %s rows (%s chains) -> %s",
                input_rows, len(merged), chains, out_path)
    return {
        "csv_path": csv_path,
        "output_path": out_path,
        "threshold": threshold,
        "input_rows": input_rows,
        "output_rows": len(merged),
        "merged_chains": chains,
        "preview": _preview_text(merged, input_rows, threshold),
    }
