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
