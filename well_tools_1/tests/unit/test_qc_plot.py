"""Unit tests for QC-plot preparation.

Two things are pinned here, because both fail silently rather than loudly:

* the **tolerant TIFF reader** — Warrior writes an LZW strip with no EOI code and
  a missing tail, which libtiff (so Pillow) rejects outright. The tests build a
  well-formed LZW TIFF with Pillow, check we decode it identically, then chop the
  end off it and check we still get the right-shaped image back;
* the **structural detection** — the crop must follow the drawn frame, not any
  fixed pixel count, so the same synthetic sheet is rendered at two different
  scales and both must yield the same blocks.
"""

import os
import struct

import numpy as np
import pytest
from PIL import Image

from well_tools.report import qc_plot
from well_tools.report.qc_plot import QcPlotError


# --------------------------------------------------------------------------
# A synthetic log sheet, drawn the way Warrior draws one
# --------------------------------------------------------------------------
def make_sheet(data_height, width=400, legend_height=80, header_height=60,
               footer_legend=True):
    """White sheet: header block, legend block, the log, then a repeat legend.

    Blocks are separated by full-width rules, and the log carries a vertical
    frame down each side — that frame is what detection keys on. Each block's
    reported bounds are its *enclosing rules*, inclusive, since those rules are
    part of the drawn frame and belong in the crop."""
    pad, gap = 10, 3                                  # `gap`: blocks don't touch
    rows = [("legend", legend_height), ("data", data_height)]
    if header_height:
        rows.insert(0, ("header", header_height))
    if footer_legend:
        rows.append(("legend2", legend_height))
    height = pad + sum(h + 2 + gap for _, h in rows) + pad

    sheet = np.full((height, width, 3), 255, dtype=np.uint8)
    blocks = {}
    y = pad
    for name, h in rows:
        sheet[y, pad:width - pad] = 0                 # rule above the block
        if name == "data":
            # The log's own frame: a rule down each side, meeting both rules,
            # plus track separators. The separators matter: they break every row
            # of log data into segments, so no row of the log can pass for a
            # full-width rule — exactly as on a real sheet.
            edges = [pad, pad + (width - 2 * pad) // 3,
                     pad + 2 * (width - 2 * pad) // 3, width - pad - 1]
            for x in edges:
                sheet[y:y + h + 2, x] = 0
            for left_edge, right_edge in zip(edges, edges[1:]):
                sheet[y + 1:y + 1 + h:3, left_edge + 3:right_edge - 3] = 60
        else:
            # Legend content: short runs of "text", never a line across the sheet.
            for row in range(y + 1, y + 1 + h, 7):
                for x in range(pad + 5, width - pad - 5, 60):
                    sheet[row, x:x + 35] = 120
        sheet[y + h + 1, pad:width - pad] = 0         # rule below the block
        blocks[name] = (y, y + h + 1)                 # inclusive, rules included
        y += h + 2 + gap
    return sheet, blocks


def inner(block):
    """A block's content rows — what detection reports, since the rules
    themselves are the separators between blocks, not part of one."""
    top, bottom = block
    return top + 1, bottom - 1


def _tag_value_offset(data, wanted):
    """Byte offset of `wanted`'s inline value field in the first IFD, so a test
    can edit one tag in place without moving anything else in the file."""
    endian = "<" if data[:2] == b"II" else ">"
    ifd = struct.unpack(endian + "I", data[4:8])[0]
    count = struct.unpack(endian + "H", data[ifd:ifd + 2])[0]
    for k in range(count):
        entry = ifd + 2 + k * 12
        tag = struct.unpack(endian + "H", data[entry:entry + 2])[0]
        if tag == wanted:
            return entry + 8, endian
    raise AssertionError(f"tag {wanted} not in the IFD")


def write_tiff(path, arr, **kwargs):
    Image.fromarray(arr).save(path, format="TIFF", **kwargs)
    return str(path)


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def test_lenient_reader_matches_pillow_on_a_valid_lzw_tiff(tmp_path):
    """Our decoder is not a fallback of last resort — on a well-formed file it
    must produce exactly what libtiff produces."""
    arr, _ = make_sheet(300)
    path = write_tiff(tmp_path / "qc.tif", arr, compression="tiff_lzw")

    ours = qc_plot._read_tiff_lenient(path)
    with Image.open(path) as im:
        theirs = np.asarray(im.convert("RGB"))

    assert np.array_equal(ours, theirs)


def test_uncompressed_tiff_reads(tmp_path):
    arr, _ = make_sheet(200)
    path = write_tiff(tmp_path / "qc.tif", arr, compression="raw")
    assert np.array_equal(qc_plot._read_tiff_lenient(path), arr)


def test_truncated_lzw_stream_is_padded_not_rejected(tmp_path):
    """The Warrior case: a structurally valid file whose LZW strip stops
    mid-stream with no EOI. Shortening StripByteCounts in place reproduces it
    exactly — every offset in the file stays valid, the pixel stream just runs
    out early. Pillow refuses it; we return a full-size image with the lost tail
    as white paper."""
    arr, _ = make_sheet(400)
    path = write_tiff(tmp_path / "qc.tif", arr, compression="tiff_lzw")

    data = bytearray(open(path, "rb").read())
    at, endian = _tag_value_offset(bytes(data), 279)          # StripByteCounts
    full = struct.unpack(endian + "I", data[at:at + 4])[0]
    struct.pack_into(endian + "I", data, at, full - 400)      # lose the last 400 bytes

    trunc = tmp_path / "trunc.tif"
    trunc.write_bytes(bytes(data))

    with pytest.raises(Exception):                            # libtiff will not have it
        with Image.open(trunc) as im:
            im.load()

    out = qc_plot._read_tiff_lenient(str(trunc))
    assert out.shape == arr.shape
    # The undamaged head of the image still decodes correctly.
    assert np.array_equal(out[:100], arr[:100])
    # ...and the lost tail is paper, not garbage.
    assert (out[-1] == 255).all()


def test_read_image_falls_back_to_pillow_for_other_formats(tmp_path):
    arr, _ = make_sheet(150)
    path = tmp_path / "qc.png"
    Image.fromarray(arr).save(path)
    assert np.array_equal(qc_plot.read_image(str(path)), arr)


def test_unsupported_tiff_is_refused_rather_than_misread(tmp_path):
    """A palette TIFF must raise, not come back as garbage — read_image then
    hands it to Pillow."""
    arr, _ = make_sheet(120)
    path = tmp_path / "qc.tif"
    Image.fromarray(arr).convert("P").save(path, format="TIFF")

    with pytest.raises(QcPlotError):
        qc_plot._read_tiff_lenient(str(path))
    assert qc_plot.read_image(str(path)).shape == arr.shape


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
def test_detects_the_log_and_the_legend_above_it():
    arr, blocks = make_sheet(600)
    found = qc_plot.detect_blocks(arr)

    assert (found["top"], found["bottom"]) == inner(blocks["data"])
    # The crop starts at the line above the legend. The block's own top border
    # and the header's base sit a few pixels apart and read as one double rule,
    # so either row is right; landing inside the header would not be.
    assert blocks["header"][1] <= found["legend_top"] <= blocks["legend"][0]
    assert found["warnings"] == []


def test_detection_follows_the_sheet_not_a_pixel_count():
    """The same sheet at two vertical scales: the detected log must match each
    one's own block, which is the whole point of not calibrating."""
    for data_height in (300, 1200):
        arr, blocks = make_sheet(data_height)
        found = qc_plot.detect_blocks(arr)
        assert (found["top"], found["bottom"]) == inner(blocks["data"])


def test_footer_legend_is_excluded():
    arr, blocks = make_sheet(500, footer_legend=True)
    found = qc_plot.detect_blocks(arr)
    assert found["bottom"] < blocks["legend2"][0]


def test_missing_legend_is_reported_not_hidden():
    """A sheet whose log is the first thing on it: nothing to crop above, and the
    run says so rather than quietly shipping a legend-less picture."""
    arr, blocks = make_sheet(500, legend_height=0, header_height=0,
                             footer_legend=False)
    found = qc_plot.detect_blocks(arr)
    assert found["legend_top"] == found["top"]
    assert any("legend" in w for w in found["warnings"])


def test_a_tiny_log_area_warns():
    """A log that occupies a sliver of the page is the shape of a bad detection,
    so it gets flagged even though nothing about the scan actually failed."""
    arr, _ = make_sheet(60, legend_height=40, header_height=40)
    sheet = np.full((arr.shape[0] * 4, arr.shape[1], 3), 255, dtype=np.uint8)
    sheet[:arr.shape[0]] = arr

    found = qc_plot.detect_blocks(sheet)
    assert any("quarter" in w for w in found["warnings"])


def test_blank_sheet_raises():
    blank = np.full((200, 200, 3), 255, dtype=np.uint8)
    with pytest.raises(QcPlotError):
        qc_plot.detect_blocks(blank)


# --------------------------------------------------------------------------
# The pipeline pass
# --------------------------------------------------------------------------
def test_prepare_writes_the_cropped_png(tmp_path):
    arr, blocks = make_sheet(700)
    write_tiff(tmp_path / "qc.tif", arr, compression="tiff_lzw")

    notes = []
    out = qc_plot.prepare_qc_image(str(tmp_path), review=notes.append)

    assert out == str(tmp_path / "qc.png")
    with Image.open(out) as im:
        height = im.size[1]
    # Legend + log, starting somewhere on the double rule above the legend.
    log_bottom = inner(blocks["data"])[1]
    assert (log_bottom - blocks["legend"][0] + 1
            <= height
            <= log_bottom - blocks["header"][1] + 1)
    assert notes == []


def test_prepare_can_drop_the_legend(tmp_path):
    arr, blocks = make_sheet(700)
    write_tiff(tmp_path / "qc.tif", arr, compression="tiff_lzw")

    qc_plot.prepare_qc_image(str(tmp_path), include_legend=False)
    log_top, log_bottom = inner(blocks["data"])
    with Image.open(tmp_path / "qc.png") as im:
        assert im.size[1] == log_bottom - log_top + 1


def test_prepare_is_a_no_op_without_a_source(tmp_path):
    """A hand-cropped qc.png with no raw sheet beside it is left alone — that is
    how someone overrides the automatic crop."""
    Image.fromarray(np.full((10, 10, 3), 7, dtype=np.uint8)).save(tmp_path / "qc.png")

    assert qc_plot.find_qc_source(str(tmp_path)) is None
    assert qc_plot.prepare_qc_image(str(tmp_path)) is None
    with Image.open(tmp_path / "qc.png") as im:
        assert im.size == (10, 10)


def test_prepare_reports_a_broken_sheet_instead_of_failing_the_run(tmp_path):
    (tmp_path / "qc.tif").write_bytes(b"not a tiff at all")

    notes = []
    assert qc_plot.prepare_qc_image(str(tmp_path), review=notes.append) is None
    assert notes and "QC plot" in notes[0]
    assert not os.path.exists(tmp_path / "qc.png")


def test_qc_tag_resolves_to_the_cropped_file():
    from well_tools.report.images import TAG_TO_FILE

    assert TAG_TO_FILE["{{qc}}"] == qc_plot.QC_OUTPUT_NAME


# --------------------------------------------------------------------------
# The real thing
# --------------------------------------------------------------------------
_REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "fixtures", "real", "IMGS", "qc.tif")


@pytest.mark.skipif(not os.path.exists(_REAL),
                    reason="local-only fixture: drop a Warrior qc.tif in tests/fixtures/real/IMGS/")
def test_real_warrior_sheet(tmp_path):
    """The synthetic sheets keep the logic honest; this keeps it honest about the
    file it was written for. Every number below was measured off the sample —
    a change to any of them means detection moved."""
    arr = qc_plot.read_image(_REAL)
    assert arr.shape == (4631, 1700, 3)

    found = qc_plot.detect_blocks(arr)
    # The log block: from the rule under the legend down to the last row before
    # the footer legend's own rule at 4225 — which is what keeps that second
    # legend out of the picture.
    assert (found["top"], found["bottom"]) == (805, 4224)
    assert (found["left"], found["right"]) == (24, 1679)
    assert found["legend_top"] == 397                          # the track legend
    assert found["warnings"] == []

    result = qc_plot.crop_plot(_REAL, str(tmp_path / "qc.png"))
    with Image.open(result["path"]) as im:
        assert im.size == (1656, 3828)


_REAL_BORDER = os.path.join(os.path.dirname(_REAL), "qc_continuous_border.tif")


@pytest.mark.skipif(not os.path.exists(_REAL_BORDER), reason="local-only fixture")
def test_continuous_border_sheet_stops_before_the_repeated_footer_legend():
    """The sheet that broke v0.2.4. Its page border runs unbroken from the header
    to the foot, so following the tallest vertical line — what v0.2.4 did — ran
    straight through the footer legend and into the picture, with every sanity
    check still passing. Blocks can't be bridged that way: the footer legend is a
    block of its own.

    Both halves are asserted, because the fix is only meaningful against the
    failure: the old signal must still be shown to span too far here."""
    arr = qc_plot.read_image(_REAL_BORDER)
    ink = arr.mean(axis=2) < 128

    found = qc_plot.detect_blocks(arr)
    footer_rule = next(b[0] for b in qc_plot._rule_rows(ink) if b[0] > found["bottom"])

    # The old signal really does overshoot on this sheet...
    _, old_bottom = qc_plot._tallest_vertical_rule(ink)
    assert old_bottom > footer_rule
    # ...and the block model stops short of the footer legend's own rule.
    assert found["bottom"] < footer_rule
    assert (found["top"], found["bottom"]) == (851, 3066)
    assert found["legend_top"] == 397
    assert found["warnings"] == []
