"""Tests for `mnem init` wizard.

The wizard is interactive class. We test:
- --json rejection
- config file is generated and parseable
- re-running with existing config respects user choice
- yaml output includes every probe's enabled flag
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mnem.cli import cli
from mnem.commands.init import _build_yaams_config, _yaams_config_path
from mnem.sources import ProbeResult


def _stub_probes() -> list[ProbeResult]:
  return [
    ProbeResult("imessage", True, "chat.db found", extras={"chat_db_path": "/tmp/chat.db"}),
    ProbeResult("email", False, "no Apple Mail", hint="run Mail.app once"),
    ProbeResult("signal", False, "Signal not installed"),
    ProbeResult("github", True, "gh authenticated"),
    ProbeResult("owa_piggy", True, "2 profiles", extras={"profiles": ["work", "personal"]}),
    ProbeResult("notes", True, "vault at /tmp/vault", extras={"vault_path": "/tmp/vault"}),
    ProbeResult("tier2_ledger", False, "ledger not on PATH", hint="brew install ledger"),
  ]


def test_init_rejects_json():
  result = CliRunner().invoke(cli, ["init", "--json"])
  assert result.exit_code == 1
  combined = result.output + (result.stderr_bytes or b"").decode("utf-8", "ignore")
  assert "interactive" in combined.lower()


def test_build_yaams_config_round_trips_through_yaml_parsing():
  """The generated YAML must be parseable by PyYAML (the dependency
  yaams already uses)."""
  pyyaml = None
  try:
    import yaml as pyyaml  # type: ignore[import-not-found]
  except ImportError:
    return  # PyYAML isn't a hard dep of mnem; skip if it's absent.
  text = _build_yaams_config(_stub_probes())
  data = pyyaml.safe_load(text)
  assert data["db_path"]
  assert data["ingest"]["imessage"]["enabled"] is True
  assert data["ingest"]["email"]["enabled"] is False
  assert data["ingest"]["github"]["enabled"] is True
  assert data["ingest"]["notes"]["enabled"] is True


def test_build_yaams_config_writes_chat_db_path_when_enabled():
  text = _build_yaams_config(_stub_probes())
  assert "chat_db_path: /tmp/chat.db" in text


def test_build_yaams_config_carries_hint_for_disabled_sources():
  text = _build_yaams_config(_stub_probes())
  # Disabled email source has its hint inline.
  assert "run Mail.app once" in text
  assert "brew install ledger" in text


def test_yaams_config_path_uses_xdg_config_home(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  assert _yaams_config_path() == tmp_path / "mnem" / "yaams" / "config.yaml"


def test_init_writes_config_when_confirmed(monkeypatch, tmp_path: Path):
  """End-to-end: pipe 'y' confirmations through, get a real config."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  # Stub probes to deterministic state.
  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  # Stub yaams binary lookup so the wizard doesn't actually run it.
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  result = CliRunner().invoke(cli, ["init"], input="y\n")
  assert result.exit_code == 0, result.output
  cfg = tmp_path / "mnem" / "yaams" / "config.yaml"
  assert cfg.is_file()
  body = cfg.read_text()
  assert "imessage" in body
  assert "enabled: true" in body
  assert "enabled: false" in body


def test_init_with_force_overwrites_existing_config(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  cfg = tmp_path / "mnem" / "yaams" / "config.yaml"
  cfg.parent.mkdir(parents=True)
  cfg.write_text("# stale\n")
  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  result = CliRunner().invoke(cli, ["init", "--force"], input="y\n")
  assert result.exit_code == 0
  # File was rewritten - the stale comment must be gone.
  assert "# stale" not in cfg.read_text()
