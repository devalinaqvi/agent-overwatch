# Codex setup & trusting the hook

OpenAI Codex CLI runs `PreToolUse` hooks, but **it ignores hooks it doesn't
trust**. So Agent Overwatch has two steps on Codex: **install** the hook, then
**trust** it. Until it's trusted, Codex runs unguarded even though the hook is
listed.

Do this before you rely on Codex enforcement.

## 1. Install the hook

```bash
./install-codex.sh           # this project      → ./.codex/hooks.json
./install-codex.sh --user    # every project     → ~/.codex/hooks.json
```

The installer honors `CODEX_HOME` if set; otherwise it uses `~/.codex`. It adds
one `PreToolUse` entry pointing at `bin/interlock-codex` and keeps a backup of the
previous hooks file. It does **not** (and can't) trust the hook for you.

## 2. Trust the hook

### From the CLI (recommended)

1. Start Codex CLI.
2. Open the **`/hooks`** screen.
3. Find the Agent Overwatch `PreToolUse` hook and set it to **Trusted**.
4. **Restart the session.** A running session keeps the trust state it started with.

For a **project** install you must also trust the project, and `features.hooks`
must not be disabled.

### How trust is stored (the "manual" view)

There is no useful hand-edit shortcut, and it helps to know why. When you trust a
hook, Codex records it in **`~/.codex/config.toml`** under a `[hooks.state]`
table — as a **`trusted_hash`** bound to that exact hook definition (the hook file
path plus the hook's contents):

```toml
[hooks.state]
[hooks.state."~/.codex/hooks.json:pre_tool_use:0:0"]
trusted_hash = "…"     # computed by Codex, not by you
```

Two consequences:

- **Editing `hooks.json` by hand does not grant trust.** The hash won't exist (or
  won't match), so Codex still treats the hook as untrusted. Use `/hooks`.
- **Changing the hook re-arms the trust gate.** If the hook definition changes
  (e.g. you reinstall or edit the command), the old hash no longer matches and you
  must trust it again in `/hooks`.

So "trust it manually" in practice means: run `/hooks` and approve — that's the
supported mechanism that writes the correct `trusted_hash`.

## 3. Verify it's active

```bash
./bin/interlock --adapter codex status
```

Reports `INACTIVE` (disabled/untrusted/missing), `UNKNOWN` (discovery failed), or
`READY` (an enabled, trusted hook was found). Exit codes 1 / 2 / 0. `READY` means
the wiring is right — it does not by itself prove a live block.

## 4. Prove a real block

In a throwaway directory with a **fake** `.env`:

```bash
mkdir -p /tmp/ao-smoke && printf 'API_KEY=fake-not-a-real-secret\n' > /tmp/ao-smoke/.env
# start Codex in /tmp/ao-smoke, then ask it: "cat .env"
```

Expect an **Agent Overwatch** `SEC-001` or `SEC-030` denial and a matching record
in `./bin/interlock tail`. A model refusal or a sandbox error alone does **not**
prove the hook ran — confirm in the audit log.

`python3 tests/codex_live_smoke.py` automates this against your installed Codex
(needs a trusted hook + model access, uses a fake secret, and never changes your
trust or policy).

## Notes & limits

- Codex has **no** `ask`: policy `ask` decisions become **deny** on Codex, with a
  reason saying a human must perform the action or pause that rule.
- Codex hooks **fail open on timeout** — a hook that's slow, crashing, disabled,
  or untrusted means the call proceeds. Keep the policy fast and watch the audit.
- Coverage: canonical `Bash` events, raw shell aliases, every `apply_patch`
  add/update/delete/move path, and MCP policy checks. Patch audit entries record
  target paths, not patch bodies. Hosted tools and input sent to an existing
  `write_stdin` session are outside `PreToolUse` coverage.
- The desktop app must use the same local Codex config as the CLI; a CLI trust
  check can't prove an already-running desktop session loaded it. Restart it.
