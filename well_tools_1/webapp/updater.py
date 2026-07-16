"""Update / control policy — the pure decision logic (no network, no UI).

Given the current app version, the local identity, and a *control manifest*
(fetched from the public releases repo, or the cached copy when offline), decide
what the app should do on launch:

    OK               → run normally
    UPDATE_OPTIONAL  → a newer version exists; offer it, user may dismiss
    UPDATE_REQUIRED  → below the required-update floor; must update (no dismiss)
    BLOCKED          → refuse to run (universal version kill, or this user/machine
                       is on the targeted blocklist)

This module is deliberately I/O-free so it is fully unit-testable and identical
on every platform. Fetching, caching, the prompt UI, and the swap-restart live
elsewhere; they call :func:`evaluate`.

The blocklist is matched on ``sha256(username)`` — hashed so the (public) manifest
never exposes names, and keyed on the username so a reinstall doesn't evade it.
This is a *soft* control: a determined reverse-engineer can patch it out. It is a
deterrent for a trusted internal team, not a hard lock.
"""

import hashlib
from dataclasses import dataclass

OK = "ok"
UPDATE_OPTIONAL = "update_optional"
UPDATE_REQUIRED = "update_required"
BLOCKED = "blocked"


@dataclass
class Decision:
    status: str
    latest: str | None = None
    message: str = ""
    reason: str = ""          # machine-readable: why (for logs/tests)


def parse_version(text):
    """'v1.2.0' / '1.2' → (1, 2, 0). Non-numeric parts are ignored; missing
    components pad with 0. Returns () for empty/None (sorts lowest)."""
    if not text:
        return ()
    s = str(text).strip().lstrip("vV")
    s = s.split("-")[0].split("+")[0]        # drop pre-release / build metadata
    parts = []
    for chunk in s.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def version_lt(a, b):
    """True if version `a` is strictly older than `b`."""
    return parse_version(a) < parse_version(b)


def user_hash(username):
    """sha256 of the normalized username (case-insensitive, trimmed)."""
    norm = (username or "").strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def evaluate(manifest, current_version, username=None, machine=None):
    """Decide what to do on launch. `manifest` is the control dict (any key may be
    absent → no constraint). Precedence: kill > blocked > required > optional > ok."""
    manifest = manifest or {}
    latest = manifest.get("latest")

    # 1) Universal kill switch — refuse to run below this version.
    kill_below = manifest.get("kill_below")
    if kill_below and version_lt(current_version, kill_below):
        return Decision(BLOCKED, latest, manifest.get("message", ""),
                        reason="version_below_kill")

    # 2) Targeted kill switch — this user or machine is blocked.
    blocked_users = set(manifest.get("blocked_users") or ())
    if username is not None and user_hash(username) in blocked_users:
        return Decision(BLOCKED, latest, manifest.get("message", ""),
                        reason="user_blocked")
    blocked_machines = {m.strip().lower() for m in (manifest.get("blocked_machines") or ())}
    if machine and machine.strip().lower() in blocked_machines:
        return Decision(BLOCKED, latest, manifest.get("message", ""),
                        reason="machine_blocked")

    # 3) Required-update floor — must update, prompt not dismissable.
    required_min = manifest.get("required_min")
    if required_min and version_lt(current_version, required_min):
        return Decision(UPDATE_REQUIRED, latest, manifest.get("message", ""),
                        reason="below_required_min")

    # 4) Optional update — a newer version exists; user may dismiss.
    if latest and version_lt(current_version, latest):
        return Decision(UPDATE_OPTIONAL, latest, manifest.get("message", ""),
                        reason="newer_available")

    return Decision(OK, latest, reason="current")
