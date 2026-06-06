"""Builds the depth-interval table from the parsed XML and optional thickness data."""

import pandas as pd

from .formatting import decimal_to_pipe_fraction, format_weight
from .thickness import _mode_for_pipe, _format_channel, _format_offset, NA_TEXT


def build_intervals_from_xml(df, thickness_sections=None):
    depths = sorted(set(df["Start"].tolist() + df["End"].tolist()))
    intervals = [(depths[i], depths[i + 1]) for i in range(len(depths) - 1)]
    has_thickness = bool(thickness_sections)
    rows = []
    for start, end in intervals:
        overlap = df[(df["Start"] <= start) & (df["End"] >= end)]
        if overlap.empty:
            continue
        overlap = overlap.sort_values('OD', ascending=True)
        ods = overlap["OD"].tolist()
        weights = overlap["Weight"].tolist()
        types = overlap["Type"].tolist()
        thicknesses = overlap["Thickness"].tolist()
        ods_formatted = [decimal_to_pipe_fraction(od) for od in ods]
        configs = []
        for od_fmt, typ, thick, wt in zip(ods_formatted, types, thicknesses, weights):
            config = f'{od_fmt}"{typ}-{thick:.3f}"@{format_weight(wt)}ppf'
            configs.append(config)
        row = {
            "Start Depth (ft)": start,
            "End Depth (ft)": end,
            "Number of Pipes": len(ods),
            "Configurations": configs
        }
        if has_thickness:
            # Channel/offset per pipe, aligned to the same ascending-OD order
            # as Configurations.
            channels, offsets = [], []
            for od in ods:
                ch = _mode_for_pipe(thickness_sections, od, start, end,
                                    "channel", _format_channel)
                off = _mode_for_pipe(thickness_sections, od, start, end,
                                     "offset", _format_offset)
                channels.append(ch if ch is not None else NA_TEXT)
                offsets.append(off if off is not None else NA_TEXT)
            row["Channels"] = channels
            row["Offsets"] = offsets
        rows.append(row)
    interval_df = pd.DataFrame(rows)
    interval_df = interval_df.sort_values("Start Depth (ft)", ascending=True)
    interval_df = interval_df.reset_index(drop=True)
    return interval_df
