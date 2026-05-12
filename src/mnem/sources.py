"""Source detection for `mnem init`.

Each probe is a pure function that returns a small structured doc.
The wizard runs every probe, writes the result into config (with
`enabled: true/false` + a hint), and lets the user override before
the dry-run.

No probe is allowed to touch the network, prompt the user, or
modify state. They look at the filesystem and at $PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProbeResult:
  name: str
  enabled: bool
  reason: str  # short human-readable explanation
  hint: str | None = None  # what the user should do to enable
  extras: dict[str, Any] = field(default_factory=dict)  # paths, profile counts, etc

  def to_dict(self) -> dict:
    out = {
      "name": self.name,
      "enabled": self.enabled,
      "reason": self.reason,
    }
    if self.hint:
      out["hint"] = self.hint
    if self.extras:
      out["extras"] = dict(self.extras)
    return out


def probe_imessage() -> ProbeResult:
  db = Path.home() / "Library" / "Messages" / "chat.db"
  if not db.is_file():
    return ProbeResult(
      "imessage",
      enabled=False,
      reason="chat.db not found",
      hint="iMessage is macOS-only; not available on this system.",
    )
  # Existence is necessary but not sufficient - Terminal/Python needs
  # Full Disk Access to read it. We don't attempt to read here.
  return ProbeResult(
    "imessage",
    enabled=True,
    reason="chat.db found at ~/Library/Messages/chat.db",
    hint=(
      "If ingest later returns exit 3, grant your terminal Full Disk "
      "Access in System Settings -> Privacy & Security."
    ),
    extras={"chat_db_path": str(db)},
  )


def probe_apple_mail() -> ProbeResult:
  candidates = list((Path.home() / "Library" / "Mail").glob("V*"))
  if not candidates:
    return ProbeResult(
      "email",
      enabled=False,
      reason="~/Library/Mail/V* not present",
      hint="Apple Mail not configured; or run mail.app at least once.",
    )
  return ProbeResult(
    "email",
    enabled=True,
    reason=f"Apple Mail store found ({len(candidates)} version dirs)",
    extras={"mail_root": str(candidates[-1])},
  )


def probe_signal() -> ProbeResult:
  signal_dir = Path.home() / "Library" / "Application Support" / "Signal"
  if not signal_dir.is_dir():
    return ProbeResult(
      "signal",
      enabled=False,
      reason="Signal Desktop not installed",
      hint="Install Signal Desktop and sign in at least once.",
    )
  if shutil.which("sqlcipher") is None:
    return ProbeResult(
      "signal",
      enabled=False,
      reason="Signal data present but sqlcipher missing on PATH",
      hint="brew install sqlcipher",
      extras={"signal_dir": str(signal_dir)},
    )
  return ProbeResult(
    "signal",
    enabled=True,
    reason="Signal Desktop present and sqlcipher available",
    extras={"signal_dir": str(signal_dir)},
  )


def probe_github() -> ProbeResult:
  if shutil.which("gh") is None:
    return ProbeResult(
      "github",
      enabled=False,
      reason="gh CLI not on PATH",
      hint="brew install gh && gh auth login",
    )
  # `gh auth token` is the fastest non-prompting check.
  result = subprocess.run(
    ["gh", "auth", "token"], capture_output=True, text=True, timeout=5,
  )
  if result.returncode != 0 or not result.stdout.strip():
    return ProbeResult(
      "github",
      enabled=False,
      reason="gh installed but no auth token",
      hint="gh auth login",
    )
  # Best-effort username lookup so the generated config doesn't ship with
  # an empty `username:` (which causes ingest to 404 against /users//events).
  username = ""
  who = subprocess.run(
    ["gh", "api", "user", "--jq", ".login"],
    capture_output=True, text=True, timeout=5,
  )
  if who.returncode == 0:
    username = who.stdout.strip()
  extras = {"username": username} if username else {}
  reason = f"gh authenticated as {username}" if username else "gh authenticated; token reachable"
  return ProbeResult(
    "github",
    enabled=True,
    reason=reason,
    extras=extras,
  )


def probe_owa_piggy() -> ProbeResult:
  if shutil.which("owa-piggy") is None:
    return ProbeResult(
      "owa_piggy",
      enabled=False,
      reason="owa-piggy not on PATH",
      hint="brew install damsleth/tap/owa-piggy",
    )
  # Reach for the data-class profiles --json. Avoid running setup or
  # anything stateful.
  result = subprocess.run(
    ["owa-piggy", "profiles", "--json"],
    capture_output=True, text=True, timeout=5,
  )
  if result.returncode != 0:
    return ProbeResult(
      "owa_piggy",
      enabled=False,
      reason="owa-piggy installed but `profiles --json` failed",
      hint="owa-piggy setup --profile <alias> --email <addr>",
    )
  import json as _json
  try:
    doc = _json.loads(result.stdout)
  except _json.JSONDecodeError:
    return ProbeResult(
      "owa_piggy",
      enabled=False,
      reason="owa-piggy profiles output not parseable",
    )
  profiles = doc.get("profiles") or []
  if not profiles:
    return ProbeResult(
      "owa_piggy",
      enabled=False,
      reason="no owa-piggy profiles configured yet",
      hint="owa-piggy setup --profile <alias> --email <addr>",
    )
  return ProbeResult(
    "owa_piggy",
    enabled=True,
    reason=f"{len(profiles)} profile(s) configured",
    extras={"profiles": [p["alias"] for p in profiles]},
  )


def probe_obsidian() -> ProbeResult:
  candidates = [
    Path.home() / "Documents" / "Obsidian",
    Path.home() / "notes",
    Path.home() / "Notes",
    Path.home() / "Obsidian",
  ]
  for c in candidates:
    if c.is_dir():
      return ProbeResult(
        "notes",
        enabled=True,
        reason=f"vault detected at {c}",
        extras={"vault_path": str(c)},
      )
  return ProbeResult(
    "notes",
    enabled=False,
    reason="no Obsidian-style vault detected at the usual locations",
    hint=(
      "Set ingest.notes.vault_path in config.yaml manually if your "
      "vault lives elsewhere."
    ),
  )


def probe_existing_yaams_config() -> ProbeResult:
  """Detect a pre-existing standalone yaams config the user already curates.

  Looks at the canonical yaams location (`$XDG_CONFIG_HOME/yaams/config.yaml`).
  If found, the wizard will offer to reuse it in place rather than overwrite
  it with mnem's freshly-generated stub. Parsing is best-effort and never
  fatal: if PyYAML isn't importable we still report the path so the wizard
  can offer the reuse-in-place path.
  """
  xdg = os.environ.get("XDG_CONFIG_HOME")
  base = Path(xdg) if xdg else Path.home() / ".config"
  cfg = base / "yaams" / "config.yaml"
  if not cfg.is_file():
    return ProbeResult(
      "existing_yaams_config",
      enabled=False,
      reason="no standalone yaams config at ~/.config/yaams/config.yaml",
    )
  parsed: dict[str, Any] = {}
  parse_note: str | None = None
  try:
    import yaml  # type: ignore
    parsed = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
  except ModuleNotFoundError:
    parse_note = "PyYAML not importable; reuse-in-place still works"
  except Exception as exc:  # noqa: BLE001
    parse_note = f"yaml parse failed: {exc}"
  extras: dict[str, Any] = {"path": str(cfg)}
  if parsed:
    extras["parsed"] = parsed
  if parse_note:
    extras["parse_note"] = parse_note
  return ProbeResult(
    "existing_yaams_config",
    enabled=True,
    reason=f"existing yaams config at {cfg}",
    extras=extras,
  )


def probe_cognitive_ledger() -> ProbeResult:
  if shutil.which("ledger") is None:
    return ProbeResult(
      "tier2_ledger",
      enabled=False,
      reason="ledger not on PATH",
      hint="brew install damsleth/tap/cognitive-ledger",
    )
  result = subprocess.run(
    ["ledger", "paths", "--json"],
    capture_output=True, text=True, timeout=5,
  )
  if result.returncode != 0:
    return ProbeResult(
      "tier2_ledger",
      enabled=False,
      reason="ledger installed but `paths --json` failed",
      hint="ledger init --root ~/.config/cognitive-ledger",
    )
  import json as _json
  try:
    paths = _json.loads(result.stdout)
  except _json.JSONDecodeError:
    return ProbeResult(
      "tier2_ledger",
      enabled=False,
      reason="ledger paths output not parseable",
    )
  notes_dir = paths.get("ledger_notes_dir")
  if not notes_dir or not Path(notes_dir).is_dir():
    return ProbeResult(
      "tier2_ledger",
      enabled=False,
      reason=f"ledger_notes_dir does not exist ({notes_dir})",
      hint="ledger init --root <root>",
    )
  return ProbeResult(
    "tier2_ledger",
    enabled=True,
    reason=f"ledger notes at {notes_dir}",
    extras={"notes_path": notes_dir},
  )


# Single entry point the wizard calls.
_ALL_PROBES = [
  probe_imessage,
  probe_apple_mail,
  probe_signal,
  probe_github,
  probe_owa_piggy,
  probe_obsidian,
  probe_cognitive_ledger,
  probe_existing_yaams_config,
]


def run_all() -> list[ProbeResult]:
  results = []
  for probe in _ALL_PROBES:
    try:
      results.append(probe())
    except Exception as exc:  # noqa: BLE001 - probe should never abort init
      results.append(ProbeResult(
        name=probe.__name__.removeprefix("probe_"),
        enabled=False,
        reason=f"probe crashed: {exc}",
      ))
  return results
