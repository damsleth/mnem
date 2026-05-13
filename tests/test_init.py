"""Tests for `mnem init` wizard.

The wizard is interactive class. We test:
- --json rejection
- master config file is generated and parseable
- yaams config is reused in place when canonical exists
- yaams config is written to canonical location when greenfield
- ledger/owa-piggy pointers reflect on-disk state
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mnem.cli import cli
from mnem.commands.init import _build_yaams_config
from mnem.config import master_config_path, read_master, render_master
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


def test_master_config_path_uses_xdg_config_home(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  assert master_config_path() == tmp_path / "mnem" / "config.yaml"


def test_render_master_emits_pointers_when_present():
  body = render_master(
    version="0.0.0",
    data_root=Path("/data"),
    yaams_config=Path("/cfg/yaams.yaml"),
    ledger_config=Path("/cfg/ledger.yaml"),
    owa_piggy_config=Path("/cfg/profiles.conf"),
  )
  parsed = {}
  for line in body.splitlines():
    s = line.strip()
    if not s or s.startswith("#") or ":" not in s:
      continue
    key, _, value = s.partition(":")
    parsed[key.strip()] = value.strip()
  assert parsed["yaams_config"] == "/cfg/yaams.yaml"
  assert parsed["ledger_config"] == "/cfg/ledger.yaml"
  assert parsed["owa_piggy_config"] == "/cfg/profiles.conf"
  assert parsed["data_root"] == "/data"


def test_render_master_comments_out_missing_pointers():
  body = render_master(
    version="0.0.0",
    data_root=Path("/data"),
    yaams_config=None,
    ledger_config=None,
    owa_piggy_config=None,
  )
  # Pointers that couldn't be resolved are commented out so they
  # don't masquerade as real paths.
  assert "# yaams_config:" in body
  assert "# ledger_config:" in body
  assert "# owa_piggy_config:" in body


def test_init_writes_master_config_pointing_at_canonical_yaams(monkeypatch, tmp_path: Path):
  """End-to-end greenfield: pipe 'y' confirmations through, get a
  master config plus a yaams config at the canonical location."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  # Two prompts: continue?, generate yaams config?
  result = CliRunner().invoke(cli, ["init"], input="y\ny\n")
  assert result.exit_code == 0, result.output

  master = tmp_path / "mnem" / "config.yaml"
  yaams_cfg = tmp_path / "yaams" / "config.yaml"
  assert master.is_file()
  assert yaams_cfg.is_file()

  parsed = read_master(master)
  assert parsed["yaams_config"] == str(yaams_cfg)

  yaams_body = yaams_cfg.read_text()
  assert "imessage" in yaams_body
  assert "enabled: true" in yaams_body
  assert "enabled: false" in yaams_body


def test_init_reuses_existing_yaams_config_in_place(monkeypatch, tmp_path: Path):
  """If `~/.config/yaams/config.yaml` already exists, mnem records
  the path in the master and does NOT overwrite the yaams config."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  existing = tmp_path / "yaams" / "config.yaml"
  existing.parent.mkdir(parents=True)
  existing.write_text("# user-curated yaams config\ndb_path: ~/brain/yaams/data.db\n")

  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  result = CliRunner().invoke(cli, ["init"], input="y\n")
  assert result.exit_code == 0, result.output

  # mnem did NOT clobber the existing yaams config.
  assert "user-curated" in existing.read_text()
  # And the master points at it.
  parsed = read_master(tmp_path / "mnem" / "config.yaml")
  assert parsed["yaams_config"] == str(existing)


def test_init_records_ledger_pointer_when_canonical_exists(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  ledger = tmp_path / "cognitive-ledger" / "config.yaml"
  ledger.parent.mkdir(parents=True)
  ledger.write_text("ledger_root: ~/code/ledger\n")
  owa = tmp_path / "owa-piggy" / "profiles.conf"
  owa.parent.mkdir(parents=True)
  owa.write_text('OWA_DEFAULT_PROFILE="swon"\n')

  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  result = CliRunner().invoke(cli, ["init"], input="y\ny\n")
  assert result.exit_code == 0, result.output
  parsed = read_master(tmp_path / "mnem" / "config.yaml")
  assert parsed["ledger_config"] == str(ledger)
  assert parsed["owa_piggy_config"] == str(owa)


def test_init_leaves_ledger_pointer_unset_when_no_canonical(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("MNEM_HOME", str(tmp_path / "data"))
  from mnem.commands import init as init_mod
  monkeypatch.setattr(init_mod, "run_all", _stub_probes)
  monkeypatch.setattr(init_mod, "_which_or_warn", lambda _name: None)
  result = CliRunner().invoke(cli, ["init"], input="y\ny\n")
  assert result.exit_code == 0, result.output
  parsed = read_master(tmp_path / "mnem" / "config.yaml")
  # ledger / owa-piggy pointers should be absent (commented out) since
  # neither canonical file exists.
  assert "ledger_config" not in parsed
  assert "owa_piggy_config" not in parsed
