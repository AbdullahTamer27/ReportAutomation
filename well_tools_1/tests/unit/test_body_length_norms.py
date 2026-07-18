"""Joint-length sanity check must judge each taper section on its own norm.

A tapered string (e.g. 4 1/2" x 3 1/2") carries two joint populations — ~38 ft
in the upper half, ~28 ft in the lower. One string-wide median would flag an
entire section as anomalous; each section gets its own median instead.
"""

from well_tools.report.tables import (
    body_length_norms, expected_body_length, review_row,
    BODY_LEN_IDX, NOM_THK_IDX,
)


def _joint(n, body_len, nom_thk, loss=1.0):
    """A 10-column joint row: #, Top, Bottom, Body Length, Nom Thk, …"""
    vals = [n, 0.0, body_len, body_len, nom_thk, 0.2, 10.0, loss, "A", ""]
    assert vals[BODY_LEN_IDX] == body_len and vals[NOM_THK_IDX] == nom_thk
    return vals


def _tapered_string():
    # 4 1/2" half (0.271 wall) ~38 ft; 3 1/2" half (0.254 wall) ~28 ft.
    upper = [_joint(i, 38.0 + (i % 3) * 0.3, 0.271) for i in range(1, 9)]
    lower = [_joint(i, 28.0 + (i % 3) * 0.3, 0.254) for i in range(9, 17)]
    return upper + lower


def test_tapered_string_gets_a_norm_per_section():
    rows = _tapered_string()
    per_section, fallback = body_length_norms(rows)
    assert set(per_section) == {0.271, 0.254}
    assert 37.9 <= per_section[0.271] <= 38.7      # upper half norm
    assert 27.9 <= per_section[0.254] <= 28.7      # lower half norm
    # the string-wide median sits uselessly between the two populations
    assert 28.0 < fallback < 38.0


def test_no_false_flags_across_a_taper():
    rows = _tapered_string()
    norms = body_length_norms(rows)
    msgs = []
    for v in rows:
        review_row("joints", v, msgs.append,
                   typical_len=expected_body_length(v, norms))
    assert [m for m in msgs if "Body Length" in m] == []   # every joint is normal


def test_old_single_median_would_have_flagged_them():
    # Guard the regression: judged against the string-wide median (~33 ft, a value
    # no real joint has), the ENTIRE 38 ft section is flagged — the bug this fixes.
    rows = _tapered_string()
    _, fallback = body_length_norms(rows)
    msgs = []
    for v in rows:
        review_row("joints", v, msgs.append, typical_len=fallback)
    flagged = [m for m in msgs if "Body Length" in m]
    upper = [v for v in rows if v[NOM_THK_IDX] == 0.271]
    assert len(flagged) >= len(upper)                  # at minimum, all of the 38 ft half
    assert all(f"joint {v[0]}:" in " ".join(flagged) for v in upper)


def test_genuinely_odd_joint_still_flagged_within_its_section():
    rows = _tapered_string()
    rows.append(_joint(99, 20.0, 0.254))          # far too short for the 28 ft half
    norms = body_length_norms(rows)
    msgs = []
    for v in rows:
        review_row("joints", v, msgs.append,
                   typical_len=expected_body_length(v, norms))
    flagged = [m for m in msgs if "Body Length" in m]
    assert len(flagged) == 1
    assert "joint 99" in flagged[0] and "0.254 in wall" in flagged[0]


def test_single_size_string_behaves_exactly_as_before():
    rows = [_joint(i, 39.0 + (i % 4) * 0.4, 0.25) for i in range(1, 13)]
    per_section, fallback = body_length_norms(rows)
    assert list(per_section) == [0.25]
    assert per_section[0.25] == fallback          # one section ⇒ identical norm
    for v in rows:
        assert expected_body_length(v, (per_section, fallback)) == fallback


def test_tiny_section_falls_back_to_the_string_median():
    # A 2-joint section can't establish a norm — use the string median instead.
    rows = [_joint(i, 39.0, 0.25) for i in range(1, 11)]
    rows += [_joint(50, 38.5, 0.5), _joint(51, 38.9, 0.5)]
    norms = body_length_norms(rows)
    per_section, fallback = norms
    assert 0.5 not in per_section                 # too few to trust
    assert expected_body_length(rows[-1], norms) == fallback
