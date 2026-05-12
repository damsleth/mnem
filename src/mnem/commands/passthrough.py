"""Generic passthrough handler for mnem verbs that route to underlying tools.

Used by `mnem query` and `mnem ingest`. The router translates the
mnem-side argv to the underlying-tool argv; this module:

1. Invokes the subprocess with stdout/stderr captured.
2. For action commands streaming NDJSON: forwards every line to
   stdout as it arrives (preserving the streaming schema).
3. For data commands: emits the captured stdout verbatim.
4. On failure: emits a redacted one-line summary on stderr,
   appends the captured stderr to ~/.local/state/mnem/last-error.log
   through mnem's own redactor, and exits with the underlying
   tool's exit code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Sequence

from mnem.conventions import redact
from mnem.failure import log_path, one_line_summary, parse_stdout, write_error_log
from mnem.router import lookup


def _stream_subprocess(argv: Sequence[str]) -> tuple[int, str, str]:
  """Run subprocess; forward stdout lines as they arrive; capture stderr.

  Returns (returncode, captured_stdout, captured_stderr).
  """
  env = os.environ.copy()
  try:
    proc = subprocess.Popen(
      list(argv),
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
      env=env,
    )
  except FileNotFoundError as exc:
    return 127, "", f"binary not on PATH: {exc}"

  stdout_chunks: list[str] = []
  assert proc.stdout is not None
  for line in proc.stdout:
    sys.stdout.write(line)
    sys.stdout.flush()
    stdout_chunks.append(line)
  stderr_text = ""
  if proc.stderr is not None:
    stderr_text = proc.stderr.read()
  proc.wait()
  return proc.returncode, "".join(stdout_chunks), stderr_text


def run(verb_args: Sequence[str], *, verbose: bool = False) -> int:
  """Dispatch ``mnem <verb-args>`` through the translation table."""
  resolved = lookup(verb_args)
  if resolved is None:
    sys.stderr.write(
      f"x mnem: no such verb: {' '.join(verb_args) or '<empty>'}\n"
      f"    Try: mnem hello\n"
    )
    return 1

  mapping, rewritten = resolved
  argv = [mapping.binary, *rewritten]
  if "--json" not in argv:
    argv.append("--json")

  rc, stdout_text, stderr_text = _stream_subprocess(argv)

  envelope = parse_stdout(stdout_text)
  crashed = envelope is None and rc != 0
  failed = crashed or rc != 0 or (envelope is not None and envelope.get("ok") is False)

  if failed:
    log = write_error_log(
      tool=mapping.binary,
      argv=argv,
      exit_code=rc,
      stderr_text=stderr_text,
    )
    if envelope and envelope.get("error"):
      err = envelope["error"]
      msg = redact(err.get("message", "operation failed"))
      hint_text = err.get("hint")
      hint = f"\n    Fix:  {redact(hint_text)}" if hint_text else ""
      sys.stderr.write(f"x {mapping.binary}: {msg}{hint}\n    Logs: {log}\n")
    elif crashed:
      sys.stderr.write(
        f"x {mapping.binary}: tool crashed - file bug\n    Logs: {log}\n"
      )
    else:
      sys.stderr.write(
        f"x {mapping.binary}: exit {rc}\n    Logs: {log}\n"
      )
    if verbose and stderr_text:
      sys.stderr.write("--- captured stderr (redacted) ---\n")
      sys.stderr.write(redact(stderr_text))
      if not stderr_text.endswith("\n"):
        sys.stderr.write("\n")

  return rc
