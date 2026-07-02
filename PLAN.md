# Plan — Test Suite + CI/CD Auto-Update

Two parallel workstreams, one per branch, with a deliberate dependency: the test
suite lands first so the release pipeline can **gate on green tests** — we never
auto-ship a build that failed.

| Branch | Purpose | Order |
| ------ | ------- | ----- |
| `feat-testSuite` | Service extraction, pytest infra, fixtures, golden + unit tests | merges to `main` **first** |
| `Webmitigation`  | Version scheme, GitHub Actions build-on-tag, in-app self-updater | after the test suite exists |

Keep the two GitHub Actions workflow files separate (`test.yml` vs `release.yml`)
so they don't conflict once both live on `main`.

### Locked decisions
1. **Service extraction (A0) is the first task** — done inside `feat-testSuite`.
2. **Release channel:** public "releases" repo (no token embedded in the app). See
   [CI/CD → B3](#phase-b3--release-channel-decision) for the reasoning.
3. **Fixtures:** both a synthesized minimal set *and* a committed real set. The
   real set goes in `well_tools_1/tests/fixtures/real/` (see that folder's README).
4. **Install location:** `%APPDATA%\WellTools` (user-writable → updates need no admin).

---

## Branch A — `feat-testSuite`

**Goal:** turn "I hope it still works" into "CI proves it," so every future change
(including the auto-updater) is safe.

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

## Branch B — `Webmitigation`

**Goal:** users click **Update Now** and get the latest build — no Python, no
installer, offline-safe otherwise.

### Phase B1 — Versioning
- Single source of truth: `__version__` in the app, shown in the UI.
- Semantic versioning; releases are git tags `v*`.

### Phase B2 — Release build pipeline (`release.yml`)
- Triggers on `v*` tags; runs on `windows-latest`.
- **Gates on `feat-testSuite`'s test job passing.**
- Runs PyInstaller (the `build_webapp.bat` path) → `WellTools.exe`.
- Creates a GitHub Release, attaches the exe + a checksum + changelog notes.

### Phase B3 — Release-channel decision
- **Chosen: a public "releases" repo.** Binaries are published there; the app reads
  that repo's public API. Source stays private. No secret in the shipped exe.

### Phase B4 — In-app updater
- On launch, **non-blocking**: read local `__version__` → query the releases repo's
  `releases/latest` → compare.
- If newer: "Update available — [notes] — Update now / Later."
- Offline / API unreachable → silently skip, run the current version.
- Verify the download checksum before applying.

### Phase B5 — Swap-and-restart
- Download the new exe to temp → launch a small helper that waits for the app to
  exit, swaps the files, relaunches.
- App lives in `%APPDATA%\WellTools` (user-writable) → no admin prompt.

### Phase B6 — Signing *(deferred)*
- Ship **unsigned** first. If AV/SmartScreen complains → **self-sign** and trust the
  cert on team machines (free). Paid EV cert only if it ever leaves the building.

**Definition of done:** pushing a `v*` tag auto-builds and publishes a release; a
running app detects it, updates on click, and relaunches on the new version —
verified on a real Windows machine; the offline path degrades gracefully.

**Risks / notes:** the swap-restart is the fiddly bit and needs a Windows
integration test; AV behaviour is environment-dependent (hence deferred signing).
The version-compare and API-parse logic is unit-testable cross-platform — put those
tests in `feat-testSuite`.

---

## Sequencing
1. **A0 → A2** (extract service + golden safety net) — smallest path to "safe changes."
2. **A3 → A4** (unit tests + CI) → merge `feat-testSuite` to `main`.
3. **B1 → B5** on `Webmitigation`, with `release.yml` depending on the test job.
4. **B6** only if reality demands it.
