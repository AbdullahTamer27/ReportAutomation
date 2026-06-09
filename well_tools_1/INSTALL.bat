@echo off
REM ============================================================
REM  Well Tools — first-run installer
REM  Run this ONCE on a new machine before using WellTools.exe
REM  After this, double-click WellTools.exe directly every time.
REM ============================================================

echo.
echo === Well Tools Setup ===
echo.

REM --- 1. Visual C++ Runtime (required by Python / the EXE itself) ----------
if exist "vc_redist.x64.exe" (
    echo [1/2] Installing Microsoft Visual C++ Runtime...
    vc_redist.x64.exe /install /quiet /norestart
    echo       Done.
) else (
    echo [1/2] vc_redist.x64.exe not found -- skipping.
    echo       If the app fails to open, download and run it manually:
    echo       https://aka.ms/vs/17/release/vc_redist.x64.exe
)

echo.

REM --- 2. Edge WebView2 Runtime (required for the app window) ---------------
if exist "MicrosoftEdgeWebview2Setup.exe" (
    echo [2/2] Installing Edge WebView2 Runtime...
    MicrosoftEdgeWebview2Setup.exe /silent /install
    echo       Done.
) else (
    echo [2/2] MicrosoftEdgeWebview2Setup.exe not found -- skipping.
    echo       On Windows 11 this is already built in.
    echo       On older Windows 10, download it from:
    echo       https://developer.microsoft.com/microsoft-edge/webview2/
)

echo.
echo ============================================================
echo  Setup complete. Launching Well Tools...
echo ============================================================
echo.

start "" "WellTools.exe"
