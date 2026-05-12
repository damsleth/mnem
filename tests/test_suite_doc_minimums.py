"""SUITE.md must declare the same minimums as ``mnem._minimums.PACKAGES``.

The fenced block under "mnem ... requires:" is the human-facing copy of
the dict. This test parses it and asserts each ``<pkg> >= <version>``
row matches the source of truth. Drift = failure.
"""

from __future__ import annotations

import re
from pathlib import Path

from mnem._minimums import PACKAGES


REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_MD = REPO_ROOT / "SUITE.md"

# Matches lines like "  yaams >= 0.1.3" inside the fenced block.
_ROW_RE = re.compile(r"^\s*([a-zA-Z0-9_-]+)\s*>=\s*([0-9][0-9A-Za-z.+-]*)\s*$")


def _parse_minimums_block(text: str) -> dict[str, str]:
  """Find the fenced block that starts with 'mnem ... requires:' and
  return the {package: version} rows it declares.
  """
  lines = text.splitlines()
  in_block = False
  found_header = False
  rows: dict[str, str] = {}
  for line in lines:
    stripped = line.strip()
    if stripped.startswith("```"):
      if in_block:
        # Closing fence: stop if we already found our header.
        if found_header:
          break
        in_block = False
        found_header = False
        continue
      in_block = True
      found_header = False
      continue
    if not in_block:
      continue
    if "requires:" in stripped and stripped.startswith("mnem"):
      found_header = True
      continue
    if not found_header:
      continue
    m = _ROW_RE.match(line)
    if m:
      rows[m.group(1)] = m.group(2)
  return rows


def test_suite_md_minimums_match_source_of_truth():
  text = SUITE_MD.read_text(encoding="utf-8")
  documented = _parse_minimums_block(text)

  assert documented, "could not find the 'mnem ... requires:' minimums block in SUITE.md"

  expected = {pkg: info["minimum"] for pkg, info in PACKAGES.items()}

  # Every package in PACKAGES must appear in SUITE.md with the same version.
  for pkg, version in expected.items():
    assert pkg in documented, (
      f"SUITE.md minimums block missing package {pkg!r}; "
      f"add '{pkg} >= {version}' to keep docs in sync with _minimums.py"
    )
    assert documented[pkg] == version, (
      f"SUITE.md says {pkg} >= {documented[pkg]} but _minimums.PACKAGES "
      f"says {version}. Update one to match the other."
    )

  # And the doc must not declare extra packages we don't know about.
  extras = set(documented) - set(expected)
  assert not extras, (
    f"SUITE.md minimums block lists packages not in _minimums.PACKAGES: {sorted(extras)}"
  )
