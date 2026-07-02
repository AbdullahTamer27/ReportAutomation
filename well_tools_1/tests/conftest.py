"""Shared test setup.

Puts the project root (``well_tools_1/``) on ``sys.path`` so tests can
``import webapp`` / ``import well_tools`` regardless of where pytest is invoked,
and provides a fixture that freezes "today" so date-dependent output (the
``{{delivery_date}}`` tag) is deterministic for golden comparisons.
"""

import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # well_tools_1/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# A fixed "now" so {{delivery_date}} is stable across runs/machines.
FROZEN_NOW = datetime(2026, 1, 1, 12, 0, 0)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze `datetime.now()` inside the report service to `FROZEN_NOW`."""
    import webapp.report_service as rs
    monkeypatch.setattr(rs, "datetime", _FrozenDatetime)
    return FROZEN_NOW
