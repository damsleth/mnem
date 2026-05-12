"""Tests for the graceful-failure middleware."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mnem.failure import (
  LOG_FILENAME,
  log_path,
  parse_stdout,
  run_subprocess,
  write_error_log,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
  """Redirect XDG_STATE_HOME so log writes don't touch the real ~/."""
  monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def test_parse_stdout_picks_last_json_line():
  raw = (
    '{"type":"progress","done":1}\n'
    '{"type":"progress","done":2}\n'
    '{"type":"result","ok":true,"command":"x"}\n'
  )
  payload = parse_stdout(raw)
  assert payload["type"] == "result"


def test_parse_stdout_handles_data_doc():
  payload = parse_stdout('{"results": [], "query": "x"}\n')
  assert payload["query"] == "x"


def test_parse_stdout_returns_none_on_empty():
  assert parse_stdout("") is None
  assert parse_stdout("   ") is None


def test_parse_stdout_returns_none_on_garbage():
  assert parse_stdout("not json at all\nstill not json") is None


def test_write_error_log_creates_file(tmp_path: Path):
  log = write_error_log(
    tool="yaams",
    argv=["yaams", "ingest", "--json"],
    exit_code=1,
    stderr_text="Traceback (most recent call last):\n  ...\nError: boom\n",
  )
  assert log.exists()
  body = log.read_text()
  assert "tool: yaams" in body
  assert "exit_code: 1" in body
  assert "Error: boom" in body


def test_write_error_log_redacts_secrets(tmp_path: Path):
  log = write_error_log(
    tool="owa-piggy",
    argv=["owa-piggy", "reseed", "--json"],
    exit_code=1,
    stderr_text='Authorization: Bearer CANARY_SECRET_xxxx_xyz_abc_def_ghi_jkl\n',
  )
  body = log.read_text()
  assert "CANARY_SECRET_xxxx_xyz_abc_def_ghi_jkl" not in body
  assert "Bearer <redacted>" in body


def test_write_error_log_rotates(tmp_path: Path):
  for i in range(3):
    write_error_log(
      tool="yaams",
      argv=["yaams"],
      exit_code=i + 1,
      stderr_text=f"run {i}",
    )
  log = log_path()
  rot1 = log.with_suffix(".log.1")
  rot2 = log.with_suffix(".log.2")
  assert log.exists()
  assert rot1.exists()
  assert rot2.exists()
  # Newest is in `last-error.log`; older rotations have higher
  # numbered suffixes.
  assert "run 2" in log.read_text()
  assert "run 1" in rot1.read_text()


def test_log_file_mode_is_0600(tmp_path: Path):
  log = write_error_log(tool="x", argv=["x"], exit_code=1, stderr_text="x")
  mode = os.stat(log).st_mode & 0o777
  assert mode == 0o600, oct(mode)


def test_run_subprocess_missing_binary_returns_crashed():
  result = run_subprocess(
    ["__definitely-not-a-real-binary-xyz__"],
    tool="__definitely-not-a-real-binary-xyz__",
  )
  assert result.crashed
  assert result.returncode == 127
  assert "not on PATH" in result.stderr


def test_run_subprocess_injects_json_flag():
  """The capture contract: mnem always passes --json to JSON-capable
  CLIs unless one is already present."""
  # Use python -c as the "underlying tool" so we can observe what
  # arguments it sees.
  result = run_subprocess(
    [
      "python",
      "-c",
      'import sys, json; print(json.dumps({"args": sys.argv[1:]}))',
      "ingest",
    ],
    tool="python",
    inject_json=True,
  )
  assert result.returncode == 0
  payload = result.stdout_envelope
  assert payload is not None
  assert "--json" in payload["args"]


def test_run_subprocess_does_not_double_inject_json():
  result = run_subprocess(
    [
      "python",
      "-c",
      'import sys, json; print(json.dumps({"args": sys.argv[1:]}))',
      "ingest",
      "--json",
    ],
    tool="python",
    inject_json=True,
  )
  payload = result.stdout_envelope
  assert payload["args"].count("--json") == 1


def test_run_subprocess_skip_inject_when_false():
  result = run_subprocess(
    [
      "python",
      "-c",
      'import sys, json; print(json.dumps({"args": sys.argv[1:]}))',
      "ingest",
    ],
    tool="python",
    inject_json=False,
  )
  assert "--json" not in result.stdout_envelope["args"]


def test_log_path_under_xdg_state_home(tmp_path: Path):
  assert log_path() == tmp_path / "mnem" / LOG_FILENAME
