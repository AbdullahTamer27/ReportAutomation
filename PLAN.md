# Plan — Test Suite + CI/CD Auto-Update

Two parallel workstreams, one per branch, with a deliberate dependency: the test
suite lands first so the release pipeline can **gate on green tests** — we never
auto-ship a build that failed.

| Branch | Purpose | Status |
| ------ | ------- | ------ |
| `feat-testSuite` | Service extraction, pytest infra, fixtures, golden + unit tests | ✅ merged to `main` |
| `feat-autoUpdate` | Versioning, build-on-tag, self-updater, **kill switches**, signing, provenance | ◻ in progress |

Keep the two GitHub Actions workflow files separate (`test.yml` vs `release.yml`)
so they don't conflict on `main`.

### Locked decisions
1. **Service extraction (A0)** — ✅ done inside `feat-testSuite`.
2. **Release channel:** public "releases" repo (no token embedded in the app). See
   [B3](#phase-b3--release-channel-decision).
3. **Fixtures:** synthesized set committed; real set is **local-only** (git-ignored,
   too large + machine-specific) in `well_tools_1/tests/fixtures/real/`.
4. **Install location:** `%APPDATA%\Talos` (user-writable → updates need no admin).
5. **Update policy:** optional, user-dismissable — **unless** the maintainer marks a
   release *required*. Enforced via a control manifest ([B4a](#phase-b4a--control-manifest-kill-switches)).
6. **Kill switches:** both **universal** (version floor) and **targeted** (per-user),
   as a *soft* control (deterrent-grade, bypassable by a determined reverse-engineer —
   accepted for a trusted internal team). Kills are honored from a cached manifest
   when offline; normal update checks fail-open.
7. **Threat model = credit theft, not IP secrecy.** Primary defense is *provable
   authorship* (signed commits + timestamped history + build provenance), with exe
   hardening as a secondary speed bump. See [Provenance & Hardening](#provenance--hardening).

---

## Branch A — `feat-testSuite` ✅ COMPLETE (merged to `main`)

**Goal:** turn "I hope it still works" into "CI proves it," so every future change
(including the auto-updater) is safe. All phases A0–A4 done; 52 tests (49 in CI).

### Phase A0 — Extract the orchestration service *(first task)*
- Pull the `generate_report` orchestration out of `webapp/main.py` into
  `webapp/report_service.py` (or `well_tools/report/service.py`): a
  `generate(inputs) -> result` function that takes a **working directory of files**,
  not FastAPI request objects.
- `webapp/main.py` becomes a thin HTTP layer that calls the service.
- Verify nothing changed with `tools/golden_report.py` (byte/behaviour-identical).
- *Why first:* makes the whole pipeline testable without HTTP, and it's the seam a
  future hosted/upload front end would reuse.

### Phase A1 — Test infrastructure
- Add `pytest` (+ `pytest-cov`) to `well_tools_1/dev-requirements.txt`.
- Layout under `well_tools_1/`:
  ```
  tests/
    unit/                 # fast, pure-logic tests
    golden/               # end-to-end generate + diff vs committed output
    fixtures/
      synthetic/          # tiny generated inputs (built by a script)
      real/               # a sanitized real input set (you drop it here)
  ```

### Phase A2 — Golden regression tests
- Wire `tools/golden_report.py` into pytest: generate from each fixture set, diff
  against a committed golden `.docx` (canonical XML compare).
- Guards the whole pipeline end-to-end.

### Phase A3 — Unit tests for the tricky pure logic
Priority targets (most likely to break silently):
- `damage_select` — worst C/D per (interval, pipe); 200 ft clustering; "4 pipes /
  same interval → 1 picture"; out-of-interval skip.
- `pipe_config` — config parse; inner→outer XML derivation; weight-change
  consolidation; role assignment; **taper edge case** (`4.5x3.5TBG` vs split PipeSets).
- `damage_blocks` — `@N` substitution **inside text boxes** (regression lock).
- `overlays` — `_damage_mapping` wording; shoe/hanger mapping; unfilled-box removal.
- `tables` — `grade_for_loss`; **grade-correction-on-update**; summary-row cloning.
- `_wbcache` + XML cache — identity, mtime invalidation, copy isolation.
- `thickness` — channel resolution.

### Phase A4 — CI test workflow
- `test.yml`: on push/PR → install deps → run `pytest` on Linux (fast/cheap for the
  pure-Python tests).

**Definition of done:** golden tests green on all fixtures; unit tests cover the
modules above; the two open loose ends (taper, grade-copy) each have a pinning
test; `pytest` runs in CI on every PR.

**Risks / notes:** building tiny-but-representative fixtures is the fiddly part; the
Word-dependent PDF *preview* can't run on Linux CI — exclude it and test only the
generation path.

---

## Branch B — `feat-autoUpdate`

**Goal:** users click **Update Now** and get the latest build — no Python, no
installer, offline-safe — plus maintainer control (required updates, kill
switches) and provable authorship baked into every release.

### Phase B1 — Versioning
- Single source of truth: `__version__` in the app, shown in the UI (About/Help).
- Semantic versioning; releases are git tags `v*`.

### Phase B2 — Release build pipeline (`release.yml`)
- Triggers on `v*` tags; runs on `windows-latest`.
- **Gates on the test job passing.**
- Runs PyInstaller (the `build_webapp.bat` path) → `Talos.exe`.
- **Build provenance:** stamp the exe (PyInstaller version-info) and the release
  notes with the **commit SHA** + version, so every binary traces to a signed
  commit in the private repo.
- **Code-signs** the exe (self-signed cert from CI secret; see B6).
- Publishes to the public releases repo: the exe + a `SHA256` checksum + notes.

### Phase B3 — Release-channel decision
- **Chosen: a public "releases" repo** (e.g. `Talos-releases`). Binaries are
  published there; the app reads that repo's public API. Source stays private. The
  publish token lives only in CI secrets — never in the shipped exe.

### Phase B4 — In-app updater
- On launch, **non-blocking**: read local `__version__` → check the releases repo →
  compare.
- If newer: "Update available — [notes] — Update now / Later." Users can **dismiss**
  (and "skip this version") unless the release is marked **required** (then the
  prompt is not dismissable).
- Offline / unreachable → silently skip, run the current version.
- Verify the `SHA256` checksum (and, later, the signature) before applying.

### Phase B4a — Control manifest (kill switches)
A small JSON the app fetches on launch (in the releases repo), driving all the
maintainer controls from one place:
```json
{
  "latest": "1.2.0",
  "required_min": "1.1.0",     // required-update floor (dismiss disabled below this)
  "kill_below": "1.0.0",       // UNIVERSAL kill switch: refuse to run below this
  "blocked_users": ["<sha256(username)>", "..."],   // TARGETED kill switch
  "blocked_machines": ["<name>", "..."],            // optional, per-PC
  "message": "Contact admin if you see this."
}
```
- **Universal kill:** `version < kill_below` → app refuses to run, shows `message`.
- **Targeted kill:** `sha256(local_username)` in `blocked_users` (hashed so the
  public manifest never leaks names; keyed on username so a reinstall doesn't evade)
  → app refuses to run.
- **Cached-kill / offline:** cache the last manifest; a kill seen in the cache stays
  in effect offline. Normal update checks fail-open; **kills fail-safe from cache**.
- Honest limit: soft/deterrent control (a reverse-engineer can patch it out).

### Phase B5 — Swap-and-restart
- Download the new exe to temp → small helper waits for exit, swaps files, relaunches.
- App lives in `%APPDATA%\Talos` (user-writable) → no admin prompt.

### Phase B6 — Code signing *(in scope)*
- **Self-signed** cert; sign the exe in `release.yml` (`signtool`, cert from a CI
  secret). Trust the cert on team machines (manual or GPO/Intune) → no AV/SmartScreen
  warnings internally, and update integrity (each build is provably an unaltered
  official build). Paid EV cert only if it ever leaves the building.

**Definition of done:** pushing a signed `v*` tag auto-builds, signs, and publishes;
a running app detects it, updates on click, relaunches; required/kill/blocked states
all behave; offline degrades gracefully — verified on a real Windows machine.

**Risks / notes:** swap-restart is the fiddly bit (Windows integration test); the
version-compare, manifest-parse, hash-block, and cached-kill logic are all
unit-testable cross-platform → add them to the suite.

---

## Provenance & Hardening

Threat model: **credit theft by an internal colleague**, not IP monetization. The
primary defense is making authorship *overwhelmingly, independently provable*;
exe hardening is a secondary speed bump (no client-side measure stops a determined
reverse-engineer — accepted).

### P1 — Provable authorship *(do first / ongoing)*
- **Signed commits** — enable GPG or SSH commit signing so every commit is
  cryptographically bound to your identity; push frequently to keep the timestamped
  history dense and continuous on the server (which you don't control → strong).
- **Author + `LICENSE` headers** naming you; keep it in the source.
- **Contemporaneous record** — a dated note/demo to management that you built it, so
  a later claim contradicts an established prior fact (pre-emption > detection).
- **Be the visible source** — you demo, you ship releases, you own the changelog.
  The release pipeline itself makes you the continuous, attributed author of every
  version the team runs; a silent hijack needs repo/CI access you control.

### P2 — Build provenance *(part of B2)*
- Stamp every exe with its **commit SHA + version**; release notes reference the
  signed commit → each binary traces back to your history.

### P3 — Exe hardening *(secondary; raises cost, not a wall)*
- Current PyInstaller exe ships decompilable bytecode. Options, in order of value:
  **Nuitka** (compile Python → native C; much harder to reverse) > **PyArmor**
  (obfuscate bytecode). Evaluate Nuitka as a build option; treat as a deterrent.
- Code signing (B6) is *integrity*, not secrecy — it proves a build is yours/unaltered.

## Sequencing
1. ✅ **A0 → A4** — done, merged to `main`.
2. **P1 (commit signing)** — set up now; it hardens authorship immediately and is
   independent of everything else.
3. **B1 → B3** — versioning, releases repo, `release.yml` (with P2 provenance + B6
   signing built in), gated on the test job.
4. **B4 → B4a → B5** — updater, control manifest (kill switches), swap-restart;
   unit-test the manifest/version/hash/cached-kill logic.
5. **P3 (Nuitka)** — evaluate once the pipeline works; only if you want the extra
   deterrent.

---

# Epic C — Template-agnostic input form

## The problem (in one line)
The second screen (the input form) is hardcoded for the **Saudi** report. Other
reports (e.g. **Oman**) need *different* fields — some Saudi fields don't apply,
some new ones do. Piling every possible field into one form makes it giant and
tedious: you'd have to *know* which fields each report actually uses.

## The idea (simply)
**Let the template decide the form.**

A report template already says what it needs — by the `{{tags}}` it contains. A
template with `{{log_date}}` needs a log date; one without it doesn't. So instead
of a fixed form, when you pick a template the app **reads its tags and shows
exactly those fields — nothing more.**

A small **registry** in code says *how* each tag should look — `{{log_date}}` is a
date picker, `{{well_name}}` is a text box, `{{orig_comp}}` is a date, etc. If the
template uses a tag the registry doesn't know yet, it just shows a plain labelled
text box, so a brand-new report works immediately and you enrich the registry
later.

> Think of it as a form that **assembles itself** from a checklist the document
> hands it — rather than one fixed form everyone has to squint at.

## Locked decisions
1. **Source of truth = the template itself** (introspection — scan its tags).
2. **Fields are authored in code** (a registry file), by a technical maintainer —
   not an in-app UI.
3. **Rich fields** — typed inputs (dates, numbers, selects), required markers, and
   groups, like today's Saudi form.

## Two zones on the form
- **Core controls** *(always shown)* — engine inputs, NOT template text tags: file/
  folder pickers, configuration, company, damage count, disclaimer / well-head /
  FW16 toggles. Unchanged.
- **Dynamic metadata fields** *(template-driven)* — the text-tag fields
  (`{{well_name}}`, `{{log_date}}`, `{{field}}`, …). This is the part that adapts.

## Three pieces to build
1. **Field registry** — one entry per tag: `tag, label, type (text|date|number|
   select|checkbox), group, source (user|derived|engine), required, validation,
   default, order`.
   - `source=user` → a form input.
   - `source=derived` → computed from config/XML/schematic (e.g. `{{casings}}`,
     `{{btm_depth}}`) — shown read-only/prefilled or hidden.
   - `source=engine` → never a form field (`{{INTERVALS}}`, `{{pie_*}}`,
     `{{DMGi_j}}`, `{{ovl_*}}`).
2. **Introspection** — on template selection, scan the `.docx` (**body + tables +
   headers/footers + overlay text-boxes** — tags live in all of these) for every
   `{{tag}}`, intersect with the registry, render the user fields, compute the
   derived ones, ignore engine ones; unknown tags → generic labelled text box.
3. **Backend generalisation** — `report_service` stops using the fixed named
   params and builds `text_fields` generically from registry + submitted values +
   derivers. Registry becomes the single source of truth for form *and* assembly.

## Phases (each provable by goldens — Saudi output never changes until C3)
- [x] **C1 — Registry + form from registry.** Author registry for today's Saudi
      tags; render the current form from it. Same fields, same output.
- [x] **C2 — Backend reads registry.** Build `text_fields` from the registry
      generically (still all Saudi fields). Goldens unchanged.
- [x] **C3 — Introspection on.** Form shows only the tags the chosen template
      contains → the Oman template with a different tag set now "just works."
- [~] **C4 — Polish (required + groups done; date-pickers/conditional deferred).** Groups / order / required from the registry; conditional
      fields (show/hide based on another field) only if a real report needs them.

## Open decisions (pinned before C1)
- **Required-per-template** — start with `required` global-per-tag in the registry;
  add per-template overrides only if a tag is required in one report, optional in
  another.
- **Derived-tag ownership** — each deriver (config→pipe tags, XML→depth,
  schematic→dates) registers the tag(s) it produces, so introspection only runs the
  derivers whose tags appear in the template.
- **Unknown-tag default** — plain text input, labelled from the tag name (safe
  degradation; never blocks a new template).

---

# Epic D — The last three pictures

Three pictures are still pasted in by hand. They are the hardest ones left, and
they are hard for different reasons.

| Picture | Status | Why it's hard |
| ------- | ------ | ------------- |
| **QC plot** (`{{qc}}`) | ✅ done | Cropping a log sheet whose geometry changes every report |
| **One-page summary** (`{{ops}}`) | ✅ done | Composed, not cropped — drawn from the data beside the `proc` log |
| **Main vs Repeat** | ◻ | Two passes to align and compare, not one picture to crop |

### D1 — QC plot ✅
Crop the raw Warrior sheet to the track legend + the log, dropping the branding
block at the top and the legend Warrior repeats at the foot.

**Locked decision: structural, not calibrated.** The sheet is read as a stack of
blocks separated by full-width rules, and the log is the tallest of them — so the
crop holds at any vertical scale, depth or track count without ever reading the
plot's scale. Depth-based cropping (a window in feet) was considered and
deferred: it needs the `1:5000` line read off the sheet, and nothing asks for it
yet. The sheet *does* print its scale, so that door stays open.

Three things worth remembering from building it:
- **Warrior TIFFs do not decode.** The LZW strip carries no EOI terminator and
  the final row is truncated, so libtiff — and with it Pillow, `sips` and Preview
  — rejects the file outright. `well_tools/report/qc_plot.py` carries its own
  tolerant reader; every QC picture depends on it.
- **Detection cannot verify itself**, so it reports what it could not confirm as
  a report note and places the picture anyway. Being told at generation time
  beats finding out from the client.
- **Following the log's side frame was the wrong signal**, and it shipped in
  v0.2.4. On a sheet whose page border runs unbroken from the header to the
  foot, the tallest vertical line *is* that border, so the crop swallowed the
  footer legend — silently, since every sanity check still passed. Horizontal
  rules partition the sheet into blocks that a continuous border cannot bridge.

### D2 — Main vs Repeat *(next)*
Not a crop: two logging passes shown against each other. Open questions — are
they two separate sheets or two track sets on one? What does "aligned" mean when
the passes cover different depth ranges? The Warrior header prints the pass name
(the sample reads **MAIN PASS**), which is the obvious discriminator.

### D3 — One-page summary ✅
The odd one out: nothing to crop, because the picture doesn't exist — it is
composed from data the engine already holds, beside the `proc` log image.

**Locked decision: the Excel template is the design; the renderer never runs
Excel.** `webapp/data/ops/OPS.xlsx` is a hand-formatted sheet carrying `{{tags}}`.
`well_tools/report/ops_render.py` reads its column widths, row heights, fonts,
fills, borders and merges with openpyxl and redraws them with PyMuPDF. The
template is only ever *read*, so the design stays somewhere it can be seen and
adjusted, while nothing depends on Office.

Getting there cost three attempts, and the discarded two are the reason for the
third:

1. **Draw it from scratch** (`ops_panel`) — close to the design but never
   exactly it, because the design lived in code.
2. **Fill the workbook and let Excel render it** (`ops_fill` + `ops_export`) —
   abandoned after it broke in three separate ways. openpyxl does not move merged
   ranges with an inserted row, and the obvious repair (unmerge, remerge) blanks
   the cells that just moved. The authored template was macro-enabled, so a
   workbook saved as `.xlsx` carried macro content types and Excel refused to
   open it — which also killed the picture, since the export handed Excel that
   very file. And converting the template by editing its zip produced something
   openpyxl accepted and Excel did not.
3. **Read the design, draw it ourselves** — the current one. Every problem above
   was incidental to *writing* `.xlsx` files. Growing a table is a list insertion
   in an in-memory model: the rows below simply move and there is nothing to
   repair.

Worth remembering:
- **The log sets the width of its own half.** Anchored to a cell range in Excel
  it can never end level with a panel whose height depends on the well; drawn at
  the panel's full height and its own proportions, the two halves always finish
  together.
- **The template cannot know a well's string names.** A tapered
  `4 1/2" × 3 1/2" × 2 7/8" TBG` is far longer than `7" CSG`, so the Pipe OD
  column widens for the labels actually present, capped at 1.5×.
- **A trailing newline in a cell counts as a second line** and pushes text off
  its own vertical alignment. Excel shows it as nothing; it is stripped on read.
