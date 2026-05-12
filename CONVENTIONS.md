# CONVENTIONS

**Status**: v1, signed off after the Phase 2a audit (2026-05-12).
Per-command conformance table is appended at the bottom; the audit
findings live in [AUDIT.md](AUDIT.md). This document is now the
binding spec for every binary in the suite.

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

## Stream routing

**Rule**: structured JSON output - success documents, success
envelopes, NDJSON streams, doctor payloads, AND failure envelopes -
travels on **stdout**. Stderr carries free-text diagnostics only:
human progress in default (non-`--json`) mode, captured tracebacks
on crash, deprecation notes, log lines.

The justification is consumer ergonomics across the suite:

- **One stream, one parser.** Every JSON-aware caller does the
  same thing: read stdout, parse the last JSON value (or the
  terminal `{type:"result"}` line for streaming actions), branch
  on the reserved `ok` key. No need to interleave stdout and
  stderr, no precedence rules, no buffering races.
- **Pipelines work.** `mnem mail messages --json | jq` handles
  both success and failure because the envelope is in the pipe.
  Stderr drains to the terminal regardless.
- **Streaming stays coherent.** Action commands emit
  `{type:"progress"}` lines on stdout and a terminal
  `{type:"result", ok: true|false}` on stdout. If failures went to
  stderr, a `tail`-style watcher on stdout would never see the
  failure terminator.

POSIX's "errors on stderr" tradition was written for unstructured
human-readable error text - which is still where it belongs. Once
the error becomes a structured machine-readable envelope, stream-
splitting between success and failure paths creates a parsing
nightmare. Modern JSON CLIs (`gh api`, `aws`, `kubectl -o json`,
`terraform output -json`) all put errors in the response body on
stdout, not on stderr; this contract follows that convention.

**For tool authors**: if your tool has a house rule "errors go to
stderr", that rule still applies to **free-text** errors. The
contract here only governs **structured envelopes** - those go
on stdout regardless of whether `ok` is `true` or `false`. Tracebacks,
log lines, human messages stay on stderr.

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
- `yaams query --tier raw|ledger|both` is a friendlier alternative
  to `--source ledger` (added in Phase 2b); yaams owns the alias
  rewrite internally.
- `config.yaml` accepts an `ingest.ledger:` block as an alias for
  `ingest.tier2_ledger:`; both keys resolve to the same adapter.
- `mnem query --tier=ledger` is a **passthrough** to `yaams query
  --tier=ledger`. (Earlier drafts had mnem rewrite `--tier ledger`
  into `--source ledger`; that rewrite became unnecessary in Phase
  2b when yaams gained native `--tier` support. The router stays as
  a thin argv passthrough per the "argument mapping, no business
  logic" rule.)

No data migration. No watermark migration. CLI aliasing only. Anyone
reading the SQLite directly sees the unchanged source id.

## Per-command conformance table

The signed-off mapping of every command in the suite to the contract
above. Each row is a regression-test fixture target for Phase 2b/2c.

Legend:
- **Class**: `data`, `action`, `interactive`
- **Modifiers**: `destructive` (or `-`)
- **`-j` / `-p`**: required (`req`), partial (`partial` - works on
  some subcommands only), missing (`miss`)
- **Success stdout**: `raw` (data document) / `envelope` /
  `ndjson+result` (streaming) / `human` (interactive only)
- **Failure stdout**: `envelope` / `n/a` (interactive: stderr only)
- **Stderr policy**: `clean` (progress/logs only, no secrets,
  redacted) / `human` (interactive prompts)
- **Exit codes**: subset of `{0,1,2,3,4,5}` the command can emit

### `yaams`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `yaams --version` | data | - | req | req | raw `{tool,version}` | envelope | clean | 0,1 |
| `yaams --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `yaams version` | data | - | req | req | raw `{tool,version}` | envelope | clean | 0,1 |
| `yaams setup` | action | - | req | req | envelope | envelope | clean | 0,1,2 |
| `yaams init-db` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `yaams ingest` | action | - | req | req | ndjson+result | envelope | clean | 0,1,2,3,5 |
| `yaams stats` | data | - | req | req | raw stats doc | envelope | clean | 0,1 |
| `yaams reset-db` | action | destructive | req | req | envelope | envelope | clean | 0,1 |
| `yaams query` | data | - | req | req | raw answer doc | envelope | clean | 0,1,2,4 |
| `yaams feedback` | action | - | req | req | envelope | envelope | clean | 0,1,4 |
| `yaams signals` | data | - | req | req | raw signals list | envelope | clean | 0,1 |
| `yaams consolidate` | action | - | req | req | envelope | envelope | clean | 0,1,2 |
| `yaams promote generate` | action | - | req | req | envelope | envelope | clean | 0,1,2 |
| `yaams promote list` | data | - | req | req | raw candidate list | envelope | clean | 0,1 |
| `yaams promote review` | interactive | - | reject | n/a | human | n/a | human | 0,1 |
| `yaams entities list` | data | - | req | req | raw entity list | envelope | clean | 0,1 |
| `yaams entities add` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `yaams entities remove` | action | destructive | req | req | envelope | envelope | clean | 0,1 |
| `yaams entities discover` | action | - | req | req | envelope | envelope | clean | 0,1,2 |
| `yaams entities denied` | data | - | req | req | raw list | envelope | clean | 0,1 |
| `yaams entities manage` | interactive | - | reject | n/a | human | n/a | human | 0,1 |
| `yaams enrich retag` | action | - | req | req | envelope | envelope | clean | 0,1,2 |

### `ledger`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ledger --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `ledger --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `ledger init` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `ledger paths` | data | - | req | req | raw paths doc | envelope | clean | 0,1 |
| `ledger loops` | data | - | req | req | raw list | envelope | clean | 0,1 |
| `ledger notes` | data | - | req | req | raw list | envelope | clean | 0,1 |
| `ledger query` | data | - | req | req | raw ranked list | envelope | clean | 0,1,4 |
| `ledger discover` | data | - | req | req | raw discovery doc | envelope | clean | 0,1 |
| `ledger embed build` | action | - | req | req | ndjson+result | envelope | clean | 0,1,2 |
| `ledger embed status` | data | - | req | req | raw status doc | envelope | clean | 0,1 |
| `ledger embed clean` | action | destructive | req | req | envelope | envelope | clean | 0,1 |
| `ledger eval` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `ledger context build` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `ledger context profiles` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `ledger ingest` | action | - | req | req | ndjson+result | envelope | clean | 0,1,2,5 |

### `ledger-obsidian`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ledger-obsidian --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `ledger-obsidian --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `ledger-obsidian sync` | action | - | req | req | envelope | envelope | clean | 0,1,2 |

### `sheep`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sheep --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `sheep --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2 |
| `sheep status` | data | - | req | req | raw status doc | envelope | clean | 0,1 |
| `sheep lint` | data | - | req | req | raw findings list | envelope | clean | 0,1 |
| `sheep index` | action | - | req | req | envelope | envelope | clean | 0,1,2 |
| `sheep sleep` | data | - | req | req | raw checklist | envelope | clean | 0,1 |
| `sheep sync` | data | - | req | req | raw diff doc | envelope | clean | 0,1 |

### `owa-piggy`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-piggy --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-piggy --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-piggy token` | data | - | req | req | raw token doc | envelope | clean | 0,1,3 |
| `owa-piggy status` | data | - | req | req | raw status doc | envelope | clean | 0,1,3 |
| `owa-piggy debug` | data | - | req | req | raw diagnostics doc | envelope | clean | 0,1,3 |
| `owa-piggy decode` | data | - | req | req | raw JWT parts | envelope | clean | 0,1 |
| `owa-piggy remaining` | data | - | req | req | raw `{minutes}` | envelope | clean | 0,1,3 |
| `owa-piggy setup` | interactive | - | reject | n/a | human | n/a | human | 0,1,3 |
| `owa-piggy reseed` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-piggy version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-piggy profiles list` | data | - | req | req | raw list | envelope | clean | 0,1 |
| `owa-piggy profiles set-default` | action | - | req | req | envelope | envelope | clean | 0,1 |
| `owa-piggy profiles delete` | action | destructive | req | req | envelope | envelope | clean | 0,1 |

### `owa-doctor`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-doctor` | data | - | req | req | doctor JSON (aggregated) | envelope | clean | 0,1,2,3 |
| `owa-doctor --version` | data | - | req | req | raw | envelope | clean | 0,1 |

### `owa-cal`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-cal --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-cal --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-cal events` | data | - | req | req | raw event list | envelope | clean | 0,1,2,3 |
| `owa-cal events-webcal` | data | - | req | req | raw webcal doc | envelope | clean | 0,1,2 |
| `owa-cal create` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-cal update` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-cal delete` | action | destructive | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-cal categories` | data | - | req | req | raw category list | envelope | clean | 0,1,2,3 |
| `owa-cal config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-cal refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |
| `owa-cal profiles` | data | - | req | req | raw list | envelope | clean | 0,1 |

### `owa-mail`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-mail --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-mail --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-mail messages` | data | - | req | req | raw message list | envelope | clean | 0,1,2,3 |
| `owa-mail show` | data | - | req | req | raw message doc | envelope | clean | 0,1,2,3,4 |
| `owa-mail send` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-mail reply` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail reply-all` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail forward` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail delete` | action | destructive | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail move` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail mark` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-mail folders` | data | - | req | req | raw folder list | envelope | clean | 0,1,2,3 |
| `owa-mail config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-mail refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |

### `owa-graph`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-graph --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-graph --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-graph get` | data | - | req | req | raw response | envelope | clean | 0,1,2,3,4 |
| `owa-graph post` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-graph put` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-graph patch` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-graph delete` | action | destructive | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-graph batch` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,5 |
| `owa-graph config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-graph refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |

### `owa-people`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-people --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-people --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-people find` | data | - | req | req | raw list | envelope | clean | 0,1,2,3 |
| `owa-people directory` | data | - | req | req | raw list | envelope | clean | 0,1,2,3 |
| `owa-people show` | data | - | req | req | raw record | envelope | clean | 0,1,2,3,4 |
| `owa-people me` | data | - | req | req | raw record | envelope | clean | 0,1,3 |
| `owa-people contacts` | data | - | req | req | raw list | envelope | clean | 0,1,2,3 |
| `owa-people config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-people refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |

### `owa-sched`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-sched --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-sched --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-sched availability` | data | - | req | req | raw availability doc | envelope | clean | 0,1,2,3 |
| `owa-sched find-time` | data | - | req | req | raw slot list | envelope | clean | 0,1,2,3 |
| `owa-sched config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-sched refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |

### `owa-drive`

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `owa-drive --version` | data | - | req | req | raw | envelope | clean | 0,1 |
| `owa-drive --doctor` | data | - | req | req | doctor JSON | envelope | clean | 0,1,2,3 |
| `owa-drive ls` | data | - | req | req | raw entry list | envelope | clean | 0,1,2,3,4 |
| `owa-drive show` | data | - | req | req | raw entry record | envelope | clean | 0,1,2,3,4 |
| `owa-drive get` | action | - | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-drive put` | action | - | req | req | envelope | envelope | clean | 0,1,2,3 |
| `owa-drive rm` | action | destructive | req | req | envelope | envelope | clean | 0,1,2,3,4 |
| `owa-drive config` | data | - | req | req | raw config doc | envelope | clean | 0,1 |
| `owa-drive refresh` | action | - | req | req | envelope | envelope | clean | 0,1,3 |

### `owa` (dispatcher)

`owa` is a passthrough dispatcher that routes `owa <tool> <args...>`
to the named `owa-<tool>` binary. It MUST itself implement
`--version` and `--doctor` per the data-class spec. All other
behavior is inherited from the dispatched binary.

### `mnem`

Defined here for completeness; lands in Phase 3a/3b.

| Command | Class | Mods | `-j` | `-p` | Success stdout | Failure stdout | Stderr | Exit codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mnem --version` | data | - | req | req | raw `{tool,version,observed[]}` | envelope | clean | 0,1 |
| `mnem hello` | data | - | req | req | raw `{verbs[],examples[]}` | envelope | clean | 0,1 |
| `mnem doctor` | data | - | req | req | doctor JSON (aggregated) | envelope | clean | 0,1,2,3 |
| `mnem version` | data | - | req | req | raw `{tool,version,observed[]}` | envelope | clean | 0,1 |
| `mnem init` | interactive | - | reject | n/a | human | n/a | human | 0,1 |
| `mnem query` | data | - | req | req | raw answer doc | envelope | clean | 0,1,2,3,4 |
| `mnem ingest` | action | - | req | req | ndjson+result | envelope | clean | 0,1,2,3,5 |
| `mnem promote review` | interactive | - | reject | n/a | human | n/a | human | 0,1 |
| `mnem ledger ...` | (inherits from `ledger` subcommand) |
| `mnem mail ...` | (inherits from `owa-mail` subcommand) |
| `mnem calendar ...` | (inherits from `owa-cal` subcommand) |
| `mnem auth ...` | (inherits from `owa-piggy` subcommand) |

## Status

Phase 1: draft published.

Phase 2a: signed off, table above is binding. Audit results in
[AUDIT.md](AUDIT.md).

Phase 2b/2c: tools migrate to conformance.

Phase 3a/3b: `mnem` ships against this contract.
