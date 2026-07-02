"""Docx comparison helpers for golden tests.

Compares two .docx files part-by-part: XML parts are compared *canonically*
(whitespace- and attribute-order-insensitive) so only meaningful differences
count; everything else is compared by bytes.
"""

import zipfile
from xml.etree import ElementTree as ET


def _canon_xml(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    return ET.canonicalize(ET.tostring(root))


def _parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def diff_docx(a_path, b_path):
    """Return a list of human-readable differences (empty == identical)."""
    a, b = _parts(a_path), _parts(b_path)
    diffs = []
    for name in sorted(set(a) | set(b)):
        if name not in a:
            diffs.append(f"+ only in second: {name}")
            continue
        if name not in b:
            diffs.append(f"- only in first:  {name}")
            continue
        if a[name] == b[name]:
            continue
        if name.endswith(".xml") or name.endswith(".rels"):
            ca, cb = _canon_xml(a[name]), _canon_xml(b[name])
            if ca is not None and ca == cb:
                continue
        diffs.append(f"~ differs: {name} ({len(a[name])} -> {len(b[name])} bytes)")
    return diffs
