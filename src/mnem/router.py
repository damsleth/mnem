"""Translation table from ``mnem <verb>`` to ``<underlying-tool> <args>``.

The router rule: argument mapping (flag rename, subcommand rename,
default-value injection) is allowed; business logic is not. If a
mapping needs more than rewriting argv, the logic belongs in the
underlying tool first.

`mnem doctor` and `mnem version` compose multiple tools and live in
the command modules rather than the table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


_LEDGER_SOURCE_ID = "tier2_ledger"


@dataclass(frozen=True)
class Mapping:
  """A single translation-table row."""
  binary: str  # underlying binary name (e.g. "yaams")
  rewrite: Callable[[Sequence[str]], list[str]]  # mnem-args -> underlying-args
  description: str  # one-line summary for `mnem hello`


def _passthrough(extra: Sequence[str] = ()) -> Callable[[Sequence[str]], list[str]]:
  """Append mnem-args verbatim to the static command head."""
  head = list(extra)

  def rewrite(args: Sequence[str]) -> list[str]:
    return head + list(args)

  return rewrite


def _query_rewrite(args: Sequence[str]) -> list[str]:
  """`mnem query` is `yaams query` with --tier ledger -> --source ledger.

  yaams already accepts both, but the alias is documented here so the
  translation table is the single source of truth for what mnem
  rewrites.
  """
  return ["query", *list(args)]


# Keep the table flat. One row per mnem verb. Subcommand-shaped verbs
# (e.g. `mnem promote review`) match by exact head and forward the
# tail verbatim.
TABLE: dict[tuple[str, ...], Mapping] = {
  ("ingest",): Mapping(
    binary="yaams",
    rewrite=_passthrough(["ingest"]),
    description="Ingest all configured sources into YAAMS",
  ),
  ("query",): Mapping(
    binary="yaams",
    rewrite=_query_rewrite,
    description="Query the suite (Tier 1 raw + Tier 2 curated)",
  ),
}


def lookup(args: Sequence[str]) -> tuple[Mapping, list[str]] | None:
  """Resolve a mnem argv into (mapping, rewritten-argv).

  Returns None if no mapping matches the head.
  """
  args = list(args)
  if not args:
    return None
  # Try longest prefix match first. Today every mnem verb is a
  # single token, but `mnem promote review` etc will arrive in 3b.
  for n in range(min(len(args), 3), 0, -1):
    head = tuple(args[:n])
    mapping = TABLE.get(head)
    if mapping is not None:
      tail = args[n:]
      rewritten = mapping.rewrite(tail)
      return mapping, rewritten
  return None


def verbs() -> list[tuple[str, str, str]]:
  """Return (mnem-verb, binary, description) rows for `mnem hello`."""
  return [
    (" ".join(verb), m.binary, m.description)
    for verb, m in TABLE.items()
  ]
