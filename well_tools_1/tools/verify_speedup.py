"""One-command check that the single-doc-I/O speedup changes nothing.

Run this on the machine where you normally generate reports. It:
  1. finds the inputs of your most recent SUCCESSFUL report run (from the app's
     database), or uses the ones you pass on the command line,
  2. generates the report the OLD way (open the Word file at every step) and the
     NEW way (open once, save once), and
  3. compares the two documents part-by-part.

It prints either:
    ✅ IDENTICAL — safe to turn the speedup on.
or:
    ❌ N difference(s) — <what differs>

Usage (simplest — uses your last successful run automatically):
    python tools/verify_speedup.py

With an XML schematic (recommended, exercises the damage/config paths):
    python tools/verify_speedup.py --xml "C:\\path\\to\\WellSchematic.xml"

Override any input:
    python tools/verify_speedup.py --template ... --excel ... --workdir ...
                                   --config "4.5-7-9-13-18" --xml ...
"""

import argparse
import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import golden_report  # noqa: E402  (same tools/ dir)

DB_PATH = os.path.join(ROOT, "webapp", "data", "app.db")


def _last_successful_run():
    """(template, excel, workdir, config) from the newest successful run, or Nones."""
    if not os.path.isfile(DB_PATH):
        return None
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        """SELECT t.file_path, r.excel_path, r.working_dir, t.config_key
           FROM report_runs r JOIN templates t ON t.id = r.template_id
           WHERE r.status = 'success'
           ORDER BY r.id DESC LIMIT 1"""
    ).fetchone()
    con.close()
    return row


def _generate(ns, out_path, single_doc_io):
    os.environ["WELLTOOLS_SINGLE_DOC_IO"] = "1" if single_doc_io else "0"
    golden_report._generate(ns, out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template")
    ap.add_argument("--excel")
    ap.add_argument("--workdir")
    ap.add_argument("--config")
    ap.add_argument("--xml")
    ap.add_argument("--damage-count", type=int, default=0)
    ap.add_argument("--wellhead-damage", action="store_true", default=None)
    args = ap.parse_args()

    # Fill any missing input from the last successful run.
    if not (args.template and args.excel and args.workdir):
        row = _last_successful_run()
        if row:
            tpl, xls, wd, cfg = row
            args.template = args.template or tpl
            args.excel = args.excel or xls
            args.workdir = args.workdir or wd
            args.config = args.config or cfg

    missing = [n for n in ("template", "excel", "workdir") if not getattr(args, n)]
    if missing:
        print("Could not determine:", ", ".join(missing))
        print("Pass them explicitly, e.g.:")
        print('  python tools/verify_speedup.py --template ... --excel ... --workdir ...')
        sys.exit(2)

    print("Using inputs:")
    print(f"   template : {args.template}")
    print(f"   excel    : {args.excel}")
    print(f"   workdir  : {args.workdir}")
    print(f"   config   : {args.config}")
    print(f"   xml      : {args.xml or '(none)'}")
    for name, val in (("template", args.template), ("excel", args.excel), ("workdir", args.workdir)):
        ok = os.path.isdir(val) if name == "workdir" else os.path.isfile(val)
        if not ok:
            print(f"\n❌ {name} not found on this machine: {val}")
            sys.exit(2)
    print()

    ns = types.SimpleNamespace(
        template=args.template, excel=args.excel, workdir=args.workdir,
        config=args.config, xml=args.xml, damage_count=args.damage_count,
        wellhead_damage=args.wellhead_damage,
    )

    tmp = tempfile.mkdtemp(prefix="verify_speedup_")
    old_path = os.path.join(tmp, "old_way.docx")
    new_path = os.path.join(tmp, "new_way.docx")

    print("Generating the OLD way (open at every step)…")
    _generate(ns, old_path, single_doc_io=False)
    print("Generating the NEW way (open once, save once)…")
    _generate(ns, new_path, single_doc_io=True)
    print()

    diffs = golden_report._compare(old_path, new_path)
    if not diffs:
        print("✅ IDENTICAL — the speedup produces the exact same report.")
        print("   You can enable it permanently. Paste this result back.")
        sys.exit(0)
    print(f"❌ {len(diffs)} difference(s) between old and new:")
    for d in diffs:
        print("  ", d)
    print(f"\n(Both files kept for inspection in: {tmp})")
    sys.exit(1)


if __name__ == "__main__":
    main()
