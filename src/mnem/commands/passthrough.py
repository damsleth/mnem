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
import threading
from typing import Sequence

from mnem.conventions import redact
from mnem.failure import log_path, one_line_summary, parse_stdout, write_error_log
from mnem.router import lookup


def _stream_subprocess(
  argv: Sequence[str],
  *,
  extra_env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
  """Run subprocess; forward stdout lines as they arrive; capture stderr.

  Returns (returncode, captured_stdout, captured_stderr).

  Stderr is drained on a background thread so that a noisy child
  (yaams ingest's tqdm progress, ledger sleep's status text, etc)
  cannot fill the stderr pipe buffer and deadlock the child while
  mnem is still pumping stdout. Without this, a child that writes
  more than ~64KB to stderr before closing stdout will block
  forever.
  """
  env = os.environ.copy()
  if extra_env:
    env.update(extra_env)
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

  stderr_chunks: list[str] = []

  def _drain_stderr() -> None:
    if proc.stderr is None:
      return
    for chunk in proc.stderr:
      stderr_chunks.append(chunk)

  drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
  drain_thread.start()

  stdout_chunks: list[str] = []
  assert proc.stdout is not None
  for line in proc.stdout:
    sys.stdout.write(line)
    sys.stdout.flush()
    stdout_chunks.append(line)

  proc.wait()
  drain_thread.join()
  return proc.returncode, "".join(stdout_chunks), "".join(stderr_chunks)


def _run_interactive(argv: Sequence[str]) -> int:
  """Run an interactive child with the real terminal attached.

  No --json injection, no stdio capture - the child needs the TTY so
  click.prompt / questionary / raw-mode tricks work. We pass stdin /
  stdout / stderr through verbatim and just propagate the exit code.
  """
  try:
    proc = subprocess.run(list(argv), check=False)
  except FileNotFoundError as exc:
    sys.stderr.write(f"x mnem: binary not on PATH: {exc}\n")
    return 127
  return proc.returncode


def run(
  verb_args: Sequence[str],
  *,
  verbose: bool = False,
  top_level_json: bool = False,
  extra_env: dict[str, str] | None = None,
) -> int:
  """Dispatch ``mnem <verb-args>`` through the translation table.

  ``top_level_json`` is the value of ``mnem --json <verb>`` and
  propagates as intent, not as a flag rewrite. Per CONVENTIONS.md
  interactive commands reject --json; we enforce that at the mnem
  layer rather than letting the child fail mysteriously.
  """
  resolved = lookup(verb_args)
  if resolved is None:
    sys.stderr.write(
      f"x mnem: no such verb: {' '.join(verb_args) or '<empty>'}\n"
      f"    Try: mnem hello\n"
    )
    return 1

  mapping, rewritten = resolved
  argv = [mapping.binary, *rewritten]

  if mapping.interactive:
    if top_level_json:
      verb_str = " ".join(verb_args)
      sys.stderr.write(
        f"x mnem: interactive command rejects --json: {verb_str}\n"
        f"    Fix:  drop the top-level --json flag, or run a non-interactive verb\n"
      )
      return 2  # EXIT_USAGE per CONVENTIONS.md
    # No --json injection, no stdio capture. CONVENTIONS.md: interactive
    # commands reject --json; injecting it here would force the
    # underlying tool to exit 1 every time.
    return _run_interactive(argv)

  if mapping.json_policy == "inject" and "--json" not in argv:
    argv.append("--json")

  rc, stdout_text, stderr_text = _stream_subprocess(argv, extra_env=extra_env)

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
