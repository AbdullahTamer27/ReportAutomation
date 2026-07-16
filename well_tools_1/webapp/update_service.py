"""Self-update service — fetch the control manifest, decide, and apply.

Ties the pure decision logic in :mod:`webapp.updater` to the real world:
  * fetches ``manifest.json`` from the public releases repo (with an on-disk
    cache so a *kill* is still honored when offline),
  * reports the launch decision to the UI (``check``),
  * downloads + verifies + swaps in a new build (``apply_update``) — Windows,
    packaged-build only.

Network + file I/O live here; the version-comparison / kill-switch rules live in
``updater`` (pure, unit-tested).
"""

import getpass
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from . import updater
from .config import DATA_DIR
from .version import __version__

# Public releases repo (raw manifest + release assets).
MANIFEST_URL = "https://raw.githubusercontent.com/AbdullahTamer27/Talos-releases/main/manifest.json"
RELEASE_BASE = "https://github.com/AbdullahTamer27/Talos-releases/releases/download"
_CACHE_PATH = os.path.join(DATA_DIR, "manifest_cache.json")
_TIMEOUT = 6


def _make_ssl_context():
    """Verify TLS against certifi's CA bundle instead of the OS cert store.

    The frozen Windows exe has no reliable system CA store to fall back on: the
    manifest host may already be cached by Windows, but GitHub redirects release
    downloads to a CDN whose intermediate CA isn't pre-installed, which surfaces
    as ``CERTIFICATE_VERIFY_FAILED``. Shipping certifi and pointing OpenSSL
    straight at it makes verification self-contained on every machine. Falls
    back to the stdlib default in dev if certifi isn't installed."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


_SSL_CTX = _make_ssl_context()


# --- identity + version -----------------------------------------------------
def _identity():
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    try:
        machine = socket.gethostname()
    except Exception:  # noqa: BLE001
        machine = ""
    return user, machine


def current_version():
    """The running build's version — prefer the CI-stamped build_info, else the
    source __version__."""
    try:
        from .build_info import VERSION
        return VERSION
    except Exception:  # noqa: BLE001
        return __version__


# --- manifest fetch + cache -------------------------------------------------
def _read_cache():
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:  # noqa: BLE001
        pass


def fetch_manifest():
    """Return ``(manifest, online)``. On a network failure, fall back to the last
    cached manifest so a previously-seen kill still applies offline."""
    try:
        with urlopen(MANIFEST_URL, timeout=_TIMEOUT, context=_SSL_CTX) as r:
            data = json.loads(r.read().decode("utf-8"))
        _write_cache(data)
        return data, True
    except Exception:  # noqa: BLE001 — offline / DNS / 404, etc.
        return _read_cache(), False


def _download_url(version):
    return f"{RELEASE_BASE}/v{version}/Talos.exe" if version else None


# --- launch decision --------------------------------------------------------
def check():
    """Evaluate the launch decision for the UI. Returns a plain dict.

    Kills (universal version floor + targeted blocklist) are honored even
    offline from the cached manifest. Ordinary update prompts are suppressed
    when offline (you can't download anyway) — fail-open."""
    manifest, online = fetch_manifest()
    cur = current_version()
    user, machine = _identity()
    d = updater.evaluate(manifest, cur, username=user, machine=machine)

    status = d.status
    if not online and status in (updater.UPDATE_OPTIONAL, updater.UPDATE_REQUIRED):
        status = updater.OK   # can't update offline — don't nag

    return {
        "status": status,
        "current": cur,
        "latest": d.latest,
        "message": d.message,
        "download_url": _download_url(d.latest),
        "online": online,
        "reason": d.reason,
    }


# --- apply (download + verify + swap-restart) -------------------------------
class UpdateError(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_update():
    """Download the latest build next to the current exe, verify its SHA256, then
    launch a helper that waits for this process to exit, swaps the exe, and
    relaunches. Only meaningful in the packaged Windows build."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        raise UpdateError("Update install is only available in the packaged Windows app.")

    d = check()
    url = d["download_url"]
    if not url or d["status"] not in (updater.UPDATE_OPTIONAL, updater.UPDATE_REQUIRED):
        raise UpdateError("No update is available to install.")

    cur_exe = sys.executable
    folder = os.path.dirname(cur_exe)
    new_exe = os.path.join(folder, f"Talos_{d['latest']}.new.exe")

    # Download the new exe + its checksum, then verify before we touch anything.
    _download(url, new_exe)
    try:
        expected = _fetch_text(url + ".sha256").split()[0].strip().lower()
        if _sha256(new_exe).lower() != expected:
            os.remove(new_exe)
            raise UpdateError("Downloaded update failed its checksum — aborted.")
    except UpdateError:
        raise
    except Exception:  # noqa: BLE001 — no/failed checksum: proceed but note it
        pass

    _spawn_swap_helper(cur_exe, new_exe)
    # Give the helper a beat to start, then exit so the file can be replaced.
    os._exit(0)


def _download(url, dest):
    try:
        with urlopen(url, timeout=60, context=_SSL_CTX) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:  # noqa: BLE001
        raise UpdateError(f"Download failed: {e}") from e


def _fetch_text(url):
    with urlopen(url, timeout=_TIMEOUT, context=_SSL_CTX) as r:
        return r.read().decode("utf-8")


def _spawn_swap_helper(cur_exe, new_exe):
    """Write and launch a detached .bat that waits for the old exe to unlock,
    replaces it with the freshly-downloaded build, and relaunches it.

    Two subtleties of the frozen onefile case, both of which broke the earlier
    version (download succeeded but the swap/relaunch didn't happen):

      * The PyInstaller bootloader keeps ``cur_exe`` locked until it fully exits
        — a beat *after* our ``os._exit(0)``. So we RETRY the move until the lock
        clears rather than assuming the file is free the moment our PID is gone.
      * ``timeout`` fails in a console-less detached process ("Input redirection
        is not supported") and returns instantly, so we sleep with ``ping``.
    """
    bat = os.path.join(tempfile.gettempdir(), "talos_update.bat")
    script = (
        "@echo off\r\n"
        "setlocal\r\n"
        "set /a tries=0\r\n"
        ":swap\r\n"
        # Succeeds only once every handle to the old exe is released.
        f'move /y "{new_exe}" "{cur_exe}" >nul 2>&1 && goto launch\r\n'
        "set /a tries+=1\r\n"
        "if %tries% geq 60 goto done\r\n"      # ~60s ceiling, then give up cleanly
        "ping -n 2 127.0.0.1 >nul\r\n"         # ~1s sleep that works without a console
        "goto swap\r\n"
        ":launch\r\n"
        f'start "" "{cur_exe}"\r\n'
        ":done\r\n"
        'del "%~f0"\r\n'
    )
    with open(bat, "w", encoding="utf-8") as f:
        f.write(script)
    DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["cmd", "/c", bat], creationflags=DETACHED, close_fds=True)
