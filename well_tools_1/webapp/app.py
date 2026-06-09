"""Desktop launcher — Phase 3.

Starts Uvicorn on a free localhost port in a background thread, then opens a
native pywebview window pointing at it. FastAPI serves both the API and the
static frontend (webapp/static/).

A small JS API is exposed to the frontend as `window.pywebview.api`:
  - pick_file(filters)  -> native open-file dialog, returns absolute path | None
  - pick_folder()       -> native folder dialog, returns absolute path | None
  - reveal_file(path)   -> open the OS file manager with the file selected

Run (from the `well_tools_1/` directory):

    python -m webapp.app
"""

import os
import sys
import time
import socket
import threading
import subprocess


def _ensure_std_streams():
    """In a windowed frozen EXE (console=False) sys.stdout/sys.stderr are None.
    Anything that writes to them then crashes — notably docx2pdf's tqdm progress
    bar during PDF preview ("NoneType has no attribute 'write'"). Point the
    missing streams at a log file (falling back to devnull) so those writes
    succeed and we capture server logs / tracebacks for debugging.
    """
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_dir = os.path.join(
            os.environ.get("APPDATA") or os.path.expanduser("~"), "WellTools"
        )
        os.makedirs(log_dir, exist_ok=True)
        stream = open(os.path.join(log_dir, "welltools.log"), "a",
                      buffering=1, encoding="utf-8", errors="replace")
    except OSError:
        stream = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_std_streams()

import uvicorn
import webview

# In dev mode, make well_tools importable from well_tools_1/.
# When frozen by PyInstaller, sys.path is already managed — skip this.
if not getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)

from webapp.main import app  # noqa: E402


# --- JS API exposed to the frontend -----------------------------------------
class Api:
    """Methods here are callable from JS as window.pywebview.api.<name>(...)."""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def pick_file(self, filters=None):
        """Open a native open-file dialog. `filters` is an optional list of
        pywebview file-type strings, e.g. ['Excel files (*.xlsx;*.xlsm)'].
        Returns the chosen absolute path, or None if cancelled."""
        file_types = tuple(filters) if filters else ("All files (*.*)",)
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types,
        )
        if not result:
            return None
        return result[0]

    def pick_folder(self):
        """Open a native folder dialog. Returns the absolute path, or None."""
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0]

    def reveal_file(self, path):
        """Open the OS file manager with `path` selected. Returns True/False."""
        if not path or not os.path.exists(path):
            return False
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
            elif os.name == "nt":
                subprocess.run(["explorer", "/select,", os.path.normpath(path)], check=False)
            else:
                subprocess.run(["xdg-open", os.path.dirname(path)], check=False)
            return True
        except Exception:
            return False


# --- Server bootstrap --------------------------------------------------------
def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server(port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait until Uvicorn reports it has started (with a safety timeout).
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return server


def main():
    port = _free_port()
    _start_server(port)

    api = Api()
    window = webview.create_window(
        "Report Automation",
        url=f"http://127.0.0.1:{port}/",
        js_api=api,
        width=1180,
        height=820,
        min_size=(820, 640),
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
