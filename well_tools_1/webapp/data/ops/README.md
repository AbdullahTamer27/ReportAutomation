# OPS workbook (bundled, not user-facing)

`OPS.xlsx` is the one-page-summary template. It is **deliberately not** in
`webapp/data/templates/`: the Template Manager lists that folder and seeds it
into `%APPDATA%\Talos\templates`, where a user can edit or delete what they
find. This workbook is a fixed part of the report engine instead — bundled
read-only into the exe, resolved through `config.OPS_TEMPLATE_PATH`, and never
copied into the user's data directory.

Two consequences worth knowing:

* **Changing the design means shipping a build.** That is the trade for it not
  being user-editable.
* **To iterate without a release**, point the `OPS_TEMPLATE` environment
  variable at a working copy. Nothing in the UI exposes it.

The tag contract this file must follow is documented in `PLAN.md` under
"Epic D — one-page summary".
