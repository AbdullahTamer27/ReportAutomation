"""Golden-file harness for the report pipeline.

Used to prove that a refactor (e.g. "open the .docx once, save once") produces a
byte/behaviour-identical report. It runs one full generation and can either
SAVE the result as a baseline or COMPARE a fresh result against that baseline.

Comparison unzips both .docx files and diffs every part. XML parts are compared
canonically (whitespace-insensitive, attribute-order-insensitive) so that only
*meaningful* differences are reported; media/binary parts are compared by bytes.

Usage
-----
Capture a baseline on the CURRENT code:

    python tools/golden_report.py baseline \
        --template webapp/data/templates/sample_6_4p5-7-9-13-18.docx \
        --excel   /path/to/data.xlsm \
        --workdir /path/to/workdir \
        --config  "4.5-7-9-13-18" \
        --xml     /path/to/WellSchematic.xml \
        --out     tools/_golden/baseline.docx

Then, after the refactor, compare:

    python tools/golden_report.py compare  ...same args...  \
        --out tools/_golden/candidate.docx --baseline tools/_golden/baseline.docx

Exit code 0 = identical, 1 = differences (printed).
"""

import argparse
import os
import sys
import zipfile
from xml.etree import ElementTree as ET


def _generate(args, out_path):
    """Run one full report generation with the given inputs -> out_path."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from well_tools.report.report_builder import build_automation_report
    from well_tools.report import _wbcache

    pipe_model = None
    damage_clusters = None
    if args.config:
        from well_tools.report.pipe_config import build_pipe_model
        pm = build_pipe_model(args.config, args.excel, xml_path=args.xml)
        pipe_model = pm["pipes"]
        if args.xml:
            from well_tools.report.damage_select import compute_damage_pictures
            damage_clusters = compute_damage_pictures(args.xml, args.excel, pipe_model)["pictures"]

    _wbcache.clear()
    build_automation_report(
        word_template_path=args.template,
        excel_data_path=args.excel,
        working_dir=args.workdir,
        output_path=out_path,
        damage_count=args.damage_count,
        pipe_model=pipe_model,
        wellhead_damage=args.wellhead_damage,
        damage_clusters=damage_clusters,
    )
    return out_path


def _canon_xml(data):
    """Canonical string for an XML part: parse and re-serialize (sorts nothing
    Word cares about, but normalizes insignificant whitespace/formatting)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None  # not XML we can canonicalize; fall back to byte compare
    # Canonical C14N gives attribute-order-insensitive, ns-normalized output.
    return ET.canonicalize(ET.tostring(root))


def _parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _compare(baseline, candidate):
    a, b = _parts(baseline), _parts(candidate)
    diffs = []
    for name in sorted(set(a) | set(b)):
        if name not in a:
            diffs.append(f"+ only in candidate: {name}")
            continue
        if name not in b:
            diffs.append(f"- only in baseline:  {name}")
            continue
        if a[name] == b[name]:
            continue
        if name.endswith(".xml") or name.endswith(".rels"):
            ca, cb = _canon_xml(a[name]), _canon_xml(b[name])
            if ca is not None and ca == cb:
                continue  # only cosmetic XML differences
        diffs.append(f"~ differs: {name}  ({len(a[name])} -> {len(b[name])} bytes)")
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["baseline", "compare"])
    ap.add_argument("--template", required=True)
    ap.add_argument("--excel", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--xml", default=None)
    ap.add_argument("--damage-count", type=int, default=0)
    ap.add_argument("--wellhead-damage", action="store_true", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline", default=None, help="baseline .docx (compare mode)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    _generate(args, args.out)
    print(f"Generated: {args.out}")

    if args.mode == "compare":
        base = args.baseline or os.path.join(os.path.dirname(args.out), "baseline.docx")
        diffs = _compare(base, args.out)
        if not diffs:
            print("✅ IDENTICAL — no meaningful differences vs baseline.")
            sys.exit(0)
        print(f"❌ {len(diffs)} difference(s) vs baseline:")
        for d in diffs:
            print("  ", d)
        sys.exit(1)


if __name__ == "__main__":
    main()
