"""Unit tests for the one-page-summary panel.

The panel restates numbers that already appear elsewhere in the report, so the
risk it carries is not "does it render" but "does it still agree with the rest of
the report a year from now". Most of these tests therefore assert against the
engine's own constants (``SEVERITY``, ``GRADE_COLORS``) rather than against
copies of their values — if someone renames a severity word or repaints a grade,
these fail instead of the panel quietly disagreeing with the tables beside it.
"""

import os

import pytest
from PIL import Image

from well_tools.report import ops_panel
from well_tools.report.pipe_config import SEVERITY
from well_tools.report.tables import GRADE_COLORS

FIELDS = {"well_name": "HRDH_1702_1", "well_type": "ARBD OIL OBSERVATION",
          "log_date": "15-May-2026", "orig_comp": "10-Mar-2004",
          "last_wko": "07-Mar-2012 #1"}

STRINGS = [
    {"Pipe OD": '18 5/8" CSG', "Weight (ppf)": 87.5, "Top (ft)": 5,
     "Bottom (ft)": 117, "Thick_Nom": 0.435},
    {"Pipe OD": '4 1/2" TBG', "Weight (ppf)": 11.6, "Top (ft)": 5,
     "Bottom (ft)": "Didn't Detect", "Thick_Nom": 0.250},
]

SPOTS = [
    {"pipe": {"suffix": '18 5/8" CSG', "type": "CSG"}, "max_loss": "5.1%",
     "grade": "B", "depth": "18.3"},
    {"pipe": {"suffix": '7 5/8" LNR', "type": "LNR"}, "max_loss": "11.2%",
     "grade": "C", "depth": "4027.0"},
    {"pipe": {"suffix": '7" CSG', "type": "CSG"}, "max_loss": "31.2%",
     "grade": "D", "depth": "4180.4"},
]


def data():
    return ops_panel.build_panel_data(FIELDS, STRINGS, SPOTS)


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------
def test_conclusions_read_like_the_report_they_sit_in():
    got = data()["conclusions"]
    assert got[:3] == [
        'Minor metal loss detected across the 18 5/8" casing string.',
        'Moderate metal loss detected across the 7 5/8" liner string.',
        'Intensive metal loss detected across the 7" casing string.',
    ]


def test_conclusion_wording_comes_from_the_shared_severity_map():
    """Not a copy of the words — the same map the {{<role>_highest_grade}} tag
    uses, so the panel and the template can never drift apart."""
    for grade, word in SEVERITY.items():
        [line] = ops_panel.build_panel_data(
            FIELDS, [], [{"pipe": {"suffix": '7" CSG', "type": "CSG"},
                          "grade": grade}])["conclusions"][:1]
        assert line.startswith(word + " metal loss")


def test_the_temperature_note_is_always_last():
    for spots in ([], SPOTS):
        got = ops_panel.build_panel_data(FIELDS, [], spots)["conclusions"]
        assert got[-1] == ops_panel.TEMPERATURE_NOTE


def test_an_unknown_grade_produces_no_conclusion_rather_than_a_broken_one():
    got = ops_panel.build_panel_data(
        FIELDS, [], [{"pipe": {"suffix": '7" CSG', "type": "CSG"}, "grade": None}])
    assert got["conclusions"] == [ops_panel.TEMPERATURE_NOTE]


def test_info_block_order_and_content():
    lines = data()["info_lines"]
    assert lines[0] == ops_panel.RIGLESS_TEXT
    assert lines[1] == "ARBD OIL OBSERVATION."
    assert lines[2] == "•Log Date: 15-May-2026."
    assert lines[3].startswith("•Original Completion Date:")
    assert lines[4].startswith("•Latest Workover Date:")


def test_missing_and_na_dates_are_left_out_not_printed_as_na():
    """A well with no recorded workover gets no workover line. Printing
    "Latest Workover Date: N/A" would read as a finding rather than a blank."""
    fields = dict(FIELDS, last_wko="N/A", orig_comp="")
    lines = ops_panel.build_panel_data(fields, [], [])["info_lines"]
    assert not any("Workover" in line for line in lines)
    assert not any("Original Completion" in line for line in lines)
    assert any("Log Date" in line for line in lines)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def test_nominal_thickness_keeps_its_trailing_zero():
    """0.250, not 0.25 — the third decimal is significant against a measured
    thickness, and Excel hands it over as a bare float."""
    assert ops_panel._thickness(0.250) == "0.250"
    assert ops_panel._thickness(0.435) == "0.435"


def test_whole_numbers_lose_the_decimal_point_and_text_survives():
    assert ops_panel._number(32.0) == "32"
    assert ops_panel._number(2234.5) == "2234.5"
    assert ops_panel._number("Didn't Detect") == "Didn't Detect"


def test_values_are_not_escaped():
    """Cells are drawn onto the page, not written into markup — an "&" has to
    reach the paper as an "&", not as "&amp;"."""
    assert ops_panel._number("AT&T") == "AT&T"
    assert ops_panel._thickness("<n/a>") == "<n/a>"


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def test_grade_fill_comes_from_the_shared_palette():
    for grade in ("A", "B", "C", "D"):
        assert ops_panel._grade_fill(grade) == ops_panel._rgb(GRADE_COLORS[grade])


def test_an_ungraded_row_is_left_unfilled_rather_than_guessed():
    assert ops_panel._grade_fill(None) is None
    assert ops_panel._grade_fill("") is None


def test_columns_fill_the_panel_exactly():
    """Fractions that don't sum to 1 would leave a gap or overrun the border —
    the failure is subtle enough on screen to be worth asserting."""
    assert sum(ops_panel.STRINGS_COLUMNS) == pytest.approx(1.0)
    assert sum(ops_panel.HOTSPOT_COLUMNS) == pytest.approx(1.0)


def test_pipe_interval_header_spans_its_two_columns():
    top, bottom = ops_panel.STRINGS_COLUMNS[2], ops_panel.STRINGS_COLUMNS[3]
    assert top == bottom                       # the two halves are drawn equal
    merged = top + bottom
    assert merged == pytest.approx(0.34)       # the design's proportion


def test_a_line_needs_more_room_than_its_font_size():
    """The height model that makes cell text appear at all: insert_textbox draws
    nothing if the box is even slightly too short, which is silent."""
    assert ops_panel._line_height(1, 8) > 8 * 1.6
    assert ops_panel._line_height(2, 7.5) > ops_panel._line_height(1, 7.5)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def test_renders_a_png_trimmed_to_its_content(tmp_path):
    dest = str(tmp_path / "ops.png")
    result = ops_panel.render_panel(data(), dest)

    assert result["warnings"] == []
    assert os.path.exists(dest)

    with Image.open(dest) as im:
        width, height = im.size
    # Height follows the content, not the default box.
    expected = ops_panel.content_height_pt(data()) / 72 * ops_panel.DEFAULT_DPI
    assert abs(height - expected) < 20
    assert width == pytest.approx(ops_panel.DEFAULT_WIDTH_PT / 72 * ops_panel.DEFAULT_DPI, abs=2)


def test_more_content_makes_a_taller_panel(tmp_path):
    """The panel grows with the well rather than shrinking its type to fit — the
    composition step scales it against the proc image afterwards."""
    short = ops_panel.content_height_pt(ops_panel.build_panel_data(FIELDS, STRINGS[:1], SPOTS[:1]))
    tall = ops_panel.content_height_pt(ops_panel.build_panel_data(FIELDS, STRINGS * 6, SPOTS * 6))
    assert tall > short


def test_a_box_too_small_is_reported_not_silently_cut(tmp_path):
    dest = str(tmp_path / "ops.png")
    result = ops_panel.render_panel(data(), dest, height_pt=60)
    assert any("did not fit" in w for w in result["warnings"])


def test_render_is_deterministic(tmp_path):
    """Two runs, byte-identical — the golden tests depend on it."""
    first = str(tmp_path / "a.png")
    second = str(tmp_path / "b.png")
    ops_panel.render_panel(data(), first)
    ops_panel.render_panel(data(), second)
    assert open(first, "rb").read() == open(second, "rb").read()


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------
def _proc(tmp_path, size=(1240, 1754)):
    """A stand-in for the processed-log image, in a colour nothing else uses so
    a test can tell it apart from the panel pixel by pixel."""
    image = Image.new("RGB", size, (10, 200, 30))
    path = str(tmp_path / "proc.jpg")
    image.save(path, quality=100)
    return path


def test_composition_puts_the_panel_beside_proc(tmp_path):
    dest = str(tmp_path / "ops.png")
    result = ops_panel.compose_ops_image(data(), _proc(tmp_path), dest)

    width, height = result["size"]
    assert height == 1754                       # proc sets the height
    share = (width - 1240) / width
    assert share == pytest.approx(ops_panel.PANEL_SHARE, abs=0.01)
    assert result["warnings"] == []


def test_proc_is_placed_untouched(tmp_path):
    """The log is the evidence in this picture — it is positioned, never
    resampled, so it stays exactly as Warrior drew it."""
    proc_path = _proc(tmp_path)
    dest = str(tmp_path / "ops.png")
    ops_panel.compose_ops_image(data(), proc_path, dest)

    with Image.open(dest) as composite, Image.open(proc_path) as handle:
        proc = handle.convert("RGB")
        left = composite.width - proc.width
        right = composite.crop((left, 0, composite.width, composite.height))
        assert list(right.getdata()) == list(proc.getdata())


def test_the_share_is_adjustable(tmp_path):
    dest = str(tmp_path / "ops.png")
    result = ops_panel.compose_ops_image(data(), _proc(tmp_path), dest, panel_share=0.5)
    width, _ = result["size"]
    assert (width - 1240) / width == pytest.approx(0.5, abs=0.01)


def test_the_panel_scratch_file_is_cleaned_up(tmp_path):
    dest = str(tmp_path / "ops.png")
    ops_panel.compose_ops_image(data(), _proc(tmp_path), dest)
    assert set(os.listdir(tmp_path)) == {"proc.jpg", "ops.png"}


def test_a_short_proc_reports_a_panel_that_cannot_fit(tmp_path):
    """A log image far shorter than the panel's content leaves nowhere to put it,
    and that surfaces as a note rather than a quietly truncated summary."""
    dest = str(tmp_path / "ops.png")
    result = ops_panel.compose_ops_image(data(), _proc(tmp_path, size=(1240, 200)), dest)
    assert any("did not fit" in w for w in result["warnings"])
