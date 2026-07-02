"""Unit tests for the damage-count logic (interval assignment, worst-per-pipe,
and depth-window clustering) — the pieces that decide how many damage pictures a
report gets, tested without XML/Excel."""

import pytest

from well_tools.report import damage_select as ds


# ---- _interval_of -----------------------------------------------------------
@pytest.mark.parametrize("depth,expected", [
    (50, 0), (100, 0), (0, 0),          # inside / on the edges of the first zone
    (250, 1), (200, 1), (300, 1),       # inside / edges of the second
    (150, None), (-5, None), (500, None),  # in gaps or outside everything
])
def test_interval_of(depth, expected):
    intervals = [(0, 100), (200, 300)]
    assert ds._interval_of(depth, intervals) == expected


# ---- _worst_per_interval_pipe ----------------------------------------------
def _dmg(role, depth, grade, loss):
    return {"role": role, "depth": depth, "grade": grade, "loss": loss}


def test_worst_prefers_D_over_C_even_at_lower_loss():
    intervals = [(0, 1000)]
    damages = [_dmg("firstPipe", 100, "C", 90.0),   # moderate, high loss
               _dmg("firstPipe", 200, "D", 20.0)]   # intensive, low loss
    reps, skipped = ds._worst_per_interval_pipe(damages, intervals)
    assert skipped == 0
    assert len(reps) == 1
    assert reps[0]["grade"] == "D" and reps[0]["depth"] == 200


def test_worst_same_grade_prefers_higher_loss():
    intervals = [(0, 1000)]
    damages = [_dmg("firstPipe", 100, "C", 30.0),
               _dmg("firstPipe", 200, "C", 55.0)]
    reps, _ = ds._worst_per_interval_pipe(damages, intervals)
    assert len(reps) == 1 and reps[0]["loss"] == 55.0


def test_worst_keeps_one_per_pipe_and_counts_out_of_range():
    intervals = [(0, 1000)]
    damages = [_dmg("firstPipe", 100, "D", 40.0),
               _dmg("secondPipe", 120, "C", 60.0),
               _dmg("firstPipe", 5000, "D", 80.0)]   # depth outside every interval
    reps, skipped = ds._worst_per_interval_pipe(damages, intervals)
    assert skipped == 1
    assert {r["role"] for r in reps} == {"firstPipe", "secondPipe"}


# ---- _cluster_by_window -----------------------------------------------------
def _rep(role, depth, interval=0):
    return {"role": role, "depth": depth, "interval": interval}


def test_four_pipes_same_interval_same_depth_is_one_picture():
    """One damage per pipe, all in the same interval within the window → a single
    picture holding all four points."""
    reps = [_rep("firstPipe", 10184.5), _rep("secondPipe", 10185.0),
            _rep("thirdPipe", 10186.0), _rep("fourthPipe", 10187.0)]
    pics = ds._cluster_by_window(reps, depth_window=200)
    assert len(pics) == 1
    assert len(pics[0]) == 4


def test_window_splits_when_beyond_window_from_start():
    """Anchored to the cluster START: a point >window ft from the first opens a
    new picture."""
    reps = [_rep("firstPipe", 1000.0), _rep("secondPipe", 1150.0),   # within 200 of start
            _rep("thirdPipe", 1400.0)]                               # 400 from start → new
    pics = ds._cluster_by_window(reps, depth_window=200)
    assert [len(c) for c in pics] == [2, 1]


def test_separate_intervals_never_share_a_picture():
    reps = [_rep("firstPipe", 500.0, interval=0),
            _rep("secondPipe", 520.0, interval=1)]   # near in depth, different interval
    pics = ds._cluster_by_window(reps, depth_window=200)
    assert len(pics) == 2


def test_pictures_sorted_shallowest_first():
    reps = [_rep("a", 3000.0, interval=1), _rep("b", 500.0, interval=0)]
    pics = ds._cluster_by_window(reps, depth_window=200)
    assert pics[0][0]["depth"] == 500.0 and pics[1][0]["depth"] == 3000.0
