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
from typing import Callable, Literal, Sequence


_LEDGER_SOURCE_ID = "tier2_ledger"


# JSON injection policy per row.
#
# - "inject": append --json to argv if not already present. Used for
#   tools that expect an explicit machine-mode flag (yaams, ledger).
# - "native": underlying tool emits JSON by default; --json is either
#   unknown or only accepted at the top level. The OWA tools fit here:
#   `owa-mail config --json` rejects --json as an unknown flag. Don't
#   inject.
# - "none": never inject. Used for interactive children (the
#   interactive=True flag also gates stdio capture) and for rewrites
#   that produce the final argv shape themselves (e.g. bare
#   `ledger context` -> `--format json`).
JsonPolicy = Literal["inject", "native", "none"]


@dataclass(frozen=True)
class Mapping:
  """A single translation-table row."""
  binary: str  # underlying binary name (e.g. "yaams")
  rewrite: Callable[[Sequence[str]], list[str]]  # mnem-args -> underlying-args
  description: str  # one-line summary for `mnem hello`
  # Interactive verbs prompt the human directly. mnem must NOT inject
  # --json into their argv (the underlying tool will reject it per
  # CONVENTIONS.md) and must NOT capture stdio - the child needs the
  # real terminal so prompts and TTY tricks work.
  interactive: bool = False
  # See JsonPolicy above. Default "inject" preserves the historical
  # passthrough behavior for yaams/ledger.
  json_policy: JsonPolicy = "inject"


def _passthrough(extra: Sequence[str] = ()) -> Callable[[Sequence[str]], list[str]]:
  """Append mnem-args verbatim to the static command head."""
  head = list(extra)

  def rewrite(args: Sequence[str]) -> list[str]:
    return head + list(args)

  return rewrite


def _query_rewrite(args: Sequence[str]) -> list[str]:
  """`mnem query` is a thin passthrough to `yaams query`.

  Earlier drafts of CONVENTIONS.md described mnem rewriting
  `--tier ledger` into `--source ledger` here. That rewrite became
  unnecessary in Phase 2b when yaams gained native `--tier
  raw|ledger|both` support (the alias rewrite happens inside yaams
  now). Per the router rule "argument mapping allowed, business
  logic forbidden", anything yaams handles natively stays as a
  passthrough.
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
    interactive=True,
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
  # Bare `ledger context` exposes --format boot|identity|json (not
  # --json) at the cognitive-ledger layer. We translate to
  # `context --format json` and mark json_policy=none so passthrough
  # does not append --json on top. Subcommands `context build` and
  # `context profiles` use their own --json natively, so they live on
  # separate rows with the default inject policy. Longest-prefix
  # match in `lookup()` ensures the 3-tuple keys resolve first.
  ("ledger", "context"): Mapping(
    binary="ledger",
    rewrite=lambda a: ["context", "--format", "json", *list(a)],
    description="Output boot context (JSON)",
    json_policy="none",
  ),
  ("ledger", "context", "build"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["context", "build"]),
    description="Build curated context files",
  ),
  ("ledger", "context", "profiles"): Mapping(
    binary="ledger",
    rewrite=_passthrough(["context", "profiles"]),
    description="List ledger context profiles",
  ),
  # --- owa-piggy (auth) -----------------------------------------------
  # owa-piggy is JSON-by-default like the rest of the OWA suite, so we
  # do not inject --json. The shared run_with_output_modes() layer
  # only consumes --json for the top-level --doctor probe.
  ("auth", "status"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["status"]),
    description="Show M365 auth status (all profiles)",
    json_policy="native",
  ),
  ("auth", "setup"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["setup"]),
    description="Interactive first-time M365 auth setup",
    interactive=True,
    json_policy="none",
  ),
  ("auth", "reseed"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["reseed"]),
    description="Refresh expired tokens from the Edge sidecar",
    json_policy="native",
  ),
  ("auth", "profiles"): Mapping(
    binary="owa-piggy",
    rewrite=_passthrough(["profiles"]),
    description="List / manage M365 profiles",
    json_policy="native",
  ),
  # --- owa-tools (M365 read/write) ------------------------------------
  # OWA tools emit JSON by default; their subcommand parsers reject
  # --json as an unknown flag. json_policy="native" keeps the argv
  # clean and unblocks mnem mail/calendar/graph/people/schedule/drive.
  ("mail",): Mapping(
    binary="owa-mail",
    rewrite=_passthrough([]),
    description="Outlook mail (messages, send, reply, search, ...)",
    json_policy="native",
  ),
  ("calendar",): Mapping(
    binary="owa-cal",
    rewrite=_passthrough([]),
    description="Outlook calendar (events, create, update, ...)",
    json_policy="native",
  ),
  ("graph",): Mapping(
    binary="owa-graph",
    rewrite=_passthrough([]),
    description="Generic Microsoft Graph CLI (GET/POST/PATCH/DELETE)",
    json_policy="native",
  ),
  ("people",): Mapping(
    binary="owa-people",
    rewrite=_passthrough([]),
    description="People / directory lookup",
    json_policy="native",
  ),
  ("schedule",): Mapping(
    binary="owa-sched",
    rewrite=_passthrough([]),
    description="Free/busy and find-time scheduling helpers",
    json_policy="native",
  ),
  ("drive",): Mapping(
    binary="owa-drive",
    rewrite=_passthrough([]),
    description="OneDrive (ls, get, put, rm, ...)",
    json_policy="native",
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
