"""Comment behaviour of the ghost-collar merge.

An annotated joint (one carrying a Comment) shows its note in place of every
measurement it reports — MaxLoss%, DptMxLos and TMin alike — in both the merged
and un-merged paths. The numbers still drive ranking/aggregation.
"""

import pandas as pd

from webapp.ghost import merge_ghost_by_single_file

THRESH = 2.0

# A + B merge (collar gap 2.0 >= THRESH); C stands alone (gap 0.5 < THRESH).
# B is the chain's worst joint (MaxLoss% 12) and holds the smaller TMin.
BASE = [
    {"Top": 0.0,  "Bottom": 30.0, "TNom": 0.30, "TMin": 0.25, "DptMxLos": 10.0, "MaxLoss%": 5.0},
    {"Top": 32.0, "Bottom": 60.0, "TNom": 0.30, "TMin": 0.20, "DptMxLos": 40.0, "MaxLoss%": 12.0},
    {"Top": 60.5, "Bottom": 90.0, "TNom": 0.30, "TMin": 0.28, "DptMxLos": 70.0, "MaxLoss%": 3.0},
]


def _run(comments=None):
    rows = [dict(r) for r in BASE]
    for i, c in (comments or {}).items():
        rows[i]["Comment"] = c
    return merge_ghost_by_single_file(pd.DataFrame(rows), THRESH)


def test_merged_without_comment_keeps_numbers_and_chain_min_tmin():
    m = _run().iloc[0]
    assert m["Source"].startswith("merged")
    assert m["TMin"] == 0.20        # minimum across the chain, not the best row's
    assert m["DptMxLos"] == 40.0    # from the worst joint
    assert m["MaxLoss%"] == 12.0


def test_merged_comment_overrides_all_three():
    # The chain's worst joint is annotated -> the note replaces every measurement.
    m = _run({0: "", 1: "Completion element", 2: ""}).iloc[0]
    assert m["MaxLoss%"] == "Completion element"
    assert m["DptMxLos"] == "Completion element"
    assert m["TMin"] == "Completion element"   # regression: used to stay numeric (0.20)


def test_unmerged_comment_overrides_all_three():
    c = _run({0: "", 1: "", 2: "Casing shoe"}).iloc[1]
    assert c["Source"] == "original"
    assert c["MaxLoss%"] == "Casing shoe"
    assert c["DptMxLos"] == "Casing shoe"
    assert c["TMin"] == "Casing shoe"


def test_blank_comment_is_ignored():
    m = _run({0: "   ", 1: "   ", 2: ""}).iloc[0]
    assert m["MaxLoss%"] == 12.0
    assert m["TMin"] == 0.20


def test_no_comment_column_at_all():
    # The column is optional — absent Comment must not break the merge.
    out = merge_ghost_by_single_file(pd.DataFrame(BASE), THRESH)
    assert out.iloc[0]["TMin"] == 0.20
    assert out.iloc[0]["MaxLoss%"] == 12.0
