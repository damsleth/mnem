"""``mnem version`` - mnem's own version + observed component versions.

Output class: data. The reserved-key contract bans a top-level
``ok`` field on success documents; this command emits
``{tool, version, components: {...}, packages: {...}}`` instead.

The set of probed binaries and their package minimums is derived from
``mnem._minimums.PACKAGES`` so there is exactly one source of truth.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from mnem import __version__
from mnem._minimums import PACKAGES
from mnem.failure import run_subprocess


def _probed_binaries() -> list[tuple[str, str, str]]:
  """Flatten PACKAGES to (binary, package, package_minimum) rows."""
  rows: list[tuple[str, str, str]] = []
  for pkg, info in PACKAGES.items():
    minimum = info["minimum"]
    for binary in info["binaries"]:
      rows.append((binary, pkg, minimum))
  return rows


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
  for binary, pkg, minimum in _probed_binaries():
    info = _probe(binary)
    info["minimum"] = minimum
    info["package"] = pkg
    components[binary] = info

  packages: dict[str, dict] = {}
  for pkg, info in PACKAGES.items():
    packages[pkg] = {
      "minimum": info["minimum"],
      "binaries": list(info["binaries"]),
    }

  return {
    "tool": "mnem",
    "version": __version__,
    "components": components,
    "packages": packages,
  }


def run(as_json: bool, stream: TextIO | None = None) -> int:
  out: TextIO = stream if stream is not None else sys.stdout
  doc = _data_doc()
  if as_json:
    out.write(json.dumps(doc, ensure_ascii=False) + "\n")
    out.flush()
    return 0

  out.write(f"mnem {doc['version']}\n")
  out.write("\nPackages:\n")
  for pkg, pkg_info in doc["packages"].items():
    out.write(f"  {pkg} (>= {pkg_info['minimum']})\n")
    for binary in pkg_info["binaries"]:
      info = doc["components"].get(binary, {})
      if not info.get("installed"):
        out.write(f"    {binary:<18} (not installed)\n")
        continue
      out.write(f"    {binary:<18} {info.get('version', '?')}\n")
  out.flush()
  return 0
