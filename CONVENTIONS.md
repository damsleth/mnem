# CONVENTIONS

**Status**: draft (Phase 1). The per-command conformance table and
sign-off land in Phase 2a; until then, every section below is open
to change. Once signed, this document is the binding spec for every
binary in the suite.

This document defines the CLI contract that `yaams`, `ledger`,
`ledger-obsidian`, `sheep`, `owa-piggy`, the eight `owa-*` tools, and
`mnem` itself all conform to. Skill authors and automation can rely
on it.

## Output classes

Each command has **exactly one primary class** (data, action, or
interactive) and **zero or more modifiers** (currently only
`destructive`). The primary class governs default output behavior;
modifiers layer in gating concerns like confirmation prompts.

### Primary classes (mutually exclusive)

| Class | Default | `--pretty` | `--json` | Example commands |
| --- | --- | --- | --- | --- |
| **data** | JSON to stdout | renders a table / prose | machine mode (same wire format as default; the explicit form callers use to assert "I expect JSON") | `yaams query`, `yaams stats`, `ledger query`, `owa-cal events`, `owa-mail list` |
| **action** | JSON result envelope on completion | renders a one-line summary | machine mode; for long-running action commands also enables NDJSON streaming (see below) | `yaams ingest`, `yaams promote generate`, `ledger sleep index`, `owa-mail send`, `yaams reset-db` |
| **interactive** | human-only; no JSON default | (n/a) | rejected with a clear error | `yaams promote review`, `owa-piggy setup` |

`--json` means **machine mode**, not "alias to default". For data
and short-running action commands the wire format is the same as the
default - the flag is the explicit form callers use when they want
to assert "I expect JSON; do not change that based on isatty
heuristics or future default flips". For long-running action
commands `--json` additionally enables NDJSON progress streaming.

### Modifiers (orthogonal, additive)

| Modifier | Effect | Output | Example commands |
| --- | --- | --- | --- |
| **destructive** | requires `--yes` or a TTY confirmation prompt before the primary class runs | inherits from primary class; envelope `stats` records what was destroyed | `yaams reset-db` (action + destructive), `ledger archive --hard` (action + destructive) |

`yaams ingest` is primary **action**: default emits the envelope on
completion; with `--json` it streams structured progress lines on
stdout followed by the final envelope. `yaams reset-db` is primary
**action** with modifier **destructive**: gated by `--yes`, then
emits an action envelope. `yaams promote review` is primary
**interactive** with no modifier: rejects `--json`, prompts a human.

## Action envelope schema

Every action command, when run with the JSON default, finishes with:

```json
{
  "tool": "yaams",
  "version": "0.2.0",
  "command": "ingest",
  "ok": true,
  "duration_ms": 12345,
  "stats": { /* command-specific */ },
  "warnings": [],
  "error": null
}
```

On failure, `ok` is `false`, `error` is an object with
`{code, message, hint}`, and exit code is nonzero.

**Invariant**: when an envelope is emitted, `ok: false` if and only
if the exit code is nonzero. The two MUST agree; a tool that
disagrees is broken and fails its own `--doctor` check.

**For callers**: shell scripts (the common case) may branch on exit
code alone - that is always present and always correct. JSON-aware
callers (`mnem`, skills, automation) parse the envelope for
structured detail and SHOULD validate that `ok` agrees with the
exit code; a disagreement is a bug to report, not state to act on.

## Streaming schema (action commands with `--json`)

Long-running action commands (`yaams ingest`, `ledger sleep index`,
`mnem ingest`) MAY emit progress as a stream when `--json` is
passed. The framing is **newline-delimited JSON (NDJSON)** on stdout,
one object per line, each object carrying an explicit `type` field:

```jsonl
{"type":"progress","source":"imessage","stage":"fetch","done":120,"total":4400,"ts":"2026-05-11T10:00:01Z"}
{"type":"progress","source":"imessage","stage":"index","done":4400,"total":4400,"ts":"2026-05-11T10:00:14Z"}
{"type":"warning","source":"signal","message":"sqlcipher not on PATH; skipping","ts":"2026-05-11T10:00:14Z"}
{"type":"result", ...full action envelope...}
```

Contract:

- `type` is required on every line. Defined values: `progress`,
  `warning`, `result`. Tools MAY add new types; consumers MUST
  ignore unknown types.
- Exactly one `{"type":"result", ...}` line per run, always last on
  a clean exit. Its body is the full action envelope.
- On crash, the `result` line may be missing. Consumers that see
  EOF without a `result` MUST treat the run as failed regardless of
  the preceding progress lines; the exit code is the source of
  truth.
- Without `--json` (default), action commands emit human-readable
  progress on stderr and the final envelope on stdout. Stderr
  framing is not a contract; stdout framing is.

## Data-class failure envelope

Data commands emit raw result documents on stdout, not envelopes. On
**failure** they MUST switch to a minimal error envelope on stdout
so JSON-aware callers always get parseable JSON:

```json
{
  "tool": "owa-cal",
  "version": "0.2.0",
  "command": "events",
  "ok": false,
  "error": {
    "code": "auth_expired",
    "message": "M365 access token expired",
    "hint": "Run: mnem auth setup"
  }
}
```

**Reserved key**: `ok` is reserved as the error-vs-success
discriminator across the suite. **Data result documents MUST NOT
contain a top-level `ok` key.** If a tool's natural payload happens
to contain an `ok` field (e.g. a record mirroring a webhook schema),
the tool MUST wrap the payload in a container that does not collide
- either an array (`[{...record with ok...}]`), an explicit results
envelope (`{"results": [...]}`), or any object whose top level has
no `ok` key. The conformance audit fails any data command whose
success output puts `ok` at the top level.

Consumer rule: parse the top-level JSON value; if it is an object
with `ok === false`, treat as error envelope; otherwise treat as
data. Exit code agrees per the invariant - if the exit code is
nonzero, expect an error envelope (or a crash with no JSON).

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success - all sub-tasks ok, `ok: true` in envelope |
| 1 | user error (bad flag, bad input) |
| 2 | transient / retryable (network, lock) |
| 3 | auth (token expired, scope missing, macOS Full Disk Access not granted) |
| 4 | not found (entity, file, profile) |
| 5 | partial success - some sub-tasks failed; `ok: false` and `warnings[]` populated. Distinct from 1 so automation can tell "nothing happened" from "some things happened". Collapses to 1 under `--strict`. |
| 64-78 | reserved for tool-specific use; document in each tool |

## Config precedence (single, suite-wide)

Per-tool config resolution order, applied in every binary. The first
match wins:

1. Explicit `--config <path>` flag.
2. Tool-specific env var (see scope table below).
3. `$XDG_CONFIG_HOME/mnem/<tool>/config.yaml` (new shared root).
4. `$XDG_CONFIG_HOME/<tool>/config.yaml` (legacy per-tool root).
5. `./config.yaml` (development-only fallback - takes effect only
   when no global config exists, so a user with a global install is
   never silently overridden by a stray file in `cwd`). Repo-local
   *override* of an installed global config requires explicit
   `--config ./config.yaml` or the tool-specific env var.

### Env var scope

Each var resolves only the binaries it owns. This is what direct-CLI
/ `mnem` parity hinges on:

| Env var | Binaries it configures |
| --- | --- |
| `YAAMS_CONFIG` | `yaams` |
| `LEDGER_CONFIG` | `ledger`, `ledger-obsidian`, `sheep` (all three read the same ledger config tree) |
| `OWA_PIGGY_CONFIG` | `owa-piggy` only (auth broker has its own config; tokens live in OS keychain regardless) |
| `OWA_CONFIG` | `owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive` (the read/write CLIs; they share one config) |
| `MNEM_CONFIG` | `mnem` itself (router-level settings; does NOT override the per-tool vars above) |

Rule: a per-tool env var only affects that tool's binaries. `mnem`
invocations of a tool inherit the user's environment, so setting
`YAAMS_CONFIG` makes both `yaams query` and `mnem query` resolve to
the same config. No tool reads another tool's env var.

### Data path resolution

Per-tool data resolution order, separate from config:

1. Explicit value in config (`db_path`, `notes_dir`, etc.).
2. `MNEM_HOME/<tool>/` if `MNEM_HOME` is set (e.g.
   `$MNEM_HOME/yaams/data.db`).
3. Tool-specific default (e.g. `~/yaams/data.db`).

Direct CLI invocation and `mnem` invocation MUST resolve to the same
config and data paths given the same environment. Each tool's test
suite gains an integration check that verifies this.

## Public CLI surface

Every JSON-capable binary in the suite MUST expose:

- `--version`. JSON shape: `{"tool": "...", "version": "x.y.z"}`.
- `--json` flag. Accepted on every command. Default for data and
  action classes. Rejected with a clear error for interactive
  classes.
- `--pretty` flag. Accepted on every data and action command.
- `<tool> --help` and `<tool> <cmd> --help`.
- `<tool> --doctor`. Output class: **data**. Returns a structured
  JSON document on stdout describing the tool's conformance state,
  config and data paths, auth state (where applicable), and
  `findings[]` with `{id, severity, message, hint}`. Exit code
  follows the standard table (0 ok, 1 user-fixable, 2 transient, 3
  auth). `mnem doctor` aggregates these documents.

### Doctor JSON schema

```json
{
  "tool": "yaams",
  "version": "0.2.0",
  "config_path": "/Users/cj/.config/mnem/yaams/config.yaml",
  "data_path": "/Users/cj/yaams/data.db",
  "auth": { "ok": true, "profiles": [] },
  "models": { "embedding": "BAAI/bge-m3", "available": true },
  "findings": [
    {
      "id": "spacy_model_missing",
      "severity": "error",
      "message": "spaCy multilingual NER model not installed",
      "hint": "Run: yaams setup"
    }
  ]
}
```

Severities: `info`, `warning`, `error`. The exit code reflects the
highest-severity finding (`error` → 1 or 3, `warning` → 0,
`info` → 0).

## Redaction (no secrets to stderr)

Every JSON-capable binary MUST run captured-or-emitted stderr through
a `redact()` utility before writing. Redaction targets:

- JWT-like strings (three base64 segments joined by `.`).
- `Bearer <...>` headers.
- `refresh_token`, `access_token`, `client_secret` field values.
- Body fields named `body`, `content`, `text` (mail/message content).
- Attachment paths.

Enforcement stack:

1. Shared `redact()` utility wired into each tool's logging path.
2. Exception handlers wrap subprocess calls and external library
   calls so uncaught exceptions are formatted through the redactor.
3. Fixture-based CI tests: feed a synthetic message containing a
   known sentinel (e.g. `CANARY_SECRET_xxxx`) through every failure
   path. CI fails if any sentinel leaks to stderr.
4. `<tool> --doctor` runs the same fixture set against the installed
   binary as a smoke test.

`mnem` applies its **own** redaction pass to captured stderr before
writing `~/.local/state/mnem/last-error.log` - defense in depth on
top of the tool-side redactor.

## YAAMS-specific contracts

Before `mnem` exists (i.e. by end of Phase 2b):

- `yaams query` accepts `--json` (alias for `--format json`) and
  `--pretty` (alias for `--format text`).
- `yaams query` accepts `--tier raw|ledger|both` (translates
  internally to `--source` filters + retrieval config; `ledger` is a
  CLI alias for `tier2_ledger`).
- Regression test covers: `--format json` (legacy), `--json` (new),
  `--pretty` (new), and `--tier=both` passthrough behavior.

### `tier2_ledger` rename - the explicit call

The internal source id stays `tier2_ledger`. Database rows,
watermarks, and adapter code do not change. The CLI surface accepts
`ledger` as an alias:

- `yaams ingest --source ledger` works and dispatches the
  `tier2_ledger` adapter.
- `yaams query --source ledger` filters by `tier2_ledger`.
- `config.yaml` accepts an `ingest.ledger:` block as an alias for
  `ingest.tier2_ledger:`; both keys resolve to the same adapter.
- `mnem query --tier=ledger` maps to `yaams query --source ledger`.

No data migration. No watermark migration. CLI aliasing only. Anyone
reading the SQLite directly sees the unchanged source id.

## Status

Phase 1: this draft published.

Phase 2a: per-command conformance table added; signed off; binary
audit complete with one filed issue per conformance gap in each
repo.

Phase 2b/2c: tools migrate to conformance.

Phase 3a/3b: `mnem` ships against this contract.
