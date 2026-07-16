# Building the Talos Desktop EXE (Phase 5)

## Prerequisites — build machine

| Requirement | Notes |
|---|---|
| **Windows 10 / 11** | PyInstaller does not cross-compile; the EXE must be built on Windows |
| **Python 3.10–3.13** | Use the same version on the build machine as on target machines |
| **Microsoft Word** | Required at run-time for PDF preview (`docx2pdf`); also needed on the build machine so pywin32 installs correctly |
| **Conda environment** | Activate the same env you use for development before building |

## Prerequisites — target / end-user machine

| Requirement | Notes |
|---|---|
| **No Python required** | The EXE bundles everything |
| **Visual C++ Runtime** | Required by the EXE itself. Missing on truly clean machines → "failed to load python DLL" error. Fixed by running `INSTALL.bat` once (see below) |
| **Edge WebView2 runtime** | Required for the app window. Pre-installed on Windows 11; may be missing on clean Windows 10. Fixed by `INSTALL.bat` |
| **Microsoft Word** | Required only for PDF preview. Without it the `.docx` still generates; only the preview panel shows "unavailable" |

---

## Build steps

```bat
REM 1. Activate your conda environment
conda activate welltools

REM 2. cd into the well_tools_1\ folder
cd path\to\ReportAutomation\well_tools_1

REM 3. Run the build script (installs deps + calls PyInstaller)
build_webapp.bat
```

Or run PyInstaller directly:

```bat
pyinstaller --clean --noconfirm Talos.spec
```

This is a **one-file** build (`Talos.spec`). Output is a single
self-contained executable:

```
well_tools_1\dist\Talos.exe   ← the only file users need
```

The frontend, bundled templates, Python runtime, and all DLLs are packed inside
the EXE. At launch it unpacks to a temp folder (so first start takes ~2–3 s).

**Distribute just `Talos.exe`.** On a Windows 11 machine with Microsoft
Office, that single file is all you need.

For *clean* machines that may lack the runtimes, ship these alongside it (all in
one folder) so the one-time installer can run:

```
Talos.exe
INSTALL.bat                    ← run once on new machines
vc_redist.x64.exe              ← download from https://aka.ms/vs/17/release/vc_redist.x64.exe
MicrosoftEdgeWebview2Setup.exe ← download from https://developer.microsoft.com/microsoft-edge/webview2/
```

Then zip: `Talos_v1.0.zip`

**On any new machine:** unzip → run `INSTALL.bat` once → done.
After that, double-click `Talos.exe` directly every time. (On Win11 + Office
you can skip `INSTALL.bat` and just run the EXE.)

### Where the app stores its data

Because this is a one-file build (the EXE's temp folder is wiped on exit), all
**writable** data lives in a permanent per-user location:

```
%APPDATA%\Talos\
    app.db          ← report-run history
    templates\      ← seeded from the bundle on first run; Template Manager writes here
    outputs\        ← PDF-preview cache
```

Rebuilding and replacing `Talos.exe` therefore **no longer wipes** the
database or any user-added templates — they persist in `%APPDATA%`.

---

## First run on a clean machine

1. Unzip `Talos_v1.0.zip` anywhere (e.g. `C:\Talos\`).
2. Double-click `Talos.exe`.
3. The first launch creates `%APPDATA%\Talos\app.db` and seeds the template registry from the bundled `manifest.json` (copying the bundled templates into `%APPDATA%\Talos\templates\`). This takes 2–3 seconds.
4. The Talos window opens. Verify:
   - The **home screen** shows three mode cards.
   - **Template Manager** lists the bundled templates.
   - **Report Automation** → choose an Excel file and working folder → template dropdown is populated.
   - **Generate Report** produces a `.docx` in the chosen working folder.
   - **PDF preview** renders (confirms Word + WebView2 are both working).
5. If the window is blank/white: install the Edge WebView2 runtime (see link above).
6. If PDF preview shows "unavailable": Word is not installed or not activated on this machine.

---

## Debugging a broken build

In `Talos.spec`, change:

```python
console=False,   # production (no terminal)
```

to:

```python
console=True,    # shows a terminal window with server logs
```

Rebuild and rerun — the terminal prints Uvicorn logs and Python tracebacks.

---

## Adding templates without rebuilding

Use the **Template Manager** inside the app — point it at any `.docx` and it
copies the file into `%APPDATA%\Talos\templates\` for you:
1. Open the app → **Template Manager** → **Register a new template** → pick the `.docx`.
2. The dropdown updates immediately; `manifest.json` is rewritten automatically.

> **Note:** Writable data (DB + user-added templates) now lives in
> `%APPDATA%\Talos\`, **outside** the EXE. Replacing `Talos.exe` with a
> new build no longer touches it, so report history and added templates survive
> upgrades. To start fresh, delete the `%APPDATA%\Talos\` folder.

---

## Production: shared network templates

Set the `TEMPLATES_DIR` environment variable before launching to point at a
shared drive — no code change or rebuild needed:

```bat
set TEMPLATES_DIR=\\server\share\TalosTemplates
Talos.exe
```

Or create a wrapper `.bat` file that sets the variable and launches the EXE.
All users on the network see the same template library.
