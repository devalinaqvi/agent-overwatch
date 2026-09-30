# Agent Overwatch — commands guide

Every command you'll use, grouped by task. Replace `./` with the path to your
Agent Overwatch checkout. Two agents are supported: **Claude Code** (default) and
**OpenAI Codex CLI** (`--adapter codex`, or the `install-codex.sh` installer).

## Install / uninstall

| Command | What it does |
|---|---|
| `./install.sh` | Wire the guard into **this project** (`./.claude/settings.json`). Backup kept. |
| `./install.sh --user` | Wire it for **every** project (`~/.claude/settings.json`). |
| `./install-codex.sh` / `--user` | Same, for Codex (`.codex/hooks.json`). **Then trust it — see below.** |
| `sudo ./install-managed.sh` | **Managed (tamper-resistant) tier**: root-owned settings the agent can't disable, plus the OS sandbox backstop. Needs `sudo`. |
| `./uninstall.sh` / `--user` | Remove Agent Overwatch from Claude settings (one scope per run). Keeps other hooks. |
| `./uninstall.sh --codex [--user]` | Remove the Codex hook. |

After any install/uninstall, **restart your agent sessions** — settings load at
session start.

## Codex: trust the hook (required)

Full walkthrough (CLI trust + how trust is stored): **[CODEX-SETUP.md](CODEX-SETUP.md)**.

Codex **ignores untrusted hooks**, so after `install-codex.sh` you must trust it,
or Codex will keep running unguarded:

1. Start Codex CLI.
2. Open **`/hooks`**.
3. Select the Agent Overwatch `PreToolUse` hook and toggle it to **Trusted**.
4. Restart the session. (Project installs also need the project trusted.)

Verify: `./bin/interlock --adapter codex status` (reports INACTIVE / UNKNOWN /
READY), then in a scratch dir with a dummy `.env`, ask Codex to `cat .env` —
expect an Agent Overwatch `SEC-001` denial and a matching audit record.

## Everyday operation

| Command | What it does |
|---|---|
| `./bin/interlock status` | Where it's wired, tier, current pause/bypass state, last 10 decisions. |
| `./bin/interlock selftest` | Feed the hook a canned `.env` read; expect `deny SEC-001`. |
| `./bin/interlock tail` | Follow today's decision log live. |
| `./bin/interlock show` | Is it paused/bypassed? Until when? |
| `./bin/interlock --adapter codex status` | Codex-specific: queries Codex hook discovery (trust/enabled). |

Audit log: `~/.interlock/audit/YYYY-MM-DD.jsonl` (override with
`INTERLOCK_AUDIT_DIR`). Secrets are redacted before anything is written.

## Temporarily standing down

**User-tier pause** (no sudo — relaxes the hook layer for your sessions):

| Command | What it does |
|---|---|
| `./bin/interlock pause 30m` | Stand down all rules for 30 min, then auto-resume. |
| `./bin/interlock pause 1h GIT-* PKG-*` | Pause only push/publish rules for 1 hour. |
| `./bin/interlock resume` | Resume enforcing now. |

**Managed master bypass** (needs sudo — relaxes *all* layers, for the tamper-resistant tier):

| Command | What it does |
|---|---|
| `sudo ./bin/interlock bypass 30m` | Relax deny rules + hook + sandbox reads for 30 min (auto-restores). Network stays isolated. |
| `sudo ./bin/interlock bypass 30m --network` | Also relax the sandbox **network** isolation (widest bypass). |
| `sudo ./bin/interlock enforce` | End the bypass now, restore all layers. |

Both are **time-boxed** (max 12h, auto-restore), **still audited** (bypassed
actions log as `paused-bypass`), and **human-only** (the agent is denied the
command and can't write the state files). **You must restart your agent sessions**
after a bypass or `enforce` so the deny-rules/sandbox layers reload.

## Testing

| Command | What it does |
|---|---|
| `python3 -m unittest discover -s tests -q` | Full suite (engine + Claude + Codex adapters). |
| `python3 tests/codex_live_smoke.py` | Optional live check that Codex actually enforces (needs a trusted hook + model access; uses a fake secret). |

## Environment variables

| Var | Purpose |
|---|---|
| `INTERLOCK_POLICY` | Use a different policy file. |
| `INTERLOCK_AUDIT_DIR` | Move the audit log. |
| `INTERLOCK_STATE` | Move the user-tier pause flag (tests). |
| `INTERLOCK_BYPASS` | Move the managed bypass flag (tests). |
| `CODEX_HOME` | Honored by the Codex installer for a custom Codex config dir. |

See [CUSTOMIZING.md](CUSTOMIZING.md) for editing the policy, [SECURITY.md](SECURITY.md)
for the threat model and limits, and [ADAPTERS.md](ADAPTERS.md) to add an agent.
