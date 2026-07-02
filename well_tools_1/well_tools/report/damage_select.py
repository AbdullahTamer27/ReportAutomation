"""Autonomous damage count.

Picks the worst Class C/D damage per (interval, pipe), then merges picks that sit
within a 200 ft depth window into one 'damage picture'. The number of pictures is
the damage count that pre-fills the otherwise-manual field.

Intervals come from the WellSchematic XML via the existing interval core (reused
deliberately — the user asked for it). Damage rows come from the Excel joints
tables. Pictures/overlays themselves are intentionally out of scope here; this
module only decides *how many* damage points there are.
"""

DEPTH_WINDOW_FT = 200.0          # picks within this share one picture
_SEVERITY = {"D": 2, "C": 1}     # intensive beats moderate
_GRADE_WORD = {"D": "Intensive", "C": "Moderate"}


def _intervals_from_xml(xml_path):
    """List of (start, end) depth zones from the schematic, via the interval core."""
    from well_tools.core.xml_parser import parse_wellschematic_xml
    from well_tools.core.intervals import build_intervals_from_xml
    idf = build_intervals_from_xml(parse_wellschematic_xml(xml_path))
    return [(float(r["Start Depth (ft)"]), float(r["End Depth (ft)"]))
            for _, r in idf.iterrows()]


def _interval_of(depth, intervals):
    """Index of the zone containing `depth`, or None if outside all zones."""
    for i, (s, e) in enumerate(intervals):
        if s <= depth <= e:
            return i
    return None


def _cd_damages(excel_path, pipes):
    """Every Class C/D joint across the pipes: (role, suffix, depth, grade, loss)."""
    from . import _wbcache
    from .tables import read_joints, grade_for_loss, MAX_LOSS_IDX, MAX_LOSS_DEPTH_IDX
    wb = _wbcache.load(excel_path, data_only=True)
    have = set(wb.sheetnames)
    out = []
    for p in pipes:
        sheet = p.get("sheet")
        if sheet not in have:
            continue
        for row in read_joints(wb[sheet]):
            loss = row[MAX_LOSS_IDX]
            if not isinstance(loss, (int, float)) or loss < 0:
                continue
            grade = grade_for_loss(loss)
            if grade not in ("C", "D"):
                continue
            depth = row[MAX_LOSS_DEPTH_IDX]
            if isinstance(depth, (int, float)):
                out.append({"role": p.get("role"), "suffix": p.get("suffix", ""),
                            "depth": float(depth), "grade": grade, "loss": float(loss)})
    return out


def _thickness_sections(excel_path):
    """THICKNESS sections from the data Excel (read-only), or None if absent."""
    try:
        from well_tools.core.thickness import parse_thickness_sections
        return parse_thickness_sections(excel_path) or None
    except Exception:  # noqa: BLE001 — no/unreadable THICKNESS sheet
        return None


def _resolve_channel(sections, od, intervals, iv):
    """Dominant THICKNESS channel for a pipe of `od` across interval `iv`."""
    if not sections or od is None or iv is None:
        return None
    from well_tools.core.thickness import _mode_for_pipe, _format_channel
    start, end = intervals[iv]
    return _mode_for_pipe(sections, od, start, end, "channel", _format_channel)


def compute_damage_pictures(xml_path, excel_path, pipes, depth_window=DEPTH_WINDOW_FT):
    """Return {pictures, count, warnings}. `pictures` is a list of clusters; each
    cluster is a list of damage dicts that share one picture."""
    intervals = _intervals_from_xml(xml_path)
    warnings = []

    # Worst C/D damage per (interval, pipe).
    best = {}
    skipped = 0
    for d in _cd_damages(excel_path, pipes):
        iv = _interval_of(d["depth"], intervals)
        if iv is None:
            skipped += 1
            continue
        d["interval"] = iv
        key = (iv, d["role"])
        rank = (_SEVERITY[d["grade"]], d["loss"], -d["depth"])
        if key not in best or rank > best[key][0]:
            best[key] = (rank, d)
    reps = [v[1] for v in best.values()]
    if skipped:
        warnings.append(f"{skipped} C/D damage(s) fell outside the schematic depth "
                        f"range and were not counted.")

    # Enrich each kept damage with its severity word and THICKNESS channel (the
    # dominant channel for that pipe's OD across its interval). Read-only.
    role_od = {p["role"]: (p["sizes"][0] if p.get("sizes") else None) for p in pipes}
    sections = _thickness_sections(excel_path)
    for d in reps:
        d["severity"] = _GRADE_WORD[d["grade"]]
        d["channel"] = _resolve_channel(sections, role_od.get(d["role"]),
                                        intervals, d["interval"])

    # Cluster within each interval by the depth window (anchored to cluster start).
    pictures = []
    for iv in sorted({r["interval"] for r in reps}):
        grp = sorted((r for r in reps if r["interval"] == iv), key=lambda r: r["depth"])
        clusters = []
        for r in grp:
            if clusters and r["depth"] - clusters[-1][0]["depth"] <= depth_window:
                clusters[-1].append(r)
            else:
                clusters.append([r])
        pictures.extend(clusters)
    pictures.sort(key=lambda c: min(x["depth"] for x in c))
    return {"pictures": pictures, "count": len(pictures), "warnings": warnings}


def manifest_lines(pictures):
    """One human-readable line per picture, for the UI to show before generating."""
    lines = []
    for i, cluster in enumerate(pictures, start=1):
        parts = [
            f"{d['suffix'] or d['role']} {_GRADE_WORD[d['grade']]} "
            f"{d['loss']:.1f}% @ {d['depth']:.0f} ft"
            for d in cluster
        ]
        lines.append(f"#{i} (interval {cluster[0]['interval'] + 1}): " + "; ".join(parts))
    return lines
