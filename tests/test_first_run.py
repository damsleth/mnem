"""First-run hint middleware tests.

When the user has no mnem config yet, the verbs that touch the
yaams DB exit 4 with a clean ``Run: mnem init`` pointer instead of
forwarding to yaams (which would crash on the missing config).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from mnem.cli import _VERBS_NEEDING_CONFIG, _ensure_config, cli


def test_verbs_needing_config_includes_phase3a_verbs():
  assert ("query",) in _VERBS_NEEDING_CONFIG
  assert ("ingest",) in _VERBS_NEEDING_CONFIG
  assert ("promote", "review") in _VERBS_NEEDING_CONFIG


def test_ensure_config_returns_none_for_unrelated_verbs(monkeypatch, tmp_path: Path):
  # auth status doesn't need yaams config.
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  assert _ensure_config(("auth", "status")) is None
  assert _ensure_config(("hello",)) is None
  assert _ensure_config(()) is None


def test_ensure_config_returns_exit_4_when_config_missing(monkeypatch, tmp_path: Path, capsys):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  code = _ensure_config(("query",))
  assert code == 4
  err = capsys.readouterr().err
  assert "mnem init" in err


def test_ensure_config_returns_none_when_config_exists(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  cfg = tmp_path / "mnem" / "config.yaml"
  cfg.parent.mkdir(parents=True)
  cfg.write_text("version: 1\nyaams_config: /tmp/x.yaml\n")
  assert _ensure_config(("query",)) is None


def test_ensure_config_bypasses_when_user_passes_explicit_config(monkeypatch, tmp_path: Path):
  """`mnem query --config /elsewhere/cfg.yaml` should NOT trigger the
  hint, since the user is explicitly opting out of the default."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  assert _ensure_config(("query", "--config", "/elsewhere.yaml")) is None
  assert _ensure_config(("query", "--config=/elsewhere.yaml")) is None


def test_ensure_config_bypasses_when_yaams_config_env_set(monkeypatch, tmp_path: Path):
  """Parity invariant from CONVENTIONS.md: setting YAAMS_CONFIG must
  make `yaams query` and `mnem query` resolve to the same config.
  mnem's first-run guard must defer to the env var the same way
  yaams does."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("YAAMS_CONFIG", "/elsewhere/cfg.yaml")
  assert _ensure_config(("query", "anything")) is None
  assert _ensure_config(("ingest",)) is None


def test_ensure_config_does_not_bypass_for_unrelated_env_vars(monkeypatch, tmp_path: Path):
  """LEDGER_CONFIG / OWA_CONFIG / OWA_PIGGY_CONFIG are unrelated to
  YAAMS-backed verbs. Setting them must NOT skip the first-run hint
  (Plan 02 / review F3). Pre-Plan-02 mnem would bypass on any of
  these and let the user crash on the missing yaams config one
  layer down."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  monkeypatch.delenv("MNEM_CONFIG", raising=False)
  for var in ("LEDGER_CONFIG", "OWA_CONFIG", "OWA_PIGGY_CONFIG"):
    monkeypatch.setenv(var, "/elsewhere/cfg.yaml")
    assert _ensure_config(("query",)) == 4, var
    assert _ensure_config(("ingest",)) == 4, var
    monkeypatch.delenv(var, raising=False)


def test_ensure_config_bypasses_when_mnem_config_env_set(monkeypatch, tmp_path: Path):
  """MNEM_CONFIG is the suite-wide override; it should still bypass."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  monkeypatch.setenv("MNEM_CONFIG", "/elsewhere/cfg.yaml")
  assert _ensure_config(("query",)) is None


def test_ensure_config_still_fires_when_no_env_var_and_no_explicit_config(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  monkeypatch.delenv("LEDGER_CONFIG", raising=False)
  monkeypatch.delenv("OWA_CONFIG", raising=False)
  monkeypatch.delenv("OWA_PIGGY_CONFIG", raising=False)
  monkeypatch.delenv("MNEM_CONFIG", raising=False)
  assert _ensure_config(("query",)) == 4


def test_ensure_config_fires_on_promote_review(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  assert _ensure_config(("promote", "review")) == 4
  # And on promote generate.
  assert _ensure_config(("promote", "generate")) == 4
  # But NOT on promote list (that's a read-only data command).
  assert _ensure_config(("promote", "list")) is None


# --- Integration: cli surface --------------------------------------------

def test_query_without_config_exits_4(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  result = CliRunner().invoke(cli, ["query", "anything"])
  assert result.exit_code == 4


def test_ingest_without_config_exits_4(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  result = CliRunner().invoke(cli, ["ingest"])
  assert result.exit_code == 4


def test_auth_status_does_not_need_config(monkeypatch, tmp_path: Path):
  """auth status routes to owa-piggy which has its own config.
  mnem should NOT block it on the missing mnem config."""
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  result = CliRunner().invoke(cli, ["auth", "status"])
  # The passthrough may fail (owa-piggy not on PATH in test env),
  # but we just want to confirm the first-run middleware didn't
  # intercept.
  assert result.exit_code != 4 or "mnem init" not in (result.stderr_bytes or b"").decode("utf-8", "ignore")
