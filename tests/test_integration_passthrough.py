"""Integration tests pinning the passthrough contract.

The Phase 3a exit gate from `mnem_plan.md`:
  "The same query against the same data produces identical output
   whether issued via `yaams query --json` or `mnem query --json`."

These tests verify that contract by invoking both paths against a
disposable yaams DB and comparing the captured JSON shape.

Skipped when yaams is not on PATH (so the suite stays runnable in
mnem's own venv without the rest of the suite installed).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _yaams_supports_json() -> bool:
  """True iff yaams on PATH ships the Phase 2b contract (--json flag)."""
  if shutil.which("yaams") is None:
    return False
  result = subprocess.run(
    ["yaams", "query", "--help"],
    capture_output=True, text=True,
  )
  return "--json" in result.stdout


pytestmark = pytest.mark.skipif(
  not _yaams_supports_json(),
  reason=(
    "yaams either not on PATH or not yet on the Phase 2b contract "
    "(needs --json on `yaams query`). Activate the YAAMS dev venv "
    "or `brew upgrade yaams` to a >=0.1.2 build to run these tests."
  ),
)


@pytest.fixture
def yaams_config(tmp_path: Path) -> Path:
  """Minimal config that init-db can bootstrap without external deps."""
  cfg = tmp_path / "config.yaml"
  db = tmp_path / "data.db"
  cfg.write_text(f"""
db_path: {db}

ingest:
  since: '2025-01-01T00:00:00Z'

embed:
  model: dummy
  dimension: 4

entities:
  dictionary: []
""")
  subprocess.run(
    ["yaams", "init-db", "--config", str(cfg)],
    check=True, capture_output=True,
  )
  return cfg


def _yaams_query(cfg: Path) -> dict:
  result = subprocess.run(
    [
      "yaams", "query",
      "--config", str(cfg),
      "--no-vector", "--no-parse", "--no-log",
      "--json",
      "anything",
    ],
    capture_output=True, text=True, check=True,
  )
  return _parse_final_json(result.stdout)


def _parse_final_json(text: str) -> dict | None:
  """Parse the final JSON document on stdout.

  Data commands emit one pretty-printed JSON doc (multi-line).
  Action commands emit NDJSON ending in a `{type:"result", ...}`
  line. Handle both by trying whole-text parse first, then falling
  back to last-line parse.
  """
  text = (text or "").strip()
  if not text:
    return None
  try:
    return json.loads(text)
  except json.JSONDecodeError:
    pass
  for line in reversed(text.splitlines()):
    try:
      return json.loads(line.strip())
    except json.JSONDecodeError:
      continue
  return None


def _mnem_query(cfg: Path) -> dict:
  mnem = shutil.which("mnem") or (Path(sys.executable).parent / "mnem")
  result = subprocess.run(
    [
      str(mnem), "query",
      "--config", str(cfg),
      "--no-vector", "--no-parse", "--no-log",
      "--json",
      "anything",
    ],
    capture_output=True, text=True, check=True,
  )
  return _parse_final_json(result.stdout)


def test_mnem_query_byte_identical_to_yaams_query(yaams_config: Path):
  direct = _yaams_query(yaams_config)
  via_mnem = _mnem_query(yaams_config)

  # retrieval_ms is timing - allow any nonzero value but ignore for
  # the equality check. Same for query_id (random uuid).
  for doc in (direct, via_mnem):
    doc.pop("retrieval_ms", None)
    doc.pop("synthesis_ms", None)
    doc.pop("query_id", None)
  assert direct == via_mnem, (
    f"mnem query and yaams query diverged.\n"
    f"  direct: {direct}\n"
    f"  via mnem: {via_mnem}"
  )


def test_mnem_query_preserves_reserved_key_contract(yaams_config: Path):
  payload = _mnem_query(yaams_config)
  # Data class: no top-level `ok` on success.
  assert "ok" not in payload


def _yaams_ingest_dry_run(cfg: Path) -> dict | None:
  result = subprocess.run(
    [
      "yaams", "ingest",
      "--config", str(cfg),
      "--dry-run",
      "--json",
    ],
    capture_output=True, text=True,
  )
  return _parse_final_json(result.stdout)


def _mnem_ingest_dry_run(cfg: Path) -> dict | None:
  mnem = shutil.which("mnem") or (Path(sys.executable).parent / "mnem")
  result = subprocess.run(
    [str(mnem), "ingest", "--config", str(cfg), "--dry-run", "--json"],
    capture_output=True, text=True,
  )
  return _parse_final_json(result.stdout)


def test_mnem_ingest_terminal_envelope_matches_yaams(yaams_config: Path):
  direct = _yaams_ingest_dry_run(yaams_config)
  via_mnem = _mnem_ingest_dry_run(yaams_config)
  for env in (direct, via_mnem):
    assert env is not None
    env.pop("duration_ms", None)
  # The terminal `{type:"result", ...}` envelope from mnem is the
  # same data shape as yaams' direct envelope, modulo timing.
  if direct.get("type") == "result":
    direct = {k: v for k, v in direct.items() if k != "type"}
  if via_mnem.get("type") == "result":
    via_mnem = {k: v for k, v in via_mnem.items() if k != "type"}
  assert direct == via_mnem
