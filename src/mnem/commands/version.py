"""``mnem version`` - mnem's own version + observed component versions.

Output class: data. The reserved-key contract bans a top-level
``ok`` field on success documents; this command emits
``{tool, version, components: {...}}`` instead.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from mnem import __version__
from mnem.failure import run_subprocess


# Which binaries to probe and the formula minimum the mnem release
# pins. (binary, formula_minimum_or_None)
_PROBED = [
  ("yaams", "0.1.2"),
  ("ledger", "0.2.0"),
  ("ledger-obsidian", "0.2.0"),
  ("sheep", "0.2.0"),
  ("owa-piggy", "0.9.0"),
  ("owa", "0.1.1"),
  ("owa-cal", "0.1.1"),
  ("owa-mail", "0.1.1"),
  ("owa-graph", "0.1.1"),
  ("owa-doctor", "0.1.1"),
  ("owa-people", "0.1.1"),
  ("owa-sched", "0.1.1"),
  ("owa-drive", "0.1.1"),
]


def _probe(binary: str) -> dict:
  """Probe `<binary> --doctor --json` and pull the version.

  We use --doctor rather than --version because --version is
  Click-default on most binaries and emits human text. The doctor
  JSON always carries a `version` field.
  """
  result = run_subprocess([binary, "--doctor"], tool=binary, inject_json=True)
  if result.crashed:
    return {"installed": False, "error": "not on PATH or crashed before producing JSON"}
  env = result.stdout_envelope or {}
  return {
    "installed": True,
    "version": env.get("version"),
  }


def _data_doc() -> dict:
  components: dict[str, dict] = {}
  for binary, minimum in _PROBED:
    info = _probe(binary)
    if minimum is not None:
      info["minimum"] = minimum
    components[binary] = info
  return {
    "tool": "mnem",
    "version": __version__,
    "components": components,
  }


def run(as_json: bool, stream: TextIO | None = None) -> int:
  if stream is None:
    stream = sys.stdout
  doc = _data_doc()
  if as_json:
    stream.write(json.dumps(doc, ensure_ascii=False) + "\n")
    stream.flush()
    return 0

  stream.write(f"mnem {doc['version']}\n")
  stream.write("\nComponents:\n")
  for binary, info in doc["components"].items():
    if not info.get("installed"):
      stream.write(f"  {binary:<18} (not installed)\n")
      continue
    minimum = info.get("minimum")
    minimum_str = f" (>= {minimum})" if minimum else ""
    stream.write(f"  {binary:<18} {info.get('version', '?')}{minimum_str}\n")
  stream.flush()
  return 0
