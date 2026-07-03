@echo off
REM ============================================================
REM  Build Talos.exe
REM  Run this from the folder that contains run.py and well_tools\
REM ============================================================

echo Installing dependencies...
pip install pyinstaller pandas openpyxl python-docx pillow tkinterdnd2

echo.
echo Building exe...
pyinstaller --noconfirm --onefile --windowed --name Talos ^
  --collect-all tkinterdnd2 ^
  run.py

echo.
echo ============================================================
echo  Done. Your exe is here:  dist\Talos.exe
echo ============================================================
pause
