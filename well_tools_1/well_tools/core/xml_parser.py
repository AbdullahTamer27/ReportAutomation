"""WellSchematic XML parsing, pipe-string classification, and pipe summary."""

import xml.etree.ElementTree as ET
import pandas as pd

from .formatting import decimal_to_pipe_fraction, format_weight

TUBING_PIPESETS = {1}
LINER_TOP_THRESHOLD = 1.0  # ft


def classify_pipe_strings(pipes):
    if not pipes:
        return pipes
    surface_ref = min(p['Start'] for p in pipes)

    # Shallowest top per string.
    string_top = {}
    for p in pipes:
        ps = p['PipeSet']
        string_top[ps] = min(string_top.get(ps, float('inf')), p['Start'])

    for p in pipes:
        ps = p['PipeSet']
        if ps in TUBING_PIPESETS:
            p['Type'] = 'TBG'
        elif string_top[ps] - surface_ref > LINER_TOP_THRESHOLD:
            p['Type'] = 'LNR'
        else:
            p['Type'] = 'CSG'
    return pipes


def parse_wellschematic_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    pipes = []
    for section in root.findall('.//sectionList/EMDSPipeSection'):
        pipe_data = {
            'ItemID':    int(section.find('ItemID').text),
            'PipeSet':   int(section.find('PipeSet').text),
            'Start':     float(section.find('TopDepth').text),
            'End':       float(section.find('BottomDepth').text),
            'OD':        float(section.find('NomOD').text),
            'Weight':    float(section.find('LBPerFt').text),
            'ID':        float(section.find('NomID').text),
            'Thickness': round(float(section.find('NomThickness').text), 4),
            'Drift':     float(section.find('Drift').text)
        }
        pipes.append(pipe_data)

    classify_pipe_strings(pipes)

    df = pd.DataFrame(pipes)
    df = df.sort_values(['OD', 'Start'], ascending=[False, True]).reset_index(drop=True)
    return df


def build_pipe_summary(df):
    summary = df.copy()
    summary = summary.sort_values(['OD', 'Start'], ascending=[False, True]).reset_index(drop=True)
    rows = []
    for _, r in summary.iterrows():
        od_label = f'{decimal_to_pipe_fraction(r["OD"])}" {r["Type"]}'
        rows.append({
            "Pipe OD":       od_label,
            "Weight (ppf)":  format_weight(r["Weight"]),
            "Top (ft)":      r["Start"],
            "Bottom (ft)":   r["End"],
            "Thick_Nom":     f'{r["Thickness"]:.3f}'
        })
    return pd.DataFrame(rows)
