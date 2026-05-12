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
  # --- YAAMS (Tier 1 raw) ---------------------------------------------
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
  ("promote", "review"): Mapping(
    binary="yaams",
    rewrite=_passthrough(["promote", "review"]),
    description="Review promotion candidates interactively",
  ),
  ("promote", "generate"): Mapping(
    binary="yaams",
    rewrite=_passthrough(["promote", "generate"]),
    description="Generate fresh promotion candidates",
  ),
  ("promote", "list"): Mapping(
    binary="yaams",
    rewrite=_passthrough(["promote", "list"]),
    description="List existing promotion candidates",
  ),
  # --- cognitive-ledger (Tier 2 curated) ------------------------------
  ("ledger", "init"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["init"]),
    description="Bootstrap a new cognitive ledger",
  ),
  ("ledger", "paths"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["paths"]),
    description="Show resolved ledger paths",
  ),
  ("ledger", "query"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["query"]),
    description="Query the curated atomic-notes layer directly",
  ),
  ("ledger", "loops"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["loops"]),
    description="List open loops from the ledger",
  ),
  ("ledger", "notes"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["notes"]),
    description="List ledger notes by type",
  ),
  ("ledger", "context"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["context"]),
    description="Output boot context or build context files",
  ),
  # --- owa-piggy (auth) -----------------------------------------------
  ("auth", "status"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["status"]),
    description="Show M365 auth status (all profiles)",
  ),
  ("auth", "setup"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["setup"]),
    description="Interactive first-time M365 auth setup",
  ),
  ("auth", "reseed"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["reseed"]),
    description="Refresh expired tokens from the Edge sidecar",
  ),
  ("auth", "profiles"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["profiles"]),
    description="List / manage M365 profiles",
  ),
  # --- owa-tools (M365 read/write) ------------------------------------
  ("mail",): Mapping(
    binary="owa-mail",
    rewrite=_passthrough([]),
    description="Outlook mail (messages, send, reply, search, ...)",
  ),
  ("calendar",): Mapping(
    binary="owa-cal",
    rewrite=_passthrough([]),
    description="Outlook calendar (events, create, update, ...)",
  ),
  ("graph",): Mapping(
    binary="owa-graph",
    rewrite=_passthrough([]),
    description="Generic Microsoft Graph CLI (GET/POST/PATCH/DELETE)",
  ),
  ("people",): Mapping(
    binary="owa-people",
    rewrite=_passthrough([]),
    description="People / directory lookup",
  ),
  ("schedule",): Mapping(
    binary="owa-sched",
    rewrite=_passthrough([]),
    description="Free/busy and find-time scheduling helpers",
  ),
  ("drive",): Mapping(
    binary="owa-drive",
    rewrite=_passthrough([]),
    description="OneDrive (ls, get, put, rm, ...)",
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
