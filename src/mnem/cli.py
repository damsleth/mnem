"""mnem Click root.

Subcommands:
- hello   - one-screen elevator pitch
- version - mnem version + observed component versions
- doctor  - aggregate health check across the suite
- query   - passthrough to `yaams query` (with --tier aliasing)
- ingest  - passthrough to `yaams ingest`
- promote, ledger, mail, calendar, auth: Phase 3b

Top-level flags: --version (Click default), --doctor, --json,
--verbose. The doctor flag is wired so `mnem --doctor` works for
parity with other binaries in the suite.
"""

from __future__ import annotations

import sys

import click

from mnem import __version__


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


@cli.command(
  "query",
  context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def query_cmd(ctx: click.Context, args: tuple[str, ...]) -> None:
  from mnem.commands.passthrough import run
  ctx.exit(run(["query", *args], verbose=ctx.obj.get("verbose", False)))


@cli.command(
  "ingest",
  context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def ingest_cmd(ctx: click.Context, args: tuple[str, ...]) -> None:
  from mnem.commands.passthrough import run
  ctx.exit(run(["ingest", *args], verbose=ctx.obj.get("verbose", False)))


def main() -> int:
  return cli(standalone_mode=False) or 0


if __name__ == "__main__":
  sys.exit(main())
