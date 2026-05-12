"""Regression test for the passthrough stderr-deadlock.

Before the fix, mnem read stdout to EOF and only then drained
stderr. A child that wrote enough free-text diagnostics to stderr
(progress lines, tqdm output, etc.) before closing stdout filled
the OS pipe buffer (~64KB on macOS, often less on Linux) and
blocked forever. mnem in turn blocked on stdout.

The fix drains stderr concurrently on a background thread.
"""
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest

from mnem.commands.passthrough import _stream_subprocess


def _make_noisy_child(tmp_path: Path, stderr_kb: int) -> list[str]:
  """Return an argv that writes <stderr_kb> KB to stderr, then a
  single JSON line to stdout, then exits 0."""
  script = tmp_path / "noisy.py"
  script.write_text(textwrap.dedent(f"""
    import sys, json
    blob = ("x" * 1024 + "\\n") * {stderr_kb}
    sys.stderr.write(blob)
    sys.stderr.flush()
    sys.stdout.write(json.dumps({{"tool": "noisy", "ok": True}}) + "\\n")
    sys.stdout.flush()
  """))
  return [sys.executable, str(script)]


def test_no_deadlock_with_large_stderr(tmp_path: Path):
  """200KB of stderr before any stdout used to deadlock the
  passthrough. Now it must complete in well under the timeout."""
  argv = _make_noisy_child(tmp_path, stderr_kb=200)
  start = time.monotonic()
  rc, stdout_text, stderr_text = _stream_subprocess(argv)
  elapsed = time.monotonic() - start
  # Generous upper bound; the actual case is sub-second.
  assert elapsed < 10.0, f"deadlock not fixed; took {elapsed:.1f}s"
  assert rc == 0
  assert '"ok": true' in stdout_text
  # All 200KB of stderr captured.
  assert len(stderr_text) >= 200 * 1024


def test_stdout_still_streams_line_by_line(tmp_path: Path):
  """The drain-on-thread refactor must preserve the streaming
  contract: stdout lines arrive in order and aren't swallowed."""
  script = tmp_path / "streaming.py"
  script.write_text(textwrap.dedent("""
    import sys, time
    for i in range(5):
        sys.stdout.write(f'{{"type": "progress", "done": {i}}}\\n')
        sys.stdout.flush()
        sys.stderr.write(f"chatter {i}\\n")
    sys.stdout.write('{"type": "result", "ok": true}\\n')
  """))
  rc, stdout_text, stderr_text = _stream_subprocess(
    [sys.executable, str(script)]
  )
  assert rc == 0
  lines = [ln for ln in stdout_text.splitlines() if ln.strip()]
  assert len(lines) == 6
  assert lines[0].endswith('"done": 0}')
  assert lines[-1] == '{"type": "result", "ok": true}'
  assert "chatter 4" in stderr_text


def test_missing_binary_returns_127(tmp_path: Path):
  rc, stdout_text, stderr_text = _stream_subprocess(
    [str(tmp_path / "definitely-not-on-disk")]
  )
  assert rc == 127
  assert "not on PATH" in stderr_text
