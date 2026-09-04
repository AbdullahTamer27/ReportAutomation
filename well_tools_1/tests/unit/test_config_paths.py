"""Where the app's files live.

The OPS workbook is the interesting case: it is bundled read-only and must stay
out of the user's template folder. That is a requirement about *absence* — the
Template Manager listing it, or `ensure_user_data` seeding a copy into
%APPDATA%, would silently hand users an editable, deletable copy of a file the
engine depends on. Nothing about the app's behaviour would look wrong until one
of them changed it.
"""

import os

from webapp import config


def test_the_ops_workbook_is_not_a_user_template():
    ops = os.path.abspath(config.OPS_TEMPLATE_PATH)
    templates = os.path.abspath(config.TEMPLATES_DIR)
    bundled = os.path.abspath(config.BUNDLED_TEMPLATES_DIR)

    assert not ops.startswith(templates + os.sep)
    assert not ops.startswith(bundled + os.sep)


def test_the_ops_workbook_is_never_seeded_into_user_data(tmp_path, monkeypatch):
    """`ensure_user_data` copies the bundled templates and logos into the user's
    data directory. The OPS workbook must not travel with them."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "TEMPLATES_DIR", str(tmp_path / "templates"))
    monkeypatch.setattr(config, "COMPANIES_DIR", str(tmp_path / "companies"))

    config.ensure_user_data()

    seeded = [name for _, _, files in os.walk(tmp_path) for name in files]
    assert not any(name.lower() == "ops.xlsx" for name in seeded)


def test_the_workbook_can_be_overridden_for_design_work(monkeypatch):
    """The escape hatch that keeps design iteration off the release cycle —
    an env var, deliberately absent from the UI."""
    import importlib

    monkeypatch.setenv("OPS_TEMPLATE", "/somewhere/else/Custom.xlsx")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.OPS_TEMPLATE_PATH == "/somewhere/else/Custom.xlsx"
    finally:
        monkeypatch.delenv("OPS_TEMPLATE")
        importlib.reload(config)
