# Real fixture set — put your clean sample here

Drop **one sanitized, real** input set in *this folder* so the golden tests can
prove a full, realistic report generation never changes unexpectedly.

## What to put here

| File | Name it exactly | What it is |
| ---- | --------------- | ---------- |
| Word template | `template.docx` | The universal master template you actually use (e.g. a copy of `ePDT_Sample.docx`). |
| Excel data | `data.xlsm` (or `.xlsx`) | The workbook you generate from — with the per-pipe `…Pipe` sheets, the `THICKNESS` sheet, and (if present) `intervals MAIN`. |
| WellSchematic XML | `schematic.xml` | The schematic that drives config / depths / damage count. |
| Images | `IMGS/` (a subfolder) | The photos/plots the template places (`proc`, `wh`, `raw`, damage photos, …). |
| Settings | `inputs.json` | The non-file inputs — see below. |

### `inputs.json`

```json
{
  "config": "4.5TBG-7LNR-9.625-13.375-18.625",
  "company": null,
  "damage_count": 0,
  "wellhead_damage": false,
  "include_disclaimer": false,
  "well_name": "SAMPLE_1_0",
  "field": "",
  "well_type": "",
  "notes": "Anything sensitive should be scrubbed — this gets committed to git."
}
```

## Sanitize before committing

This folder **is committed to the repo**, so remove anything confidential:
real well names, field names, client identifiers, proprietary notes. Rename the
well to something generic (e.g. `SAMPLE_1_0`) and blur/replace sensitive photos if
needed. The test only cares that the *pipeline* produces a stable document — not
what the well actually is.

## What happens next

Once your files are here, the golden test will:
1. run a full generation from `template.docx` + `data.xlsm` + `schematic.xml` + `IMGS/` + `inputs.json`,
2. save the result as the committed **golden** output the first time,
3. on every later run, diff a fresh generation against that golden and fail on any
   meaningful change.

If you'd rather not commit a real set at all, that's fine — the `synthetic/`
fixtures still give end-to-end coverage; the real set just adds confidence that a
production-shaped document stays stable.
