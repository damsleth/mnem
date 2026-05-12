"""Usage-error paths must emit a one-line stderr message, not a
Python traceback.

Click is invoked with `standalone_mode=False` so the router can
control exit codes; `main()` is the seam that turns Click's
exceptions into clean stderr output with the right exit code.
"""
from __future__ import annotations

import subprocess
import sys


def _run(*args):
  return subprocess.run(
    [sys.executable, "-m", "mnem", *args],
    capture_output=True, text=True,
  )


def test_unknown_option_exits_2_with_friendly_stderr():
  result = _run("--bad-flag-that-does-not-exist")
  assert result.returncode == 2
  assert "Traceback" not in result.stderr
  assert "No such option" in result.stderr
  # Nothing structured leaks to stdout.
  assert result.stdout == ""


def test_unknown_subcommand_exits_2_with_friendly_stderr():
  result = _run("definitely-not-a-real-verb")
  assert result.returncode == 2
  assert "Traceback" not in result.stderr
  # Click's standard message is "No such command".
  assert "No such command" in result.stderr or "no such verb" in result.stderr.lower()


def test_unknown_option_on_subcommand_exits_2():
  result = _run("hello", "--no-such-flag")
  assert result.returncode == 2
  assert "Traceback" not in result.stderr
  assert "No such option" in result.stderr or "no such" in result.stderr.lower()
