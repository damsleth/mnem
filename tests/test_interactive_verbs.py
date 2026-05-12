"""Interactive verbs (promote review, auth setup) must NOT have
--json injected into argv and must NOT capture stdio.

CONVENTIONS.md marks these as interactive class with --json
rejected. Before the fix mnem unconditionally appended --json,
which made `mnem promote review` and `mnem auth setup` fail before
prompting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mnem.commands import passthrough
from mnem.router import TABLE, lookup


def test_promote_review_is_marked_interactive():
  mapping, _ = lookup(["promote", "review"])
  assert mapping.interactive is True


def test_auth_setup_is_marked_interactive():
  mapping, _ = lookup(["auth", "setup"])
  assert mapping.interactive is True


def test_non_interactive_verbs_stay_non_interactive():
  for verb in (("query",), ("ingest",), ("ledger", "init"), ("promote", "list"), ("mail",)):
    mapping, _ = lookup(list(verb))
    assert mapping.interactive is False, verb


def test_interactive_run_does_not_inject_json(monkeypatch, tmp_path: Path):
  """Spy on _run_interactive: argv must not contain --json."""
  captured: dict[str, list[str]] = {}

  def _fake_interactive(argv):
    captured["argv"] = list(argv)
    return 0

  monkeypatch.setattr(passthrough, "_run_interactive", _fake_interactive)

  # Need to bypass the first-run guard since promote review is in
  # _VERBS_NEEDING_CONFIG. Easiest: pass --config explicitly.
  rc = passthrough.run(
    ["promote", "review", "--config", str(tmp_path / "cfg.yaml")]
  )
  assert rc == 0
  assert captured["argv"][0] == "yaams"
  assert "--json" not in captured["argv"]


def test_interactive_run_bypasses_stream_subprocess(monkeypatch):
  """_stream_subprocess must NOT be called for interactive verbs -
  it captures stdio, which breaks interactive prompts."""
  stream_called = {"flag": False}

  def _fake_stream(argv):
    stream_called["flag"] = True
    return 0, "", ""

  def _fake_interactive(argv):
    return 0

  monkeypatch.setattr(passthrough, "_stream_subprocess", _fake_stream)
  monkeypatch.setattr(passthrough, "_run_interactive", _fake_interactive)

  passthrough.run(["auth", "setup", "--profile", "test"])
  assert stream_called["flag"] is False


def test_non_interactive_run_still_uses_stream_subprocess(monkeypatch, tmp_path: Path):
  """The regression check: non-interactive paths must keep going
  through _stream_subprocess (NDJSON streaming, stderr capture, log
  rotation all depend on it)."""
  stream_called = {"flag": False, "argv": []}

  def _fake_stream(argv):
    stream_called["flag"] = True
    stream_called["argv"] = list(argv)
    # Return a clean envelope to skip the failure path.
    return 0, '{"tool":"yaams","ok":true}\n', ""

  monkeypatch.setattr(passthrough, "_stream_subprocess", _fake_stream)
  passthrough.run(["query", "--config", str(tmp_path / "x.yaml"), "x"])
  assert stream_called["flag"] is True
  # Non-interactive path SHOULD have --json injected.
  assert "--json" in stream_called["argv"]


def test_run_interactive_unit(tmp_path: Path):
  """_run_interactive forwards the exit code from the child."""
  script = tmp_path / "exit42.py"
  script.write_text("import sys; sys.exit(42)\n")
  rc = passthrough._run_interactive([sys.executable, str(script)])
  assert rc == 42


def test_run_interactive_missing_binary(tmp_path: Path):
  rc = passthrough._run_interactive([str(tmp_path / "no-such-binary")])
  assert rc == 127
