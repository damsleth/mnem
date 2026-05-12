"""Tests for the source-detection probes used by `mnem init`.

Probes must:
- never raise (failures become disabled=False findings).
- return ProbeResult with name/enabled/reason/optional hint+extras.
- not call out to the network and not prompt the user.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mnem.sources import (
  ProbeResult,
  probe_apple_mail,
  probe_cognitive_ledger,
  probe_github,
  probe_imessage,
  probe_obsidian,
  probe_owa_piggy,
  probe_signal,
  run_all,
)


def test_probe_result_to_dict_shape():
  r = ProbeResult(
    name="x", enabled=True, reason="ok",
    extras={"path": "/tmp/x"},
  )
  d = r.to_dict()
  assert d["name"] == "x"
  assert d["enabled"] is True
  assert d["extras"]["path"] == "/tmp/x"
  assert "hint" not in d


def test_probe_result_includes_hint_when_disabled():
  r = ProbeResult(name="x", enabled=False, reason="missing", hint="install x")
  d = r.to_dict()
  assert d["hint"] == "install x"


# --- Individual probes never raise -----------------------------------------

@pytest.mark.parametrize("probe", [
  probe_imessage,
  probe_apple_mail,
  probe_signal,
  probe_github,
  probe_owa_piggy,
  probe_obsidian,
  probe_cognitive_ledger,
])
def test_probe_never_raises(probe):
  r = probe()
  assert isinstance(r, ProbeResult)
  assert r.name
  assert isinstance(r.enabled, bool)
  assert r.reason


# --- run_all -------------------------------------------------------------

def test_run_all_returns_every_probe():
  results = run_all()
  names = {r.name for r in results}
  expected = {
    "imessage", "email", "signal", "github",
    "owa_piggy", "notes", "tier2_ledger",
  }
  assert expected.issubset(names)


def test_run_all_swallows_probe_crashes(monkeypatch):
  """A buggy probe must not abort the wizard - it should surface as
  disabled with reason='probe crashed: ...'."""
  from mnem import sources

  def _broken():
    raise RuntimeError("simulated crash")

  monkeypatch.setattr(sources, "probe_imessage", _broken)
  monkeypatch.setattr(
    sources, "_ALL_PROBES",
    [_broken, sources.probe_apple_mail],
  )
  results = sources.run_all()
  assert results[0].enabled is False
  assert "crashed" in results[0].reason


# --- iMessage path-existence behaviour --------------------------------------

def test_imessage_probe_handles_missing_chat_db(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("HOME", str(tmp_path))
  monkeypatch.setattr(Path, "home", lambda: tmp_path)
  r = probe_imessage()
  assert r.enabled is False
  assert "not found" in r.reason


def test_imessage_probe_finds_existing_chat_db(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(Path, "home", lambda: tmp_path)
  (tmp_path / "Library" / "Messages").mkdir(parents=True)
  (tmp_path / "Library" / "Messages" / "chat.db").write_bytes(b"")
  r = probe_imessage()
  assert r.enabled is True
  assert "chat.db" in r.reason
  assert r.extras["chat_db_path"].endswith("chat.db")


# --- Obsidian fallback behaviour --------------------------------------------

def test_obsidian_probe_falls_back_to_known_paths(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(Path, "home", lambda: tmp_path)
  (tmp_path / "Documents" / "Obsidian").mkdir(parents=True)
  r = probe_obsidian()
  assert r.enabled is True
  assert "vault" in r.reason.lower()


def test_obsidian_probe_disabled_when_no_vault(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(Path, "home", lambda: tmp_path)
  r = probe_obsidian()
  assert r.enabled is False
