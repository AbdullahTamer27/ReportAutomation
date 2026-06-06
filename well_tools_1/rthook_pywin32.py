# Runtime hook: make pywin32 system DLLs findable by Windows COM when frozen.
# PyInstaller places pythoncom3X.dll / pywintypes3X.dll inside _internal/ but
# Windows COM infrastructure only searches standard system paths. We register
# _internal/ (sys._MEIPASS) and the EXE's own directory as DLL search paths
# so COM automation (docx2pdf → Word) finds them.

import os
import sys

if hasattr(sys, "_MEIPASS"):
    # Primary: the bundle extraction directory (_internal/)
    try:
        os.add_dll_directory(sys._MEIPASS)
    except (AttributeError, OSError):
        pass

    # Secondary: the folder containing the EXE itself (for --onedir root)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if exe_dir and exe_dir != sys._MEIPASS:
        try:
            os.add_dll_directory(exe_dir)
        except (AttributeError, OSError):
            pass
