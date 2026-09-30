# How Agent Overwatch works

## No daemon — a rule consulted per tool call

Nothing runs in the background. The installer adds a `PreToolUse` hook to a Claude
Code settings file, pointing at `bin/interlock-claude-code`. At session start
Claude Code reads it; before every tool call it runs that entrypoint.

## One tool call, start to finish

1. Claude Code runs `bin/interlock-claude-code` with the event JSON on stdin.
2. The **Claude Code adapter** (`interlock/adapters/claude_code.py`) turns that
   event into an abstract **Action**.
3. The **engine** (`interlock/engine.py`) evaluates the Action against
   `policy/policy.json` and returns `deny` / `ask` / `defer`.
4. A redacted line is written to the audit log.
5. The adapter turns the decision back into Claude Code's response:
   | Decision | Claude Code does |
   |---|---|
   | `deny` | refuses the call; the agent sees the rule id + reason |
   | `ask` | shows you a permission prompt |
   | `defer` | proceeds through the normal permission flow |
   | *(exit 2)* | **hard block** — used for any internal error (fail-closed) |
6. The process exits. A fresh one runs for the next call — nothing persistent to
   disable or kill.

The engine never returns `allow`; it only blocks, asks, or steps aside, so your
own permission rules still govern anything it defers.

## Why the split matters

The engine is agent-agnostic — it operates on the abstract Action, not on Claude
Code types. The Claude-specific parts (reading the event, emitting
`permissionDecision`, the exit-2 block) live only in the adapter and the
entrypoint. That means the *rules* are written once and any future adapter reuses
them. See [ADAPTERS.md](ADAPTERS.md).

## Fail-closed

Claude Code's contract: exit 2 always blocks; a hook that times out, crashes, or
prints malformed JSON on exit 0 fails *open*. So the entrypoint wraps everything
in a `try/except` that exits 2 on any error — a missing policy, malformed input,
or an unwritable audit log all become a hard block. The evaluator is stdlib-only
and fast to stay well under the hook timeout.

## Layering (recommended)

Agent Overwatch is the text-inspection layer. Pair it with the agent's own permission
`deny` rules and an OS sandbox so secrets are *absent* from the filesystem — which
holds even when a command is obfuscated past the text layer. See
[SECURITY.md](SECURITY.md).
