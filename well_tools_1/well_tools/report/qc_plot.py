"""QC-plot preparation — read a Warrior log plot and crop it to the log itself.

The QC picture handed to us is a full logging sheet exported by Warrior: a
title/logo block, a metadata block, the track legend, the log, and then the
legend printed a second time at the foot of the sheet. The report wants the
middle of that — the legend and the log — with the branding and the duplicate
footer legend gone.

Two things make this harder than "crop a fixed rectangle":

1. **Warrior's TIFFs do not decode.** It writes an LZW strip that never emits the
   EOI terminator (and truncates the final row), so libtiff — and therefore
   Pillow, `sips` and Preview — refuse the file outright with
   ``decoder error -2``. We keep a tolerant reader here: Pillow is tried first
   (it handles every well-formed image), and only when it fails do we decode the
   strips ourselves and pad whatever tail is missing with white.

2. **Nothing about the geometry is fixed.** The plot's vertical scale, the well's
   depth and the number of tracks all change between reports, so the log occupies
   a different rectangle every time. We never count pixels: the log is found as
   the tallest continuous vertical rule on the sheet (its own frame), and the
   legend as the block sitting between the last two full-width rules above it.

Detection cannot verify itself, so `detect_blocks` returns the checks it could
not satisfy in ``warnings``; the caller surfaces them as report notes and the
picture still gets placed. Being told at generation time that the crop looks
wrong is the whole point — the alternative is finding out from the client.
"""

import os
import struct

import numpy as np

# The sheet is white paper: "ink" is anything clearly darker than the page, and
# "not blank" is anything at all off-white (faint grid lines, pale curve tints).
_INK = 128
_BLANK = 245
# A row is a rule if an unbroken ink line covers this much of it. Rules span the
# sheet; the densest log data (solid colour tracks) is split by track borders.
_RULE_COVERAGE = 0.6
# Double rules are drawn as two lines a few pixels apart — merge them.
_RULE_GAP = 8

# The tag is an ordinary image tag ({{qc}} -> qc.png), so placement, sizing and
# the border all come from the existing image pass. This module only has to turn
# the raw sheet into the picture that tag expects.
QC_SOURCE_STEM = "qc"
QC_SOURCE_EXTS = (".tif", ".tiff")
QC_OUTPUT_NAME = "qc.png"


class QcPlotError(Exception):
    """The QC plot could not be read or made sense of."""


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def _lzw_decode(data):
    """TIFF LZW (variable 9–12 bit codes, early change). Returns what it could
    decode: a stream that ends without an EOI code is not an error here, it is
    the case we exist to handle."""
    out = bytearray()
    CLEAR, EOI = 256, 257

    def reset():
        return {i: bytes([i]) for i in range(256)}, 258, 9

    table, next_code, width = reset()
    prev = None
    acc = accbits = i = 0
    n = len(data)

    while True:
        while accbits < width:
            if i >= n:
                return bytes(out)          # truncated stream — keep what we have
            acc = (acc << 8) | data[i]
            i += 1
            accbits += 8
        code = (acc >> (accbits - width)) & ((1 << width) - 1)
        accbits -= width
        acc &= (1 << accbits) - 1

        if code == EOI:
            return bytes(out)
        if code == CLEAR:
            table, next_code, width = reset()
            prev = None
            continue

        if prev is None:
            entry = table[code]
        else:
            if code in table:
                entry = table[code]
            elif code == next_code:
                entry = prev + prev[:1]
            else:
                raise QcPlotError(f"corrupt LZW stream (bad code {code})")
            table[next_code] = prev + entry[:1]
            next_code += 1
            # "Early change": widen one code before the width is exhausted.
            if next_code + 1 >= (1 << width) and width < 12:
                width += 1

        out += entry
        prev = entry


_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _read_ifd(data):
    """Tag → list of values for the file's first IFD."""
    if data[:2] not in (b"II", b"MM"):
        raise QcPlotError("not a TIFF file")
    endian = "<" if data[:2] == b"II" else ">"
    magic, offset = struct.unpack(endian + "HI", data[2:8])
    if magic != 42:
        raise QcPlotError("not a TIFF file")

    count = struct.unpack(endian + "H", data[offset:offset + 2])[0]
    tags = {}
    for k in range(count):
        entry = offset + 2 + k * 12
        tag, typ, n = struct.unpack(endian + "HHI", data[entry:entry + 8])
        size = _TYPE_SIZE.get(typ, 1) * n
        if size <= 4:
            raw = data[entry + 8:entry + 8 + size]
        else:
            at = struct.unpack(endian + "I", data[entry + 8:entry + 12])[0]
            raw = data[at:at + size]
        if typ == 3:
            tags[tag] = list(struct.unpack(endian + f"{n}H", raw[:2 * n]))
        elif typ == 4:
            tags[tag] = list(struct.unpack(endian + f"{n}I", raw[:4 * n]))
        else:
            tags[tag] = [raw]
    return tags


def _read_tiff_lenient(path):
    """Decode a TIFF Pillow refused. Supports the shape Warrior writes: 8-bit,
    contiguous samples, uncompressed or LZW. Missing tail rows come back white."""
    with open(path, "rb") as f:
        data = f.read()
    t = _read_ifd(data)

    def one(tag, default=None):
        v = t.get(tag)
        return v[0] if v else default

    width, height = one(256), one(257)
    if not width or not height:
        raise QcPlotError("TIFF has no image dimensions")
    bits = t.get(258, [8])
    samples = one(277, 1)
    if any(b != 8 for b in bits):
        raise QcPlotError(f"unsupported TIFF bit depth {bits} (only 8-bit)")
    if one(284, 1) != 1:
        raise QcPlotError("unsupported TIFF planar configuration (only contiguous)")

    photometric = one(262, 1)
    if photometric not in (0, 1, 2):
        # Palette / YCbCr / separated: rare, and misreading one silently would be
        # worse than handing it to Pillow.
        raise QcPlotError(f"unsupported TIFF photometric interpretation {photometric}")

    compression = one(259, 1)
    offsets, counts = t.get(273, []), t.get(279, [])
    if not offsets or len(offsets) != len(counts):
        raise QcPlotError("TIFF strip table is missing or inconsistent")

    raw = bytearray()
    for off, cnt in zip(offsets, counts):
        strip = data[off:off + cnt]
        if compression == 1:
            raw += strip
        elif compression == 5:
            raw += _lzw_decode(strip)
        else:
            raise QcPlotError(f"unsupported TIFF compression {compression}")

    expected = width * height * samples
    if len(raw) < expected:
        raw += b"\xff" * (expected - len(raw))    # pad the lost tail with paper
    arr = np.frombuffer(bytes(raw[:expected]), dtype=np.uint8).reshape(height, width, samples)

    if one(317, 1) == 2:                          # horizontal differencing
        arr = np.cumsum(arr, axis=1, dtype=np.uint8)
    if photometric == 0:                          # 0 = white is zero
        arr = 255 - arr
    if samples == 1:
        arr = np.repeat(arr, 3, axis=2)
    return np.ascontiguousarray(arr[:, :, :3])


def read_image(path):
    """The plot as an ``(H, W, 3)`` uint8 array.

    TIFFs go to our own decoder first — the ones we are handed are the ones
    libtiff rejects, and letting it fail first only buys a scary
    ``LZWDecode: ... not terminated`` on stderr. Anything our decoder does not
    positively understand it refuses, and Pillow (which handles every
    well-formed image, TIFF or not) takes over."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None                  # log sheets are legitimately huge
    if path.lower().endswith(QC_SOURCE_EXTS):
        try:
            return _read_tiff_lenient(path)
        except QcPlotError:
            pass                                   # an unusual TIFF — Pillow's turn
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------
def _tallest_vertical_rule(ink):
    """``(top, bottom)`` of the tallest continuous run of ink in any column.

    The fallback for a sheet drawn without full-width rules, where the frame down
    the side of the data area is the only structure to go on. Columns within 2%
    of the winner vote on the edges so a single ragged column of solid colour
    cannot shift the answer. Not the primary signal: on a sheet whose page border
    is unbroken, the tallest run is the border itself, and it spans everything."""
    height, width = ink.shape
    run = np.zeros(width, dtype=np.int32)
    best = np.zeros(width, dtype=np.int32)
    best_end = np.zeros(width, dtype=np.int32)
    for row in range(height):
        run = np.where(ink[row], run + 1, 0)
        better = run > best
        best = np.where(better, run, best)
        best_end = np.where(better, row, best_end)

    longest = int(best.max())
    if longest == 0:
        raise QcPlotError("no vertical rule found — is this a log plot?")
    agree = best >= longest * 0.98
    bottom = int(np.median(best_end[agree]))
    top = int(np.median((best_end - best + 1)[agree]))
    return top, bottom


def _rule_rows(ink, limit=None):
    """Full-width horizontal rules (above `limit`, if given), as merged
    ``(start, end)`` bands so a double-line border counts once.

    A rule has to be one *continuous* line across the sheet — a row of tightly
    packed legend text can easily be 60% ink, but it is 60% ink in short bursts."""
    band = ink[:limit] if limit is not None else ink
    if not band.size:
        return []
    run = np.zeros(band.shape[0], dtype=np.int32)
    longest = np.zeros(band.shape[0], dtype=np.int32)
    for column in range(band.shape[1]):
        run = np.where(band[:, column], run + 1, 0)
        longest = np.maximum(longest, run)

    rows = np.where(longest > band.shape[1] * _RULE_COVERAGE)[0]
    bands = []
    for r in rows:
        if bands and r - bands[-1][1] <= _RULE_GAP:
            bands[-1][1] = int(r)
        else:
            bands.append([int(r), int(r)])
    return [tuple(b) for b in bands]


def _trim_blank(marked, top, bottom):
    """Shrink ``(top, bottom)`` past any blank rows at either end."""
    used = np.where(marked[top:bottom + 1].any(axis=1))[0]
    if not len(used):
        return top, bottom
    return top + int(used.min()), top + int(used.max())


def detect_blocks(arr):
    """Locate the log and the legend above it.

    Returns ``{top, bottom, left, right, legend_top, warnings}`` — all row/column
    indices into `arr`, inclusive. `top`/`bottom` bound the log; `legend_top` is
    where the track legend starts (equal to `top` when no legend was found).

    The sheet is read as a stack of blocks separated by full-width rules, and the
    log is the tallest of them. Keying on the horizontal rules rather than the
    log's side frame matters: on sheets whose page border runs unbroken from the
    header to the foot, the side frame is one continuous line down the whole
    page, and following it swallows the legend Warrior repeats at the bottom.
    Blocks can't do that — the footer legend is a block of its own."""
    height, width, _ = arr.shape
    grey = arr.mean(axis=2)
    ink = grey < _INK
    marked = grey < _BLANK

    bands = _rule_rows(ink)
    # Blocks are the gaps between consecutive rules; the log is the tallest.
    blocks = [(bands[i][1] + 1, bands[i + 1][0] - 1, i)
              for i in range(len(bands) - 1)
              if bands[i + 1][0] - 1 > bands[i][1] + 1]

    legend_top = None
    if blocks:
        top, bottom, above = max(blocks, key=lambda b: b[1] - b[0])
        top, bottom = _trim_blank(marked, top, bottom)
        # The legend is the block directly above the log, so the crop starts at
        # that block's own top rule.
        if above >= 1:
            legend_top = bands[above - 1][0]
    else:
        # A sheet drawn without rules: fall back to the log's side frame.
        top, bottom = _tallest_vertical_rule(ink)

    # Horizontal extent: everything that is not blank paper beside the log.
    columns = np.where(marked[top:bottom + 1].any(axis=0))[0]
    if not len(columns):
        raise QcPlotError("the detected log area is blank")
    left, right = int(columns.min()), int(columns.max())

    if legend_top is None:
        legend_top = top

    warnings = []
    if (bottom - top + 1) < height * 0.25:
        warnings.append("the log area came out under a quarter of the sheet")
    if (right - left + 1) < width * 0.4:
        warnings.append("the log area came out narrower than half the sheet")
    if legend_top == top:
        warnings.append("no track legend was found above the log")

    return {"top": top, "bottom": bottom, "left": left, "right": right,
            "legend_top": legend_top, "warnings": warnings}


# --------------------------------------------------------------------------
# Cropping
# --------------------------------------------------------------------------
def crop_plot(src_path, dest_path, include_legend=True):
    """Crop `src_path` to the log (with the legend above it by default) and write
    `dest_path` as a PNG. Returns ``{path, box, warnings}``, where `box` is
    ``(left, top, right, bottom)``."""
    arr = read_image(src_path)
    blocks = detect_blocks(arr)

    top = blocks["legend_top"] if include_legend else blocks["top"]
    box = (blocks["left"], top, blocks["right"], blocks["bottom"])
    cropped = arr[top:blocks["bottom"] + 1, blocks["left"]:blocks["right"] + 1]

    from PIL import Image

    Image.fromarray(cropped).save(dest_path)
    return {"path": dest_path, "box": box, "warnings": blocks["warnings"]}


# --------------------------------------------------------------------------
# Pipeline hook
# --------------------------------------------------------------------------
def find_qc_source(img_folder):
    """The raw QC sheet in `img_folder` (``qc.tif``/``qc.tiff``), or None."""
    try:
        entries = os.listdir(img_folder)
    except OSError:
        return None
    for name in sorted(entries):
        stem, ext = os.path.splitext(name)
        if stem.lower() == QC_SOURCE_STEM and ext.lower() in QC_SOURCE_EXTS:
            return os.path.join(img_folder, name)
    return None


def prepare_qc_image(img_folder, progress=None, review=None, include_legend=True):
    """Crop the raw QC sheet into ``qc.png`` beside it, for the image pass to
    place. Returns the written path, or None when there is nothing to do.

    A hand-cropped ``qc.png`` with no raw sheet beside it is left untouched, so
    overriding the automatic crop is just a matter of deleting the source."""
    log = progress or (lambda m: None)
    rev = review or (lambda m: None)

    src = find_qc_source(img_folder)
    if not src:
        return None

    dest = os.path.join(img_folder, QC_OUTPUT_NAME)
    try:
        result = crop_plot(src, dest, include_legend=include_legend)
    except QcPlotError as e:
        rev(f"❌ QC plot: not cropped — {e}")
        return None
    except Exception as e:                       # noqa: BLE001 — never fail a run for this
        rev(f"❌ QC plot: not cropped — {os.path.basename(src)}: {e}")
        return None

    left, top, right, bottom = result["box"]
    log(f"OK cropped {os.path.basename(src)} -> {QC_OUTPUT_NAME} "
        f"[{left},{top} - {right},{bottom}]")
    for w in result["warnings"]:
        rev(f"⚠️ QC plot: {w} — check the picture in the report")
    return result["path"]
