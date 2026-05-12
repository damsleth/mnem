"""``mnem doctor`` - aggregate health check across the suite.

Output class: data. Fans out to each `<tool> --doctor --json` and
collects findings into one document.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from mnem import __version__
from mnem.failure import run_subprocess


# Order is the report order; mnem first, then tiers, then M365.
_FANOUT = [
  "yaams",
  "ledger",
  "sheep",
  "ledger-obsidian",
  "owa-piggy",
  "owa-cal",
  "owa-mail",
  "owa-graph",
  "owa-people",
  "owa-sched",
  "owa-drive",
  "owa",
]


def _probe(binary: str) -> dict:
  """Probe `<binary> --doctor --json` and return the parsed payload.

  On crash or non-JSON output, synthesises a stub payload that
  preserves the doctor-schema invariants (tool name, findings list).
  """
  result = run_subprocess([binary, "--doctor"], tool=binary, inject_json=True)
  if result.crashed:
    return {
      "tool": binary,
      "version": None,
      "installed": False,
      "findings": [
        {
          "id": "binary_missing",
          "severity": "error",
          "message": "binary not on PATH or crashed before emitting JSON",
          "hint": f"brew install damsleth/tap/{binary} (or check PATH)",
        }
      ],
    }
  env = result.stdout_envelope or {}
  env["installed"] = True
  # Each binary's doctor exit code influenced findings already.
  # Track the raw exit_code for the aggregator's severity rollup.
  env["exit_code"] = result.returncode
  return env


def _aggregate() -> dict:
  components = []
  worst_exit = 0
  for binary in _FANOUT:
    payload = _probe(binary)
    components.append(payload)
    # Aggregate severity from two sources:
    # (1) the subprocess returncode (clamped to the standard set), and
    # (2) the findings list - an error-severity finding always bumps
    # exit to at least 1, even if the binary itself returned 0.
    sub_exit = int(payload.get("exit_code") or 0)
    if not payload.get("installed", False):
      # Missing binary -> user-fixable (install or PATH); not the raw
      # FileNotFoundError exit (127).
      sub_exit = 1
    severities = {f.get("severity") for f in (payload.get("findings") or [])}
    if "error" in severities:
      sub_exit = max(sub_exit, 1)
    worst_exit = max(worst_exit, sub_exit)
  return {
    "tool": "mnem",
    "version": __version__,
    "components": components,
    "_exit_code": worst_exit,
  }


def run(as_json: bool, stream: TextIO | None = None) -> int:
  if stream is None:
    stream = sys.stdout
  doc = _aggregate()
  exit_code = int(doc.pop("_exit_code", 0))
  if as_json:
    stream.write(json.dumps(doc, ensure_ascii=False) + "\n")
    stream.flush()
    return exit_code

  stream.write(f"mnem doctor (v{doc['version']})\n")
  for comp in doc["components"]:
    name = comp["tool"]
    if not comp.get("installed"):
      stream.write(f"  {name:<18}  - not installed\n")
      continue
    findings = comp.get("findings") or []
    if not findings:
      stream.write(f"  {name:<18}  ok\n")
      continue
    severities = {f["severity"] for f in findings}
    if "error" in severities:
      mark = "x"
    elif "warning" in severities:
      mark = "!"
    else:
      mark = "."
    stream.write(f"  {name:<18}  {mark} {len(findings)} finding(s)\n")
    for f in findings:
      hint = f"  hint: {f['hint']}" if f.get("hint") else ""
      stream.write(f"    - [{f['severity']}] {f['id']}: {f['message']}{hint}\n")
  stream.flush()
  return exit_code
