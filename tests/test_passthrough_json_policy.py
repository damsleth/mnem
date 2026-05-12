"""Per-mapping JSON policy in passthrough (Plan 01 / review F1+F4).

mnem used to unconditionally append --json to every non-interactive
routed argv, which broke OWA tools (`owa-mail config`, `owa-cal profiles`,
...) because their parsers reject --json as an unknown flag - OWA is
JSON-by-default and only honors --json on the top-level --doctor probe.

These tests pin the new contract:

  - inject  -> argv gets --json (yaams, ledger).
  - native  -> argv stays clean (owa-piggy, owa-mail, owa-cal, ...).
  - none    -> argv stays clean (used by rewrites that produce their
               own final shape, e.g. `ledger context --format json`).

Plus the top-level `mnem --json <interactive verb>` rejection so the
child setup flow does not launch under a machine invocation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mnem.commands import passthrough
from mnem.router import TABLE, lookup


def _spy_stream(monkeypatch):
  """Replace _stream_subprocess with a recorder that returns a clean
  envelope so the failure path does not fire."""
  captured: dict[str, list[str]] = {"argv": []}

  def _fake(argv, **_kwargs):
    captured["argv"] = list(argv)
    return 0, '{"tool":"x","ok":true}\n', ""

  monkeypatch.setattr(passthrough, "_stream_subprocess", _fake)
  return captured


def _spy_interactive(monkeypatch):
  captured: dict[str, list[str]] = {"argv": []}

  def _fake(argv, **_kwargs):
    captured["argv"] = list(argv)
    return 0

  monkeypatch.setattr(passthrough, "_run_interactive", _fake)
  return captured


# --- router-side policy contract -----------------------------------------

def test_owa_mappings_are_native_policy():
  for verb in (("mail",), ("calendar",), ("graph",), ("people",), ("schedule",), ("drive",)):
    mapping, _ = lookup(list(verb) + ["dummy"])
    assert mapping.json_policy == "native", verb


def test_auth_status_and_reseed_and_profiles_are_native():
  for verb in (("auth", "status"), ("auth", "reseed"), ("auth", "profiles")):
    mapping, _ = lookup(list(verb))
    assert mapping.json_policy == "native", verb


def test_auth_setup_is_none_policy_and_interactive():
  mapping, _ = lookup(["auth", "setup"])
  assert mapping.interactive is True
  assert mapping.json_policy == "none"


def test_yaams_and_ledger_mappings_keep_inject_policy():
  # yaams ingest/query and bare ledger.* should stay on inject.
  for verb in (("ingest",), ("query",), ("ledger", "paths"), ("ledger", "query")):
    mapping, _ = lookup(list(verb))
    assert mapping.json_policy == "inject", verb


# --- passthrough behavior: native = no --json ----------------------------

def test_mail_config_does_not_inject_json(monkeypatch, tmp_path: Path):
  captured = _spy_stream(monkeypatch)
  rc = passthrough.run(["mail", "config"])
  assert rc == 0
  assert captured["argv"][0] == "owa-mail"
  assert "--json" not in captured["argv"]


def test_calendar_profiles_does_not_inject_json(monkeypatch, tmp_path: Path):
  captured = _spy_stream(monkeypatch)
  passthrough.run(["calendar", "profiles"])
  assert captured["argv"][0] == "owa-cal"
  assert "--json" not in captured["argv"]


def test_auth_status_does_not_inject_json(monkeypatch):
  captured = _spy_stream(monkeypatch)
  passthrough.run(["auth", "status"])
  assert captured["argv"][0] == "owa-piggy"
  assert "--json" not in captured["argv"]


def test_query_still_injects_json(monkeypatch, tmp_path: Path):
  captured = _spy_stream(monkeypatch)
  # pass --config so the first-run guard isn't relevant inside
  # passthrough.run (it doesn't run the guard - that's cli.py).
  passthrough.run(["query", "--config", str(tmp_path / "x.yaml"), "anything"])
  assert captured["argv"][0] == "yaams"
  assert "--json" in captured["argv"]


def test_ledger_paths_still_injects_json(monkeypatch):
  captured = _spy_stream(monkeypatch)
  passthrough.run(["ledger", "paths"])
  assert captured["argv"][0] == "ledger"
  assert "--json" in captured["argv"]


# --- top-level --json rejection for interactive children ----------------

def test_top_level_json_rejects_auth_setup_before_launch(monkeypatch, capsys):
  """The whole point: stop machine callers from accidentally launching
  the interactive setup flow."""
  called = {"interactive": False, "stream": False}

  def _fake_interactive(argv):
    called["interactive"] = True
    return 0

  def _fake_stream(argv):
    called["stream"] = True
    return 0, "", ""

  monkeypatch.setattr(passthrough, "_run_interactive", _fake_interactive)
  monkeypatch.setattr(passthrough, "_stream_subprocess", _fake_stream)

  rc = passthrough.run(["auth", "setup", "--profile", "x"], top_level_json=True)
  assert rc == 2, "expected EXIT_USAGE"
  assert called["interactive"] is False
  assert called["stream"] is False
  err = capsys.readouterr().err
  assert "interactive command rejects --json" in err


def test_top_level_json_without_interactive_proceeds(monkeypatch):
  """`mnem --json mail config` should still work - mail is native, not
  interactive."""
  captured = _spy_stream(monkeypatch)
  rc = passthrough.run(["mail", "config"], top_level_json=True)
  assert rc == 0
  assert "--json" not in captured["argv"]


def test_top_level_json_with_inject_policy_proceeds(monkeypatch, tmp_path: Path):
  captured = _spy_stream(monkeypatch)
  passthrough.run(
    ["query", "--config", str(tmp_path / "x.yaml"), "anything"],
    top_level_json=True,
  )
  assert "--json" in captured["argv"]


# --- regression: interactive promote review without top-level json -----

def test_interactive_promote_review_without_top_level_json_runs(monkeypatch, tmp_path: Path):
  captured = _spy_interactive(monkeypatch)
  rc = passthrough.run(
    ["promote", "review", "--config", str(tmp_path / "cfg.yaml")]
  )
  assert rc == 0
  assert "--json" not in captured["argv"]


def test_interactive_promote_review_with_top_level_json_rejected(monkeypatch, capsys):
  rc = passthrough.run(["promote", "review"], top_level_json=True)
  assert rc == 2
  assert "interactive command rejects --json" in capsys.readouterr().err
