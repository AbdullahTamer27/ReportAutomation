@echo off
REM ============================================================
REM  Build WellTools web-app desktop EXE
REM  Run from the well_tools_1\ folder with your conda env active
REM ============================================================

echo.
echo === Well Tools — EXE build ===
echo.

echo [1/3] Installing / verifying build dependencies...
pip install pyinstaller pywin32 ^
    fastapi "uvicorn[standard]" sqlalchemy pywebview ^
    pymupdf docx2pdf python-docx openpyxl pandas lxml matplotlib
echo.

echo [2/3] Running pywin32 post-install (COM support for docx2pdf)...
python -m pywin32_postinstall -install 2>nul
echo.

echo [3/3] Building with PyInstaller...
pyinstaller --clean --noconfirm WellTools.spec
echo.

if exist dist\WellTools\WellTools.exe (
    echo ============================================================
    echo  BUILD SUCCEEDED
    echo  EXE:  dist\WellTools\WellTools.exe
    echo  Distribute the entire dist\WellTools\ folder.
    echo ============================================================
) else (
    echo ============================================================
    echo  BUILD FAILED — check the output above for errors.
    echo ============================================================
    exit /b 1
)

pause
