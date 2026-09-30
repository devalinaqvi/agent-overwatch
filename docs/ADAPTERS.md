# Adapters — supporting more agents

Agent Overwatch is split into two parts:

- **The engine** (`interlock/engine.py`) — agent-agnostic. It evaluates an
  abstract **Action** against the policy and returns a decision. Every rule lives
  here, written once.
- **An adapter** (`interlock/adapters/<agent>.py`) — agent-specific. It knows one
  agent's event format and response format, and nothing about policy.

Supporting a new agent means writing one adapter. The engine does not change.

## The Action contract

An adapter's job is to turn an agent's "about to call a tool" event into this
plain dict:

```python
{
  "kind":    "file" | "files" | "bash" | "mcp" | "tool",
  "paths":   ["<path>"],          # files: every patch source/destination (writes)
  "access":  "read" | "write",   # file only
  "path":    "<path>",           # file only
  "command": "<shell command>",  # bash only
  "tool":    "<original tool name>",
  "params":  { ... },            # the tool's input params
  "cwd":     "<working directory>",
}
```

`engine.evaluate(policy, action)` returns `(decision, rule_id, reason, target)`
where `decision` is `deny` | `ask` | `defer`. `defer` means "no opinion — let the
agent's own permission flow decide". The engine never says `allow`.

## The adapter contract

Subclass `interlock.adapters.base.Adapter`:

```python
class Adapter:
    name = "your-agent"
    FAIL_CLOSED_EXIT = 2       # the exit code that makes THIS agent hard-block

    def parse(self, event):    # -> Action dict, or None if not a tool call
        ...
    def context(self, event):  # -> audit fields (session/agent/tool/cwd + adapter)
        ...
    def respond(self, decision, rule_id, reason):  # emit the agent's native deny/ask
        ...
    def is_config_event(self, event):  # optional: audit-only config changes
        return False
```

Then add an entrypoint under `bin/` that reads the agent's event, runs
`engine.evaluate`, calls `adapter.respond`, and — critically — **exits with
`FAIL_CLOSED_EXIT` on any error** so a broken guard blocks instead of passing
through. Copy `bin/interlock-claude-code` as a template.

## The hard requirement: a pre-execution block

An adapter can only be written for an agent that lets you **veto a tool call
before it runs**. This is the whole premise — a guard that finds out afterward is
not a guard. Concretely the agent must offer *both*:

1. a **pre-tool hook** that fires before the action executes, and
2. a way for that hook to **block** the action (a decision signal and/or a
   blocking exit code).

Claude Code provides both (its `PreToolUse` hook + `permissionDecision` + the
exit-2 block). Some agents provide neither, or only post-hoc observation — those
cannot be guarded by this design. For them, confine the whole agent process in an
**OS sandbox** instead; that is a different tool, not an Agent Overwatch adapter.

Before writing an adapter, confirm against the target agent's *official* docs
that a blocking pre-tool hook exists, and what its exact input/response format and
failure semantics are. Do not assume a nonzero exit blocks — verify it.

## Checklist for a new adapter

- [ ] Confirmed the agent has a blocking pre-tool hook (cite its docs).
- [ ] `parse()` maps every tool the agent can call to an Action `kind`.
- [ ] `normalize_decision()` maps unsupported decisions before audit/response.
      Codex maps `ask` to `deny`; it cannot force a native approval prompt.
- [ ] `respond()` emits a supported blocking response.
- [ ] `FAIL_CLOSED_EXIT` is the agent's real hard-block code, verified.
- [ ] An entrypoint under `bin/` that exits fail-closed on error.
- [ ] `install.sh`/`uninstall.sh` support wiring it in and out.
- [ ] Adapter tests that run the entrypoint as a subprocess (copy
      `tests/test_claude_code_adapter.py`), plus the shared engine tests still pass.
- [ ] Docs updated honestly, including anything the adapter *can't* guarantee.

## Codex-specific behavior

The [official contract](https://learn.chatgpt.com/docs/hooks) reports shell tools
(including unified exec) as `Bash`, with a string `tool_input.command`. Native
`apply_patch` events also carry their patch in `tool_input.command`. Matcher
aliases such as `Edit` do not change the patch event's canonical tool name.

The adapter extracts every patch source and move destination into a `files`
action, then the engine checks each path. Unknown patch syntax and malformed
shell inputs exit 2. Raw shell aliases and argv arrays are accepted for
compatibility; they are not a substitute for canonical hook fixtures.

`AUDIT_ALL = True` records Codex deferrals too. Policy pauses are applied before
`normalize_decision`, so explicitly paused ask rules still defer; otherwise asks
are audited and returned as denies. Claude continues to receive asks unchanged.

An installed hook must be reviewed/trusted in `/hooks`. A passing adapter test,
a hook registration, or exit-2 handling cannot guarantee enforcement if Codex
skips the hook, cannot launch it, times it out, or does not hook that tool path.
