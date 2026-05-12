"""``mnem hello`` - the one-screen elevator pitch.

Output class: data. Runs without any config; safe on a fresh
install before anything is wired up. Emits JSON on stdout under
--json, a human banner otherwise.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from mnem import __version__
from mnem.router import verbs


# Static verbs that ship in 3a beyond the translation table.
_BUILTIN_VERBS = [
  ("hello", "mnem", "Show this elevator pitch"),
  ("version", "mnem", "Show mnem version and observed component versions"),
  ("doctor", "mnem", "Run health checks across the whole suite"),
]


def _all_verbs() -> list[tuple[str, str, str]]:
  return _BUILTIN_VERBS + verbs()


def _data_doc() -> dict:
  return {
    "tool": "mnem",
    "version": __version__,
    "tagline": "Local-first memory suite for AI agents.",
    "verbs": [
      {"verb": verb, "binary": binary, "description": desc}
      for (verb, binary, desc) in _all_verbs()
    ],
    "next_steps": [
      "mnem doctor",
      "mnem query \"<question>\"",
      "mnem ingest",
    ],
  }


def run(as_json: bool, stream: TextIO | None = None) -> int:
  if stream is None:
    stream = sys.stdout
  if as_json:
    stream.write(json.dumps(_data_doc(), ensure_ascii=False) + "\n")
    stream.flush()
    return 0

  doc = _data_doc()
  stream.write(f"mnem v{doc['version']} - {doc['tagline']}\n\n")
  stream.write("Verbs:\n")
  width = max(len(v) for (v, _, _) in doc["verbs"] if isinstance(v, str)) if doc["verbs"] else 0
  for entry in doc["verbs"]:
    verb = entry["verb"]
    desc = entry["description"]
    stream.write(f"  {verb:<{width}}  {desc}\n")
  stream.write("\nNext steps:\n")
  for cmd in doc["next_steps"]:
    stream.write(f"  $ {cmd}\n")
  stream.flush()
  return 0
