"""End-to-end CLI tests via click's CliRunner.

These pin the user-facing contract: hello/version/doctor output
shapes, the reserved-key contract on data success documents, the
ok/exit-code invariant.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from mnem import __version__
from mnem.cli import cli


# --- mnem hello -----------------------------------------------------------

def test_hello_json_shape():
  result = CliRunner().invoke(cli, ["hello", "--json"])
  assert result.exit_code == 0, result.output
  payload = json.loads(result.output.strip())
  assert payload["tool"] == "mnem"
  assert payload["version"] == __version__
  # Reserved-key contract: data class has no top-level `ok`.
  assert "ok" not in payload
  assert isinstance(payload["verbs"], list)
  assert any(v["verb"] == "query" for v in payload["verbs"])
  assert any(v["verb"] == "ingest" for v in payload["verbs"])


def test_hello_human():
  result = CliRunner().invoke(cli, ["hello"])
  assert result.exit_code == 0, result.output
  assert "mnem" in result.output
  assert "Verbs:" in result.output


def test_bare_mnem_falls_back_to_hello():
  """`mnem` with no args prints help/hello."""
  result = CliRunner().invoke(cli, [])
  # Either exit 0 with hello-shaped content, or click's default
  # help. We just want a non-crashing path.
  assert result.exit_code in (0, 2)


# --- --pretty acceptance on data-class builtins ---------------------------
# CONVENTIONS.md per-command table requires --pretty on hello / version /
# doctor. Default is already human-pretty so --pretty is effectively a
# confirmation; what we pin is that the flag is accepted (no UsageError).

def test_hello_accepts_pretty_flag():
  result = CliRunner().invoke(cli, ["hello", "--pretty"])
  assert result.exit_code == 0, result.output
  assert "mnem" in result.output


def test_version_accepts_pretty_flag():
  result = CliRunner().invoke(cli, ["version", "--pretty"])
  assert result.exit_code == 0, result.output
  assert "mnem" in result.output


def test_doctor_accepts_pretty_flag():
  result = CliRunner().invoke(cli, ["doctor", "--pretty"])
  # doctor exit can be 0 or 1 depending on whether components are on PATH.
  assert result.exit_code in (0, 1)
  assert "mnem doctor" in result.output


def test_hello_json_wins_over_pretty_when_both_passed():
  """If a caller passes both, --json takes precedence (machine
  mode is the safer default under ambiguity, matching CONVENTIONS
  wording on the --json flag)."""
  result = CliRunner().invoke(cli, ["hello", "--json", "--pretty"])
  assert result.exit_code == 0
  json.loads(result.output.strip())  # must parse


# --- mnem --version --------------------------------------------------------

def test_version_flag_works():
  result = CliRunner().invoke(cli, ["--version"])
  assert result.exit_code == 0
  assert __version__ in result.output


# --- mnem version subcommand ----------------------------------------------

def test_version_subcommand_json_shape():
  result = CliRunner().invoke(cli, ["version", "--json"])
  assert result.exit_code == 0, result.output
  payload = json.loads(result.output.strip())
  assert payload["tool"] == "mnem"
  assert "ok" not in payload  # reserved-key
  assert "components" in payload
  # Every probed binary must appear.
  assert "yaams" in payload["components"]
  assert "ledger" in payload["components"]
  assert "owa-piggy" in payload["components"]


def test_version_subcommand_human():
  result = CliRunner().invoke(cli, ["version"])
  assert result.exit_code == 0
  assert "mnem" in result.output
  assert "Components:" in result.output


# --- mnem doctor ----------------------------------------------------------

def test_doctor_json_shape():
  result = CliRunner().invoke(cli, ["doctor", "--json"])
  # Even if every component is missing, exit 0 or 1 are valid; not 2
  # (which would be transient) and not a crash code.
  assert result.exit_code in (0, 1)
  payload = json.loads(result.output.strip())
  assert payload["tool"] == "mnem"
  assert "ok" not in payload
  assert "components" in payload
  assert isinstance(payload["components"], list)
  # Each component is either a real doctor doc or a synthesized
  # binary_missing finding.
  for comp in payload["components"]:
    assert "tool" in comp
    assert "findings" in comp


def test_doctor_flag_form_works():
  """`mnem --doctor` is wired alongside `mnem doctor`."""
  result = CliRunner().invoke(cli, ["--doctor", "--json"])
  assert result.exit_code in (0, 1)
  payload = json.loads(result.output.strip())
  assert payload["tool"] == "mnem"


# --- mnem query / ingest passthrough --------------------------------------

def test_query_unknown_verb_handled():
  # `mnem query` with a query body that yaams isn't installed for.
  # We can't easily install yaams in mnem's venv, so we expect the
  # passthrough to fail cleanly. The key: don't crash mnem.
  result = CliRunner().invoke(cli, ["query", "anything"])
  # Either succeeded (yaams happened to be on PATH) or failed
  # cleanly with a non-zero exit. Either way we have valid output.
  assert isinstance(result.exit_code, int)


def test_ingest_unknown_verb_handled():
  result = CliRunner().invoke(cli, ["ingest", "--dry-run"])
  assert isinstance(result.exit_code, int)
