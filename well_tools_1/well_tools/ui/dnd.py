"""Drag-and-drop plumbing shared by all tabs.

tkinterdnd2 is optional. If it isn't installed (or won't load against the
local Tcl/Tk build) the app still works fully via the buttons.
"""

import sys
import tkinter as tk


def _note(msg):
    """print() that won't crash a windowed PyInstaller build (stdout is None)."""
    if sys.stdout is not None:
        try:
            print(msg)
        except Exception:
            pass


try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_IMPORTED = True
except ImportError:
    DND_IMPORTED = False
    DND_FILES = None
    _note("Note: tkinterdnd2 not installed — drag-and-drop disabled. "
          "The app works fully via the buttons.")


def make_root():
    """Return (root, dnd_enabled)."""
    if DND_IMPORTED:
        try:
            return TkinterDnD.Tk(), True
        except Exception as e:
            # tkdnd present but won't load against this Tcl/Tk build.
            _note(f"Note: drag-and-drop unavailable — tkdnd failed to load "
                  f"({e}). Continuing with buttons only.")
    return tk.Tk(), False


def parse_drop_data(data):
    """Parse the platform-specific string Tk hands us on a file drop."""
    paths = []
    current = ""
    in_brace = False
    for ch in data:
        if ch == '{':
            in_brace = True
        elif ch == '}':
            in_brace = False
            if current:
                paths.append(current)
                current = ""
        elif ch == ' ' and not in_brace:
            if current:
                paths.append(current)
                current = ""
        else:
            current += ch
    if current:
        paths.append(current)
    return paths
