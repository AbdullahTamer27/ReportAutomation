"""Unit tests for the update / control decision logic — the universal and
targeted kill switches, required vs optional updates, and version comparison."""

import pytest

from webapp import updater as up


# ---- version parsing / comparison ------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("1.2.0", (1, 2, 0)), ("v1.2.0", (1, 2, 0)), ("1.2", (1, 2)),
    ("2.0.0-beta.1", (2, 0, 0)), ("", ()), (None, ()),
])
def test_parse_version(text, expected):
    assert up.parse_version(text) == expected


@pytest.mark.parametrize("a,b,older", [
    ("1.0.0", "1.0.1", True), ("1.2", "1.10", True), ("2.0.0", "1.9.9", False),
    ("1.0.0", "1.0.0", False), ("v1.0", "1.0.1", True),
])
def test_version_lt(a, b, older):
    assert up.version_lt(a, b) is older


def test_user_hash_is_case_insensitive_and_stable():
    assert up.user_hash("JDoe") == up.user_hash("  jdoe ")
    assert up.user_hash("jdoe") != up.user_hash("someoneelse")


# ---- evaluate: precedence and each branch ----------------------------------
def test_ok_when_current_and_no_constraints():
    d = up.evaluate({"latest": "1.0.0"}, "1.0.0", username="jdoe")
    assert d.status == up.OK


def test_optional_update_is_dismissable_status():
    d = up.evaluate({"latest": "1.1.0"}, "1.0.0", username="jdoe")
    assert d.status == up.UPDATE_OPTIONAL and d.latest == "1.1.0"


def test_required_update_below_floor():
    d = up.evaluate({"latest": "1.2.0", "required_min": "1.1.0"}, "1.0.0")
    assert d.status == up.UPDATE_REQUIRED


def test_universal_kill_switch_blocks_old_versions():
    m = {"latest": "1.2.0", "kill_below": "1.0.0", "message": "Update required."}
    assert up.evaluate(m, "0.9.0").status == up.BLOCKED
    assert up.evaluate(m, "1.0.0").status != up.BLOCKED   # at/above floor is fine


def test_targeted_kill_switch_blocks_listed_user():
    m = {"latest": "1.0.0", "blocked_users": [up.user_hash("mallory")]}
    assert up.evaluate(m, "1.0.0", username="mallory").status == up.BLOCKED
    assert up.evaluate(m, "1.0.0", username="alice").status == up.OK


def test_targeted_kill_switch_by_machine():
    m = {"latest": "1.0.0", "blocked_machines": ["OLD-PC-01"]}
    assert up.evaluate(m, "1.0.0", machine="old-pc-01").status == up.BLOCKED
    assert up.evaluate(m, "1.0.0", machine="my-pc").status == up.OK


def test_kill_takes_precedence_over_required_and_optional():
    m = {"latest": "2.0.0", "required_min": "1.5.0", "kill_below": "1.0.0"}
    # version below everything → the hardest outcome (blocked) wins
    assert up.evaluate(m, "0.5.0").status == up.BLOCKED


def test_blocked_user_beats_available_update():
    m = {"latest": "2.0.0", "blocked_users": [up.user_hash("mallory")]}
    assert up.evaluate(m, "1.0.0", username="mallory").status == up.BLOCKED


def test_empty_manifest_is_ok():
    assert up.evaluate({}, "1.0.0", username="jdoe").status == up.OK
    assert up.evaluate(None, "1.0.0").status == up.OK
