# Conformance audit (Phase 2a)

**Audit date**: 2026-05-12
**Auditor**: read-only scan of source under `~/code/{YAAMS,
cognitive-ledger, CLI/owa/*}` against
[CONVENTIONS.md](CONVENTIONS.md) v1.

Each gap below is one issue to file against the named repo before
the Phase 2b/2c migration starts. The mnem repo does not file these
issues itself - that is a human action that touches shared state
(GitHub).

Severity legend:
- **block**: violates a hard invariant; the suite contract breaks if
  not fixed.
- **major**: required for `mnem` to ship, but not invariant-breaking.
- **minor**: stylistic or surface-area gap that can land any time
  before Phase 3a.

---

## YAAMS (`damsleth/yaams`, v0.1.x)

**Target**: v0.2.0 in Phase 2b.

### block
1. **No top-level `yaams --doctor`.** Required by 2c. No structured
   doctor JSON. (`yaams/cli.py:59` shows the group but no `--doctor`
   option.)
2. **No action envelopes on action-class commands.** `init-db`,
   `ingest`, `consolidate`, `reset-db`, `setup`, `feedback`,
   `promote generate`, `enrich retag`, `entities {add,remove,
   discover}` all need the standard envelope on stdout. Today they
   print human-readable strings on stdout.
3. **`reset-db` not gated by `--yes` / TTY confirmation.** Spec
   requires destructive modifier; current code may proceed without
   confirmation.
4. **Exit codes flatten to 0/1.** Need 2 (transient), 3 (auth), 4
   (not found), 5 (partial success) wired through where the table
   says.

### major
5. **`--json` is partial.** Defined on `query` (line 66) and as
   `--format json` only. Per spec it must be a top-level flag
   accepted on every data and action command (rejected on
   `promote review` / `entities manage`).
6. **No `--pretty` alias.** `query` accepts `--format text`; the
   `--pretty` alias does not exist yet.
7. **No NDJSON streaming on `ingest`.** With `--json`, ingest must
   emit `{type:"progress"|"warning"|"result"}` lines per the
   streaming schema. Today it emits human progress on stdout, which
   would break the contract when consumed by `mnem`.
8. **`promote review` and `entities manage` do not explicitly
   reject `--json`.** Required for interactive class - they should
   exit 1 with a clear message, not silently ignore the flag.
9. **`yaams query` reserved-key compliance not verified.** Audit
   that the answer document does not put `ok` at the top level. If
   it does, wrap it.
10. **`--tier` not present on `yaams query`.** Required before
    Phase 3 per the spec; should accept `raw|ledger|both` and be a
    user-facing alias on top of internal `--source` filters.
11. **Config alias `ingest.ledger:` → `ingest.tier2_ledger:`** does
    not exist yet.

### minor
12. **Stderr deprecation warning** when stdout is a TTY and the
    user gets legacy default human output that flips in 0.2.x.
    Migration-window requirement; not a permanent contract.
13. **No redaction sentinel test** in the test suite. Spec requires
    a `CANARY_SECRET_xxxx` fixture run through every failure path.
14. **Existing `--format json` must keep working** alongside the
    new `--json` flag for one release.

---

## cognitive-ledger (`damsleth/cognitive-ledger`, v0.2.x)

**Target**: v0.3.0 in Phase 2b, same week as YAAMS.

### block
1. **No top-level `ledger --doctor`, `ledger-obsidian --doctor`,
   `sheep --doctor`.** Required by 2c.
2. **No action envelopes.** `init`, `ingest`, `embed build`, `embed
   clean`, `eval`, `context build`, `context profiles` need
   envelopes on stdout. argparse-based today; output is mostly
   prints.
3. **`embed clean` not gated as destructive.** Spec requires
   `--yes` / TTY confirmation.
4. **Exit codes flatten to 0/1.** Need 2/3/4/5 per the table.

### major
5. **`--json` is partial** (`cli.py:753, 783, 805, 809, 813, 838,
   870`). Defined on `query`, `discover`, `embed build`, `embed
   status`, `embed clean`, `eval`, `paths`. Missing on `init`,
   `loops`, `notes`, `context build`, `context profiles`, `ingest`,
   plus all `sheep` and `ledger-obsidian` subcommands.
6. **No `--pretty` flag.** Today some subcommands use `--format
   text` (line 849) - alias `--pretty` to it.
7. **No NDJSON streaming on `ingest`, `embed build`.** Both are
   long-running and need the streaming contract under `--json`.
8. **Reserved-key compliance not verified** on `query`,
   `discover`, `loops`, `notes`, `paths` output. Audit and wrap any
   that put `ok` at the top level.

### minor
9. **`sheep` subcommand flag coverage.** Currently no `--json` /
   `--pretty` anywhere (`maintenance.py:1126`).
10. **Redaction stack** - same as YAAMS minor 13.
11. **`ledger-obsidian` surface is minimal** but must still
    implement `--version`, `--doctor`, `--json`, `--pretty`.

---

## owa-piggy (`damsleth/owa-piggy`, v0.8.x)

**Target**: v0.9.0 in Phase 2c.

### block
1. **`--doctor` exists but JSON shape needs alignment.** Verify the
   document matches the doctor schema in CONVENTIONS.md (tool,
   version, config_path, data_path, auth, findings[]). The current
   `do_status` / `do_debug` paths predate the spec.
2. **Exit codes flatten.** Verify 0/1/2/3 are emitted per the
   table; some commands likely collapse 3 (auth) to 1.
3. **Action envelopes missing on `reseed`, `profiles set-default`,
   `profiles delete`.**

### major
4. **`--pretty` audit.** owa-piggy README says JSON-by-default; verify
   `--pretty` is the spelling everywhere (not e.g. `--format
   pretty`).
5. **`setup` declared interactive.** Must reject `--json` cleanly.
6. **`profiles delete` not gated as destructive.** Add `--yes` /
   confirmation.

### minor
7. **`--version` JSON shape** - confirm it is `{tool, version}` not
   a bare string.
8. **Redaction sentinel test.** Tokens and JWT segments are
   exactly the secrets to be redacted; this is the highest-priority
   redaction surface in the suite.

---

## owa-tools (`damsleth/owa-tools`, v0.1.x)

**Target**: v0.2.0 in Phase 2c. Eight binaries:
`owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`,
`owa-people`, `owa-sched`, `owa-drive`.

### block
1. **No per-binary `--doctor`.** Today `owa-doctor` is a separate
   binary that aggregates. Spec requires each `owa-*` binary to
   also implement `<tool> --doctor` so `mnem doctor` can fan out.
   `owa-doctor` itself stays and aggregates per-binary doctors.
2. **No action envelopes** on any action-class command (`owa-cal
   create/update/delete`, `owa-mail send/reply/forward/delete/move/
   mark`, `owa-graph post/put/patch/delete/batch`, `owa-drive
   get/put/rm`, `owa-* refresh`).
3. **`owa-cal delete`, `owa-mail delete`, `owa-graph delete`,
   `owa-drive rm`** not gated as destructive.
4. **Exit codes** - `owa-cal/cli.py` docstring says "0 success, 1
   error" - need 2/3/4/5 per the table.

### major
5. **`--json` flag.** owa-tools is already JSON-by-default, but the
   explicit `--json` flag is missing from the subcommand surfaces.
   Add it as a no-op alias that asserts machine mode (and blocks
   isatty heuristics).
6. **NDJSON streaming on `owa-graph batch`.** Batch is the one
   long-running action; needs the streaming contract under
   `--json`.
7. **Reserved-key compliance.** Graph responses can legitimately
   contain an `ok` field at the top level (`{"value": [...]}` is
   safe, but raw passthrough of an arbitrary Graph response is
   not). Audit and wrap raw passthrough responses.
8. **`--pretty` spelling audit** across all eight binaries; confirm
   no `--format pretty` aliases remain.

### minor
9. **Redaction sentinel test** specifically for message bodies in
   `owa-mail send/reply/forward` failure paths.
10. **`owa-doctor` schema alignment** with the aggregator JSON
    shape `mnem doctor` will consume.

---

## mnem (`damsleth/mnem`, this repo)

**Target**: 0.1.0 in Phase 3a.

This repo is greenfield. Phase 1 deliverables (README, SUITE,
CONVENTIONS) are in place. No code yet; the router lands in 3a.

The conformance table at the bottom of CONVENTIONS.md defines what
`mnem` itself must implement; nothing to audit retroactively.

---

## Cross-cutting issues

These are not per-repo but apply to the suite as a whole:

1. **Shared `redact()` utility.** Each tool currently has ad-hoc
   logging; the spec requires a common redaction shape. Decide
   whether this lives in a shared package (`mnem-conventions`?) or
   is copy-pasted into each repo with a regression test ensuring
   sync.
2. **Doctor schema package.** The doctor JSON shape is shared
   across every binary. Same decision: shared package or
   copy-paste with tests.
3. **Action envelope helpers.** Three lines of boilerplate per
   action command across ~50 commands is enough to justify a
   shared `emit_envelope()` helper.

Recommendation: create `mnem-conventions` as a small shared Python
package shipped from this repo. Each tool depends on it. Phase 3a
work; track as an issue against `damsleth/mnem`.
