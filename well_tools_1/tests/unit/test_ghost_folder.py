"""Unit tests for the batch (whole-folder) Ghost Merger."""

import os
import pytest

from webapp.ghost import merge_ghost_folder, GhostInputError

_VALID = (
    "SmartLog banner line one\n"
    "banner line two\n"
    "Top,Bottom,TNom,TMin,DptMxLos,MaxLoss%\n"
    "0,30,0.400,0.350,15,12\n"
    "33,60,0.400,0.360,45,8\n"      # collar gap 3.0 => merges at threshold 3
)
_INVALID = "banner\nbanner\nFoo,Bar\n1,2\n"   # missing required columns


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w") as f:
        f.write(text)


def test_batch_processes_all_csvs(tmp_path):
    d = str(tmp_path)
    _write(d, "well_a.csv", _VALID)
    _write(d, "well_b.csv", _VALID)
    _write(d, "broken.csv", _INVALID)
    _write(d, "notes.txt", "ignored")   # non-csv is skipped

    res = merge_ghost_folder(d, 3.0)
    assert res["succeeded"] == 2
    assert res["failed"] == 1
    by_file = {r["file"]: r for r in res["results"]}
    assert set(by_file) == {"well_a.csv", "well_b.csv", "broken.csv"}   # .txt ignored
    assert by_file["well_a.csv"]["ok"] and os.path.isfile(by_file["well_a.csv"]["output_path"])
    assert by_file["broken.csv"]["ok"] is False and by_file["broken.csv"]["error"]
    # each good CSV got a merged_*.xlsx beside it
    assert os.path.isfile(os.path.join(d, "merged_well_a.xlsx"))


def test_no_csvs_raises(tmp_path):
    _write(str(tmp_path), "a.txt", "x")
    with pytest.raises(GhostInputError, match="No .csv"):
        merge_ghost_folder(str(tmp_path), 3.0)


def test_missing_folder_and_bad_length(tmp_path):
    with pytest.raises(GhostInputError, match="Folder not found"):
        merge_ghost_folder(str(tmp_path / "nope"), 3.0)
    _write(str(tmp_path), "a.csv", _VALID)
    with pytest.raises(GhostInputError, match="greater than 0"):
        merge_ghost_folder(str(tmp_path), 0)
