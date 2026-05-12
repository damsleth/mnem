"""Tests for mnem/conventions.py - mirrors the sibling test files."""
from __future__ import annotations

import io
import json

from mnem import __version__
from mnem.conventions import (
  DoctorFinding,
  DoctorPayload,
  EXIT_OK,
  EXIT_PARTIAL,
  EXIT_USER_ERROR,
  action_envelope,
  data_error,
  emit_action,
  emit_data_error,
  redact,
  stream_progress,
  stream_result,
  stream_warning,
)


def test_redact_jwt_like():
  jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnkifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
  assert jwt not in redact(f"x={jwt}")


def test_redact_bearer():
  assert "abc123def456" not in redact("Authorization: Bearer abc123def456")


def test_redact_token_fields():
  out = redact('{"access_token":"xyz","refresh_token":"qrs"}')
  assert "xyz" not in out and "qrs" not in out


def test_redaction_sentinel_does_not_leak():
  jwt = "eyJfake." + "CANARY_SECRET_xxxx" + "." + "padding1234"
  assert "CANARY_SECRET_xxxx" not in redact(f"Authorization: Bearer {jwt}")


def test_redact_handles_non_string():
  assert redact(None) == ""
  assert redact(42) == "42"


def test_action_envelope_shape():
  env = action_envelope(command="ingest", ok=True, stats={"sources": 3})
  assert env["tool"] == "mnem"
  assert env["version"] == __version__
  assert env["command"] == "ingest"
  assert env["ok"] is True
  assert env["stats"]["sources"] == 3


def test_action_envelope_failure():
  env = action_envelope(
    command="ingest", ok=False,
    error={"code": "x", "message": "boom"},
  )
  assert env["ok"] is False
  assert env["error"]["code"] == "x"


def test_emit_action_one_line():
  buf = io.StringIO()
  emit_action(action_envelope(command="x", ok=True), stream=buf)
  payload = json.loads(buf.getvalue())
  assert payload["command"] == "x"


def test_data_error_shape():
  err = data_error(command="x", code="c", message="m", hint="h")
  assert err["tool"] == "mnem"
  assert err["ok"] is False
  assert err["error"]["hint"] == "h"


def test_emit_data_error_one_line():
  buf = io.StringIO()
  emit_data_error(data_error(command="x", code="c", message="m"), stream=buf)
  payload = json.loads(buf.getvalue())
  assert payload["ok"] is False


def test_stream_progress_schema():
  buf = io.StringIO()
  stream_progress(source="yaams", stage="ingest", done=10, total=100, stream=buf)
  payload = json.loads(buf.getvalue())
  assert payload["type"] == "progress"
  assert payload["source"] == "yaams"
  assert "ts" in payload


def test_stream_warning_redacts():
  buf = io.StringIO()
  stream_warning("Bearer secrettoken in stack trace", stream=buf)
  assert "secrettoken" not in json.loads(buf.getvalue())["message"]


def test_stream_result_carries_envelope():
  buf = io.StringIO()
  stream_result(action_envelope(command="ingest", ok=True), stream=buf)
  payload = json.loads(buf.getvalue())
  assert payload["type"] == "result"
  assert payload["command"] == "ingest"


def test_doctor_payload_minimal():
  d = DoctorPayload().to_dict()
  assert d["tool"] == "mnem"
  assert d["findings"] == []


def test_doctor_payload_full():
  d = DoctorPayload(
    config_path="/etc/mnem/config.yaml",
    findings=[
      DoctorFinding(id="x", severity="error", message="m", hint="fix it"),
    ],
  ).to_dict()
  assert d["config_path"] == "/etc/mnem/config.yaml"
  assert d["findings"][0]["severity"] == "error"
  assert d["findings"][0]["hint"] == "fix it"


def test_doctor_exit_codes():
  assert DoctorPayload().exit_code() == EXIT_OK
  d = DoctorPayload(findings=[DoctorFinding(id="x", severity="error", message="m")])
  assert d.exit_code() == EXIT_USER_ERROR


def test_exit_constants():
  assert EXIT_OK == 0
  assert EXIT_USER_ERROR == 1
  assert EXIT_PARTIAL == 5
