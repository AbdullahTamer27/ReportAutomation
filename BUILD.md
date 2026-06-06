# Building the WellTools Desktop EXE (Phase 5)

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
| **Microsoft Word** | Required for the PDF preview feature. Without it the `.docx` still generates cleanly; only the preview panel shows "unavailable" |
| **Edge WebView2 runtime** | Ships pre-installed on Windows 11 and most up-to-date Windows 10 machines. If the window opens but shows blank, install from: https://developer.microsoft.com/en-us/microsoft-edge/webview2/ |

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
pyinstaller --clean --noconfirm WellTools.spec
```

Output lands at:

```
well_tools_1\dist\WellTools\
    WellTools.exe           ← the entry point users double-click
    _internal\              ← all bundled Python + DLLs (don't touch)
        webapp\
            static\         ← bundled frontend (HTML/JS/CSS)
            data\
                templates\  ← bundled template .docx files + manifest.json
```

**Distribute the entire `dist\WellTools\` folder** — the EXE alone won't run.
Zip it for distribution: `WellTools_v1.0.zip`.

---

## First run on a clean machine

1. Unzip `WellTools_v1.0.zip` anywhere (e.g. `C:\WellTools\`).
2. Double-click `WellTools.exe`.
3. The first launch creates `_internal\webapp\data\app.db` and seeds the template registry from the bundled `manifest.json`. This takes 2–3 seconds.
4. The Well Tools window opens. Verify:
   - The **home screen** shows three mode cards.
   - **Template Manager** lists the bundled templates.
   - **Report Automation** → choose an Excel file and working folder → template dropdown is populated.
   - **Generate Report** produces a `.docx` in the chosen working folder.
   - **PDF preview** renders (confirms Word + WebView2 are both working).
5. If the window is blank/white: install the Edge WebView2 runtime (see link above).
6. If PDF preview shows "unavailable": Word is not installed or not activated on this machine.

---

## Debugging a broken build

In `WellTools.spec`, change:

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

Use the **Template Manager** inside the app:
1. Copy your new `.docx` to `_internal\webapp\data\templates\`.
2. Open the app → **Template Manager** → **Register a new template**.
3. The dropdown updates immediately; `manifest.json` is rewritten automatically.

> **Note:** If the user replaces the `WellTools\` folder with a new build, the
> `_internal\webapp\data\` folder (DB + any user-added templates) is overwritten.
> Phase 6 will move mutable data to an external location (e.g. `%APPDATA%\WellTools\`
> or a shared network drive via the `TEMPLATES_DIR` env var).

---

## Production: shared network templates

Set the `TEMPLATES_DIR` environment variable before launching to point at a
shared drive — no code change or rebuild needed:

```bat
set TEMPLATES_DIR=\\server\share\WellToolsTemplates
WellTools.exe
```

Or create a wrapper `.bat` file that sets the variable and launches the EXE.
All users on the network see the same template library.
