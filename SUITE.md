# Suite architecture

The polished narrative of how the four tools fit together. If
`README.md` is the elevator pitch, this is the floor plan.

## The four components

Each component is its own repo with its own release cadence. `mnem`
declares minimum versions of each; nothing else is synchronized.

| Component | Repo | Binaries | Role |
| --- | --- | --- | --- |
| YAAMS | [`damsleth/yaams`](https://github.com/damsleth/yaams) | `yaams` | Tier 1 raw memory store |
| Cognitive Ledger | [`damsleth/cognitive-ledger`](https://github.com/damsleth/cognitive-ledger) | `ledger`, `ledger-obsidian`, `sheep` | Tier 2 curated atomic notes engine |
| owa-piggy | [`damsleth/owa-piggy`](https://github.com/damsleth/owa-piggy) | `owa-piggy` | M365 auth broker |
| owa-tools | [`damsleth/owa-tools`](https://github.com/damsleth/owa-tools) | `owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive` | M365 read/write CLIs |
| **mnem** (this repo) | `damsleth/mnem` | `mnem` | Suite hub + meta-CLI |

## Two-tier memory

Each tier has an **engine** (public code) and a **store** (private,
your data, never committed).

```
Tier 1 (raw, high-volume)              Tier 2 (curated, atomic)
┌────────────────────────────┐         ┌────────────────────────────┐
│ engine: YAAMS              │         │ engine: cognitive-ledger   │
│                            │         │                            │
│ store:  YAAMS SQLite db    │ ──────► │ store:  ledger notes       │
│         (private,          │ promote │         (private, markdown │
│          db_path)          │         │          tree)             │
└────────────────────────────┘         └────────────────────────────┘
              ▲                                       ▲
              │ adapters                              │
              │                                       │
   ┌──────────┴──────────┐                  ┌─────────┴──────────┐
   │ iMessage, Signal,   │                  │ Obsidian, the      │
   │ Apple Mail, GitHub, │                  │ ledger's own       │
   │ owa-piggy, ...      │                  │ markdown tree      │
   └─────────────────────┘                  └────────────────────┘
```

- **YAAMS** is the firehose: ingest everything, normalize to one
  schema, embed, query across the lot.
- **cognitive-ledger** is the keep-forever layer: atomic notes
  (facts, preferences, goals, open loops, concepts, identity) you
  curate by hand or by promoting items out of YAAMS.
- They fuse at query time: `yaams query` reads the ledger as a Tier 2
  source via the `tier2_ledger` adapter and applies a small boost so
  curated notes outrank raw ingest when both match.

This diagram is duplicated, intentionally, from `YAAMS/AGENTS.md`.
The YAAMS copy is the binding entry point for agents working in that
repo; this copy is the binding entry point for the suite as a whole.

## M365 surface

`owa-piggy` and `owa-tools` are a separate package pair, not a
monorepo. The split is by trust boundary, not by size:

- `owa-piggy` is the only thing that touches your OWA session and
  holds refresh tokens. Tokens live in the OS keychain.
- `owa-tools` ships eight read/write CLIs that **borrow** access
  tokens from `owa-piggy` over a local socket. The tools never
  import `owa-piggy` and never see refresh tokens.

YAAMS uses `owa-piggy` directly for the Teams and calendar adapters.
`mnem mail` and `mnem calendar` route through `owa-tools`.

## Data flow

```
                                    mnem
                                     │
       ┌─────────────────┬───────────┴──────────┬─────────────────┐
       │                 │                      │                 │
       ▼                 ▼                      ▼                 ▼
   yaams ingest    yaams query          owa-* read/write       ledger
       │                 │                      │                 │
       ├─ iMessage       │                      ├─ owa-cal        │
       ├─ Apple Mail     │                      ├─ owa-mail       │
       ├─ Signal         │                      ├─ owa-graph      │
       ├─ GitHub         │                      ├─ owa-people     │
       ├─ owa-piggy      │                      └─ ...            │
       │  (Teams,        │                                        │
       │   calendar)     │                                        │
       └─ tier2_ledger ◄─┴─ reads ledger as Tier 2 source ────────┘
```

Ingestion is one-way (sources → YAAMS). Promotion is one-way (YAAMS
→ ledger, gated by `promote review`). Queries fuse both tiers and
cite back to the source items.

## Install model

One brew install pulls the whole suite via formula dependencies:

```bash
brew install damsleth/tap/mnem
```

The `mnem` formula declares minimum versions of `yaams`,
`cognitive-ledger`, `owa-piggy`, and `owa-tools`. Brew resolves the
graph and installs whatever isn't already present.

If you already have any of the underlying tools installed and on a
recent enough version, brew leaves them alone. After install, `mnem
init` is the one wizard that wires up sources, generates configs,
and runs a dry-run so you can see what's about to be ingested.

## CLI contract

Every binary in the suite conforms to [CONVENTIONS.md](CONVENTIONS.md):

- Output classes (data / action / interactive) with `destructive` as
  an orthogonal modifier.
- Action envelope schema with an `ok` invariant tied to exit code.
- NDJSON streaming schema for long-running action commands run with
  `--json`.
- Reserved-key contract on data results so machine consumers always
  have a parseable JSON value.
- Single, suite-wide config precedence chain. `MNEM_HOME` is the
  shared **data** root; config stays under `$XDG_CONFIG_HOME/mnem/`.
- Standardized exit codes: 0 ok, 1 user error, 2 transient, 3 auth,
  4 not found, 5 partial success.

Skill authors target `mnem` instead of individual binaries. Power
users can still hit `yaams query --json` or `owa-cal events
--today --json` directly and get byte-identical output.

## Skills boundary

```
                    mnem (meta-CLI)
                          │
              wraps │ (one direction)
                          ▼
        yaams · cognitive-ledger · owa-piggy · owa-tools
                          ▲
              wraps │ (skills wrap mnem, not the other way)
                          │
       damsleth/SKILLS (public)        damsleth/SKILLS-private
       ├── /memory (routes mnem)       ├── cj-mnem
       ├── cj-yaams                    ├── cj-did
       ├── /notes                      ├── cj-timereg
       └── ...                         └── cj-weekly-review
```

`mnem` wraps CLIs only. Skills wrap `mnem`. The public/private split
keeps reusable abstractions discoverable while personal-infra skills
stay in a separate repo with a separate installer.

## Releases

Independent semver per tool. `mnem` declares minimums. After the
Phase 2c conformance bump, every tool returns to independent cadence.

```
mnem 0.1.0 requires:
  yaams >= 0.1.3
  cognitive-ledger >= 0.2.3
  owa-piggy >= 0.9.0
  owa-tools >= 0.1.2
```

Source of truth: `src/mnem/_minimums.py`. Keep this block in sync; CI enforces.

A breaking change in any underlying tool bumps that tool's major and
`mnem` bumps its declared minimum on the next release; consumers see
one suite version, not five.
