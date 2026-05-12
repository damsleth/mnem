# mnem

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![status](https://img.shields.io/badge/status-pre--release-orange)

**A local-first memory suite for AI agents.** One install gets you a
two-tier memory store, an M365 read/write surface, and a single CLI
that ties them together. Your data stays on your machine.

`mnem` is the umbrella over four independent tools that already work
on their own. The umbrella adds one verb surface, one install command,
one place to find what is in the box.

```
                            mnem (meta-CLI + suite hub)
                                       |
              +------------------------+------------------------+
              |               |                |                |
            YAAMS    cognitive-ledger    owa-piggy        owa-tools
         (Tier 1 raw)   (Tier 2 curated)  (M365 auth)   (M365 read/write)
```

## What's in the box

| Tool | Purpose | Binaries |
| --- | --- | --- |
| [**YAAMS**](https://github.com/damsleth/yaams) | Tier 1 raw memory store - every iMessage, mail, calendar event, GitHub issue, ingested and queryable from a single SQLite file. | `yaams` |
| [**cognitive-ledger**](https://github.com/damsleth/cognitive-ledger) | Tier 2 curated atomic notes engine - the gems you promote out of YAAMS and keep forever as markdown with frontmatter. | `ledger`, `ledger-obsidian`, `sheep` |
| [**owa-piggy**](https://github.com/damsleth/owa-piggy) | Microsoft 365 auth broker - turns your existing Outlook Web session into a reusable token. No app registration. | `owa-piggy` |
| [**owa-tools**](https://github.com/damsleth/owa-tools) | M365 read/write CLI suite - calendar, mail, Graph, OneDrive, scheduling, people lookup, all JSON-by-default. | `owa`, `owa-cal`, `owa-mail`, `owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive` |

`mnem` itself adds one more binary that routes the verbs above into
a single user-facing surface.

## Install

```bash
brew install damsleth/tap/mnem
```

The Homebrew formula pulls the whole suite via dependencies. On
PyPI the package is `mnem-suite` (both `mnem` and `mnem-cli` were
already taken on PyPI by unrelated projects); the installed binary
is still `mnem`:

```bash
pipx install mnem-suite
```

Then:

```bash
mnem init           # detect sources, write config, run a dry-run
mnem hello          # one-screen tour of the verbs
mnem doctor         # health check across every tool
```

`mnem init` is idempotent and never edits your dotfiles.

## What can it do

```bash
mnem query "what did we decide at the brand kickoff?"
mnem ingest                       # all configured sources, partial-success tolerant
mnem promote review               # interactive: promote YAAMS gems to the ledger
mnem mail send --to ...           # owa-mail wrapper
mnem calendar today               # owa-cal wrapper
mnem ledger init                  # bootstrap a new ledger
mnem auth status                  # owa-piggy wrapper
mnem doctor                       # aggregate health check
mnem version                      # own version + observed component versions
```

Every JSON-capable command accepts `--json` (machine mode) and
`--pretty` (human rendering). Exit codes are predictable per
[CONVENTIONS.md](CONVENTIONS.md): 0 ok, 1 user error, 2 transient,
3 auth, 4 not found, 5 partial success.

## First day

1. `brew install damsleth/tap/mnem`
2. `mnem init` - the wizard probes for iMessage, Apple Mail, Signal,
   GitHub, owa-piggy, Obsidian, and an existing cognitive-ledger. It
   enables what it finds and writes `enabled: false` with a hint for
   what it doesn't.
3. `mnem ingest` - first run downloads embedding models (~2 GB) with
   a prompt before any download.
4. `mnem query "..."` - ask the suite anything.

See [SUITE.md](SUITE.md) for the full data flow and architecture, and
[CONVENTIONS.md](CONVENTIONS.md) for the CLI contract every tool in
the suite conforms to.

## Skills

Two agent skill repos sit on top of `mnem`:

- [`damsleth/SKILLS`](https://github.com/damsleth/SKILLS) - public,
  reusable agent skills. Includes `/memory`, which routes through
  `mnem`.
- `damsleth/SKILLS-private` - personal-infra `cj-*` skills (timereg,
  did, weekly review). Same installer pattern; private repo.

Skills wrap `mnem`. `mnem` does not call skills. One direction, no
circular dependencies.

## License

MIT. See [LICENSE](LICENSE).
