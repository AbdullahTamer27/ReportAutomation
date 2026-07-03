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
