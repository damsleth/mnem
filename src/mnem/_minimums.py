"""Single source of truth for component minimums.

Each entry maps the **package** label used in ``SUITE.md`` and the brew
formula to (a) the minimum version mnem requires, and (b) the binaries
that ship inside that package.

Consumers:
  - ``mnem.commands.version`` probes each binary and renders the
    package minimum alongside.
  - ``tests/test_suite_doc_minimums.py`` parses ``SUITE.md`` and
    asserts the documented values match this dict. Drift fails CI.

Bumping a minimum is a release decision. Update this dict, regenerate
``SUITE.md`` (or hand-sync), and ship.
"""

from __future__ import annotations


PACKAGES: dict[str, dict] = {
  "yaams": {
    "minimum": "0.1.3",
    "binaries": ["yaams"],
  },
  "cognitive-ledger": {
    "minimum": "0.2.3",
    "binaries": ["ledger", "ledger-obsidian", "sheep"],
  },
  "owa-piggy": {
    "minimum": "0.9.0",
    "binaries": ["owa-piggy"],
  },
  "owa-tools": {
    "minimum": "0.1.2",
    "binaries": [
      "owa",
      "owa-cal",
      "owa-mail",
      "owa-graph",
      "owa-doctor",
      "owa-people",
      "owa-sched",
      "owa-drive",
    ],
  },
}


def binary_to_package() -> dict[str, str]:
  """Reverse index: binary name -> package label."""
  out: dict[str, str] = {}
  for pkg, info in PACKAGES.items():
    for binary in info["binaries"]:
      out[binary] = pkg
  return out
