"""Graceful-failure middleware for the mnem router.

Implements the subprocess capture contract from
mnem/CONVENTIONS.md:

- mnem invokes underlying CLIs with --json (machine mode).
- stdout is captured for envelope parsing.
- stderr is captured, run through mnem's own redaction pass, then
  appended to ~/.local/state/mnem/last-error.log.
- The user sees a single redacted one-line summary on stderr;
  --verbose dumps the full captured stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mnem.conventions import redact


def _state_dir() -> Path:
  """``~/.local/state/mnem`` with the standard mode-0700 perms."""
  xdg = os.environ.get("XDG_STATE_HOME")
  base = Path(xdg) if xdg else Path.home() / ".local" / "state"
  d = base / "mnem"
  d.mkdir(parents=True, exist_ok=True, mode=0o700)
  return d


LOG_FILENAME = "last-error.log"
LOG_KEEP = 5


def log_path() -> Path:
  return _state_dir() / LOG_FILENAME


def _rotate(log: Path) -> None:
  """Keep the most recent LOG_KEEP rotations next to the current log."""
  if not log.exists():
    return
  for i in range(LOG_KEEP - 1, 0, -1):
    src = log.with_suffix(f".log.{i}")
    if src.exists():
      src.rename(log.with_suffix(f".log.{i + 1}"))
  log.rename(log.with_suffix(".log.1"))


def write_error_log(*, tool: str, argv: Sequence[str], exit_code: int, stderr_text: str) -> Path:
  """Append a redacted error record to last-error.log; rotate older logs."""
  log = log_path()
  _rotate(log)
  redacted = redact(stderr_text)
  body = (
    f"# mnem subprocess failure\n"
    f"tool: {tool}\n"
    f"argv: {list(argv)}\n"
    f"exit_code: {exit_code}\n"
    f"stderr (redacted):\n{redacted}\n"
  )
  log.write_text(body, encoding="utf-8")
  try:
    log.chmod(0o600)
  except OSError:
    pass
  return log


@dataclass
class SubprocessResult:
  """Outcome of a subprocess invocation."""
  argv: list[str]
  returncode: int
  stdout: str
  stderr: str
  stdout_envelope: dict | None  # parsed top-level JSON if present
  crashed: bool  # True when no parseable JSON came back on stdout

  @property
  def ok(self) -> bool:
    return self.returncode == 0


def parse_stdout(stdout: str) -> dict | None:
  """Parse the final JSON value on stdout.

  Underlying tools emit one of two shapes:

  1. Action commands with --json: NDJSON stream (progress / warning
     / result lines), terminated by a single ``{type:"result", ...}``
     line. The result line is the value we want.
  2. Data commands with --json: a single JSON document, possibly
     pretty-printed across multiple lines.

  Try (1) first by attempting whole-text parse (works for compact
  single-line JSON, common in success/failure envelopes). Fall back
  to last-line parse for NDJSON streams.

  Returns the parsed dict, or None if no JSON could be recovered
  (the failure-handling layer treats that as "tool crashed").
  """
  text = (stdout or "").strip()
  if not text:
    return None
  # Whole-text first: handles pretty-printed multi-line data docs
  # (yaams query --json indents with 2 spaces by default, ledger
  # paths does the same).
  try:
    parsed = json.loads(text)
    if isinstance(parsed, dict):
      return parsed
  except json.JSONDecodeError:
    pass
  # NDJSON streaming: walk back to the last parseable line.
  for line in reversed(text.splitlines()):
    line = line.strip()
    if not line:
      continue
    try:
      parsed = json.loads(line)
      if isinstance(parsed, dict):
        return parsed
    except json.JSONDecodeError:
      continue
  return None


def run_subprocess(
  argv: Sequence[str],
  *,
  tool: str,
  inject_json: bool = True,
  extra_env: dict | None = None,
) -> SubprocessResult:
  """Invoke an underlying CLI and capture its output.

  When ``inject_json`` is True (the default), ``--json`` is appended
  to argv if not already present. mnem always invokes JSON-capable
  underlying commands with --json so the capture contract holds.
  """
  argv_list = list(argv)
  if inject_json and "--json" not in argv_list:
    argv_list.append("--json")
  env = os.environ.copy()
  if extra_env:
    env.update(extra_env)
  try:
    proc = subprocess.run(
      argv_list,
      capture_output=True,
      text=True,
      env=env,
      check=False,
    )
  except FileNotFoundError as exc:
    return SubprocessResult(
      argv=argv_list,
      returncode=127,
      stdout="",
      stderr=f"binary not on PATH: {exc}",
      stdout_envelope=None,
      crashed=True,
    )

  envelope = parse_stdout(proc.stdout)
  crashed = envelope is None and proc.returncode != 0
  result = SubprocessResult(
    argv=argv_list,
    returncode=proc.returncode,
    stdout=proc.stdout,
    stderr=proc.stderr,
    stdout_envelope=envelope,
    crashed=crashed,
  )
  if crashed or (envelope is not None and envelope.get("ok") is False):
    write_error_log(
      tool=tool,
      argv=argv_list,
      exit_code=proc.returncode,
      stderr_text=proc.stderr,
    )
  return result


def one_line_summary(*, tool: str, result: SubprocessResult) -> str:
  """Build the redacted one-line stderr message mnem shows on failure."""
  log = log_path()
  if result.crashed:
    msg = "tool crashed - file bug"
    hint = ""
  elif result.stdout_envelope and result.stdout_envelope.get("error"):
    err = result.stdout_envelope["error"]
    msg = redact(err.get("message", "operation failed"))
    hint_text = err.get("hint")
    hint = f"\n    Fix:  {redact(hint_text)}" if hint_text else ""
  else:
    msg = f"exit {result.returncode}"
    hint = ""
  return f"x {tool}: {msg}{hint}\n    Logs: {log}"
