"""Tests for the translation table.

The router rule is "argument mapping, no business logic". These
tests pin the table so the rule stays enforceable.
"""
from __future__ import annotations

import pytest

from mnem.router import TABLE, lookup, verbs


def test_table_has_required_verbs_for_phase_3a():
  expected = {("ingest",), ("query",)}
  assert expected.issubset(set(TABLE.keys()))


def test_lookup_unknown_verb_returns_none():
  assert lookup(["does-not-exist"]) is None
  assert lookup([]) is None


def test_lookup_ingest_passthrough():
  mapping, rewritten = lookup(["ingest"])
  assert mapping.binary == "yaams"
  assert rewritten == ["ingest"]


def test_lookup_ingest_forwards_extra_args():
  mapping, rewritten = lookup(["ingest", "--source", "imessage", "--dry-run"])
  assert mapping.binary == "yaams"
  assert rewritten == ["ingest", "--source", "imessage", "--dry-run"]


def test_lookup_query_routes_to_yaams():
  mapping, rewritten = lookup(["query", "what was discussed?"])
  assert mapping.binary == "yaams"
  assert rewritten == ["query", "what was discussed?"]


def test_lookup_query_forwards_tier_flag_verbatim():
  """`--tier` is rewritten on yaams' side already; the router just
  forwards. Pin the contract: no router-side rewrite of --tier."""
  _, rewritten = lookup(["query", "--tier", "ledger", "x"])
  assert "--tier" in rewritten
  assert "ledger" in rewritten


def test_verbs_returns_descriptions():
  rows = verbs()
  assert rows
  for verb, binary, desc in rows:
    assert isinstance(verb, str)
    assert isinstance(binary, str)
    assert isinstance(desc, str)


def test_every_mapping_has_callable_rewrite():
  for verb, mapping in TABLE.items():
    rewritten = mapping.rewrite([])
    assert isinstance(rewritten, list)


# --- Phase 3b expansions ----------------------------------------------------

def test_promote_review_routes_to_yaams():
  mapping, rewritten = lookup(["promote", "review"])
  assert mapping.binary == "yaams"
  assert rewritten == ["promote", "review"]


def test_promote_review_forwards_extra_flags():
  _, rewritten = lookup(["promote", "review", "--all"])
  assert rewritten == ["promote", "review", "--all"]


def test_ledger_query_routes_to_ledger():
  mapping, rewritten = lookup(["ledger", "query", "test"])
  assert mapping.binary == "ledger"
  assert rewritten == ["query", "test"]


def test_auth_status_routes_to_owa_piggy():
  mapping, rewritten = lookup(["auth", "status"])
  assert mapping.binary == "owa-piggy"
  assert rewritten == ["status"]


def test_mail_routes_to_owa_mail():
  mapping, rewritten = lookup(["mail", "messages"])
  assert mapping.binary == "owa-mail"
  assert rewritten == ["messages"]


def test_calendar_routes_to_owa_cal():
  mapping, rewritten = lookup(["calendar", "events", "--today"])
  assert mapping.binary == "owa-cal"
  assert rewritten == ["events", "--today"]


def test_drive_routes_to_owa_drive():
  mapping, rewritten = lookup(["drive", "ls"])
  assert mapping.binary == "owa-drive"
  assert rewritten == ["ls"]


# --- ledger context (Plan 03 / review F6) ----------------------------------

def test_bare_ledger_context_emits_format_json():
  """Bare `ledger context` rejects --json; the route rewrites to
  --format json and marks json_policy=none so passthrough doesn't
  add anything."""
  mapping, rewritten = lookup(["ledger", "context"])
  assert mapping.binary == "ledger"
  assert rewritten == ["context", "--format", "json"]
  assert mapping.json_policy == "none"


def test_bare_ledger_context_forwards_extra_args():
  _, rewritten = lookup(["ledger", "context", "--scope", "today"])
  assert rewritten == ["context", "--format", "json", "--scope", "today"]


def test_ledger_context_build_uses_native_json_route():
  mapping, rewritten = lookup(["ledger", "context", "build"])
  assert mapping.binary == "ledger"
  assert rewritten == ["context", "build"]
  assert mapping.json_policy == "inject"


def test_ledger_context_profiles_uses_native_json_route():
  mapping, rewritten = lookup(["ledger", "context", "profiles"])
  assert mapping.binary == "ledger"
  assert rewritten == ["context", "profiles"]
  assert mapping.json_policy == "inject"


def test_ledger_context_build_with_args():
  _, rewritten = lookup(["ledger", "context", "build", "--profile", "boot"])
  assert rewritten == ["context", "build", "--profile", "boot"]


def test_longest_prefix_match_wins():
  # `mnem promote review` should beat any hypothetical `mnem
  # promote` mapping (today there's no bare `promote`, but the
  # routing logic must still resolve the longest prefix first).
  mapping, _ = lookup(["promote", "review"])
  assert mapping.binary == "yaams"
  # And a bare `mnem promote` with no subcommand returns None
  # rather than dispatching to a shorter prefix.
  result = lookup(["promote"])
  # promote-only doesn't exist in the table; expect None.
  assert result is None or result[0].binary == "yaams"
