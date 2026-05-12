"""mnem-side YAAMS_CONFIG fallback (Plan 05B / review F2 Part B).

When `mnem init` writes ``$XDG_CONFIG_HOME/mnem/yaams/config.yaml``
and the user has not set ``YAAMS_CONFIG``, mnem forwards the path
to yaams-backed child processes via the env var. This unblocks
first-day flow even when the installed yaams build does not yet
search the suite-shared config root.

Contract:
- Inject only for yaams-backed routes.
- Never override a user-set ``YAAMS_CONFIG``.
- Never inject when the user passes ``--config`` explicitly.
- Never inject when the mnem yaams config does not exist on disk.
"""
from __future__ import annotations

from pathlib import Path

from mnem.cli import _yaams_config_env


def _make_cfg(tmp_path: Path) -> Path:
  cfg = tmp_path / "mnem" / "yaams" / "config.yaml"
  cfg.parent.mkdir(parents=True)
  cfg.write_text("db_path: /tmp/x.db\n")
  return cfg


def test_injects_yaams_config_for_query(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  cfg = _make_cfg(tmp_path)
  env = _yaams_config_env(("query", "anything"))
  assert env == {"YAAMS_CONFIG": str(cfg)}


def test_injects_for_ingest_and_promote_review(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  cfg = _make_cfg(tmp_path)
  for verb in (("ingest",), ("promote", "review"), ("promote", "generate"), ("promote", "list")):
    assert _yaams_config_env(verb) == {"YAAMS_CONFIG": str(cfg)}, verb


def test_does_not_inject_for_non_yaams_routes(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  _make_cfg(tmp_path)
  # ledger.*, auth.*, mail.*, calendar.*, ... should all return {}.
  for verb in (
    ("ledger", "paths"), ("ledger", "context"),
    ("auth", "status"), ("auth", "profiles"),
    ("mail", "config"), ("calendar", "profiles"),
    ("graph", "schema"), ("drive", "ls"),
  ):
    assert _yaams_config_env(verb) == {}, verb


def test_never_overrides_user_set_yaams_config(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.setenv("YAAMS_CONFIG", "/users/private/cfg.yaml")
  _make_cfg(tmp_path)
  assert _yaams_config_env(("query", "x")) == {}


def test_does_not_inject_when_user_passes_explicit_config(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  _make_cfg(tmp_path)
  assert _yaams_config_env(("query", "--config", "/elsewhere.yaml")) == {}
  assert _yaams_config_env(("query", "--config=/elsewhere.yaml")) == {}


def test_does_not_inject_when_mnem_config_missing(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  monkeypatch.delenv("YAAMS_CONFIG", raising=False)
  # No _make_cfg() call - config doesn't exist on disk.
  assert _yaams_config_env(("query", "x")) == {}


def test_passthrough_run_forwards_extra_env(monkeypatch):
  """End-to-end: passthrough.run threads extra_env through to the
  child subprocess via _stream_subprocess."""
  from mnem.commands import passthrough
  captured: dict[str, object] = {}

  def _fake(argv, *, extra_env=None):
    captured["argv"] = list(argv)
    captured["extra_env"] = extra_env
    return 0, '{"tool":"yaams","ok":true}\n', ""

  monkeypatch.setattr(passthrough, "_stream_subprocess", _fake)
  passthrough.run(
    ["query", "--config", "/tmp/x.yaml", "anything"],
    extra_env={"YAAMS_CONFIG": "/mnem/cfg.yaml"},
  )
  assert captured["extra_env"] == {"YAAMS_CONFIG": "/mnem/cfg.yaml"}


def test_stream_subprocess_merges_extra_env_into_child(tmp_path: Path):
  """Unit check that the env actually reaches the child."""
  from mnem.commands import passthrough
  import sys
  script = tmp_path / "show_env.py"
  script.write_text(
    "import os, sys\n"
    "sys.stdout.write(os.environ.get('FOO', '<unset>'))\n"
  )
  rc, out, _err = passthrough._stream_subprocess(
    [sys.executable, str(script)],
    extra_env={"FOO": "bar"},
  )
  assert rc == 0
  assert out.strip() == "bar"
