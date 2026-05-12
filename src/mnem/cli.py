"""mnem Click root.

Subcommands:
- hello   - one-screen elevator pitch
- version - mnem version + observed component versions
- doctor  - aggregate health check across the suite
- init    - first-run wizard (interactive; rejects --json)
- query   - passthrough to `yaams query` (with --tier aliasing)
- ingest  - passthrough to `yaams ingest`
- promote - passthrough to `yaams promote <sub>`
- ledger  - passthrough to `ledger <sub>`
- auth    - passthrough to `owa-piggy <sub>`
- mail    - passthrough to `owa-mail`
- calendar - passthrough to `owa-cal`
- graph   - passthrough to `owa-graph`
- people  - passthrough to `owa-people`
- schedule - passthrough to `owa-sched`
- drive   - passthrough to `owa-drive`

Top-level flags: --version (Click default), --doctor, --json,
--verbose. The doctor flag is wired so `mnem --doctor` works for
parity with other binaries in the suite.

First-run hint middleware: subcommands that depend on the yaams DB
(query, ingest, promote review) exit 4 with a clean
``Run: mnem init`` pointer when the user has no mnem config yet.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from mnem import __version__


# --- First-run hint helpers -------------------------------------------------

def _yaams_config_path() -> Path:
  xdg = os.environ.get("XDG_CONFIG_HOME")
  base = Path(xdg) if xdg else Path.home() / ".config"
  return base / "mnem" / "yaams" / "config.yaml"


_VERBS_NEEDING_CONFIG = {
  ("query",),
  ("ingest",),
  ("promote", "review"),
  ("promote", "generate"),
}


def _explicit_config_in_args(args: tuple[str, ...]) -> bool:
  """True iff the user passed --config / --config=... themselves."""
  return any(
    a == "--config" or a.startswith("--config=") for a in args
  )


# Env vars that bypass the first-run guard. Per CONVENTIONS.md the
# direct-CLI / mnem parity invariant requires `YAAMS_CONFIG` (and
# friends) to resolve the same config in both invocation paths; mnem
# must defer to them when set even if its own config doesn't exist.
_CONFIG_ENV_VARS = ("YAAMS_CONFIG", "LEDGER_CONFIG", "OWA_CONFIG", "OWA_PIGGY_CONFIG", "MNEM_CONFIG")


def _ensure_config(verb_args: tuple[str, ...]) -> int | None:
  """Return None if it's OK to proceed; an exit code if mnem should
  bail with a first-run hint."""
  if not verb_args:
    return None
  for prefix in _VERBS_NEEDING_CONFIG:
    if tuple(verb_args[: len(prefix)]) == prefix:
      break
  else:
    return None
  if _explicit_config_in_args(verb_args):
    return None
  if any(os.environ.get(name) for name in _CONFIG_ENV_VARS):
    return None
  cfg = _yaams_config_path()
  if cfg.is_file():
    return None
  click.echo(
    f"x mnem: no mnem config at {cfg}.\n"
    f"    Fix:  mnem init",
    err=True,
  )
  return 4  # EXIT_NOT_FOUND per CONVENTIONS.md


@click.group(
  invoke_without_command=True,
  context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="mnem")
@click.option(
  "--doctor",
  is_flag=True,
  default=False,
  help="Run health check across the suite and exit.",
)
@click.option(
  "--json",
  "as_json_top",
  is_flag=True,
  default=False,
  help="Machine mode (JSON output) for top-level commands.",
)
@click.option(
  "-v",
  "--verbose",
  is_flag=True,
  default=False,
  help="Verbose mode: dump captured stderr from subprocess failures.",
)
@click.pass_context
def cli(ctx: click.Context, doctor: bool, as_json_top: bool, verbose: bool) -> None:
  ctx.ensure_object(dict)
  ctx.obj["json"] = as_json_top
  ctx.obj["verbose"] = verbose
  if doctor:
    from mnem.commands.doctor import run as doctor_run
    ctx.exit(doctor_run(as_json_top))
  if ctx.invoked_subcommand is None:
    from mnem.commands.hello import run as hello_run
    ctx.exit(hello_run(as_json_top))


@cli.command("hello")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.pass_context
def hello_cmd(ctx: click.Context, as_json: bool) -> None:
  from mnem.commands.hello import run
  ctx.exit(run(as_json or ctx.obj.get("json", False)))


@cli.command("version")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.pass_context
def version_cmd(ctx: click.Context, as_json: bool) -> None:
  from mnem.commands.version import run
  ctx.exit(run(as_json or ctx.obj.get("json", False)))


@cli.command("doctor")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.pass_context
def doctor_cmd(ctx: click.Context, as_json: bool) -> None:
  from mnem.commands.doctor import run
  ctx.exit(run(as_json or ctx.obj.get("json", False)))


@cli.command("init")
@click.option(
  "--json",
  "as_json",
  is_flag=True,
  default=False,
  help="(rejected) init is interactive; use `mnem doctor --json` instead.",
)
@click.option(
  "--force",
  is_flag=True,
  default=False,
  help="Overwrite an existing yaams config without prompting.",
)
@click.pass_context
def init_cmd(ctx: click.Context, as_json: bool, force: bool) -> None:
  from mnem.commands.init import run
  ctx.exit(run(as_json or ctx.obj.get("json", False), force=force))


def _make_passthrough(name: str, head: tuple[str, ...]):
  """Generate a Click subcommand that forwards to the passthrough
  module after the first-run hint check."""

  @cli.command(
    name,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
  )
  @click.argument("args", nargs=-1, type=click.UNPROCESSED)
  @click.pass_context
  def _cmd(ctx: click.Context, args: tuple[str, ...]) -> None:
    full = (*head, *args)
    hint = _ensure_config(full)
    if hint is not None:
      ctx.exit(hint)
    from mnem.commands.passthrough import run
    ctx.exit(run(list(full), verbose=ctx.obj.get("verbose", False)))

  _cmd.__doc__ = f"Run `mnem {name}` against the suite."
  return _cmd


# Translation-table-driven Click commands.
query_cmd = _make_passthrough("query", ("query",))
ingest_cmd = _make_passthrough("ingest", ("ingest",))
promote_cmd = _make_passthrough("promote", ("promote",))
ledger_cmd = _make_passthrough("ledger", ("ledger",))
auth_cmd = _make_passthrough("auth", ("auth",))
mail_cmd = _make_passthrough("mail", ("mail",))
calendar_cmd = _make_passthrough("calendar", ("calendar",))
graph_cmd = _make_passthrough("graph", ("graph",))
people_cmd = _make_passthrough("people", ("people",))
schedule_cmd = _make_passthrough("schedule", ("schedule",))
drive_cmd = _make_passthrough("drive", ("drive",))


def main() -> int:
  """Top-level entry. Catches Click usage errors so users get a clean
  one-line message instead of a Python traceback.

  Free-text diagnostics (per CONVENTIONS.md stream routing) go to
  stderr. Exit codes follow Click's defaults: 2 for usage errors, 1
  for everything else.
  """
  try:
    return cli(standalone_mode=False) or 0
  except click.exceptions.UsageError as exc:
    # `mnem --bad-flag`, `mnem hello --does-not-exist`, etc.
    # Click already builds a helpful message; just route it cleanly.
    exc.show(file=sys.stderr)
    return exc.exit_code
  except click.exceptions.Abort:
    # User hit Ctrl-C in an interactive prompt.
    sys.stderr.write("\nAborted.\n")
    return 1
  except click.exceptions.ClickException as exc:
    exc.show(file=sys.stderr)
    return exc.exit_code


if __name__ == "__main__":
  sys.exit(main())
