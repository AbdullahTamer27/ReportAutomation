"""The swap-restart helper must relaunch the new exe with a CLEAN environment.

A onefile app runs with ``_MEIPASS2`` pointing at its own extraction dir. If the
relaunched exe inherits it, its bootloader thinks it is already extracted and
runs from the dying old process's temp dir — failing with "Failed to load Python
DLL … python311.dll". These tests pin the sanitising.
"""

import os
import tempfile
from unittest import mock

from webapp import update_service


def _spawn_and_capture(monkeyenv):
    """Run _spawn_swap_helper with a faked environment; return (script, popen_kwargs)."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return mock.Mock()

    with mock.patch.dict(os.environ, monkeyenv, clear=False), \
         mock.patch.object(update_service.subprocess, "Popen", fake_popen):
        update_service._spawn_swap_helper(r"C:\app\Talos.exe", r"C:\app\Talos_new.exe")

    bat = os.path.join(tempfile.gettempdir(), "talos_update.bat")
    with open(bat, "r", encoding="utf-8") as f:
        script = f.read()
    return script, captured


PYI_ENV = {
    "_MEIPASS2": r"C:\Users\x\AppData\Local\Temp\_MEI319682",
    "_PYI_APPLICATION_HOME_DIR": r"C:\Users\x\AppData\Local\Temp\_MEI319682",
    "_PYI_ARCHIVE_FILE": r"C:\app\Talos.exe",
    "PATH": os.environ.get("PATH", ""),
}


def test_helper_env_strips_pyinstaller_vars():
    _script, cap = _spawn_and_capture(PYI_ENV)
    env = cap["kwargs"]["env"]
    assert "_MEIPASS2" not in env
    assert not any(k.startswith("_PYI") for k in env)
    assert "PATH" in env                       # the rest of the environment survives


def test_script_clears_the_vars_too():
    script, _cap = _spawn_and_capture(PYI_ENV)
    assert 'set "_MEIPASS2="' in script
    assert 'set "_PYI_APPLICATION_HOME_DIR="' in script
    # and it clears them BEFORE launching the new exe
    assert script.index('set "_MEIPASS2="') < script.index("start ")


def test_script_still_retries_the_move_and_launches():
    script, cap = _spawn_and_capture(PYI_ENV)
    assert "move /y" in script and "goto swap" in script    # lock retry intact
    assert 'start "" "C:\\app\\Talos.exe"' in script        # relaunch intact
    assert "ping -n" in script                              # console-less sleep
    assert cap["kwargs"]["creationflags"] == (0x00000008 | 0x00000200)
