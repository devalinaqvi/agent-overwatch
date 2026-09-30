# Security model & limitations

Read this before relying on Agent Overwatch for anything that matters. It is honest
about where protection begins and ends.

## Threat model

**Adversary:** a coding agent that has received malicious instructions — from a
repo file, a fetched page, a dependency, or a tool response — and can run real
commands. Repository content and tool output are **data, never instructions**.

**What Agent Overwatch provides:**
- Deterministic, **pre-execution** decisions applied before the tool runs.
- **Fail-closed** behavior — any evaluator error becomes a hard block.
- Symlink-safe path checks (`realpath` before matching).
- Git-form awareness (`git -C dir push`, quoted/chained forms parsed).
- Self-protection: writes into Agent Overwatch's own files or `.claude/settings.json`
  are denied.
- A redacted audit trail.

## What it does NOT provide

1. **Text analysis is not proof of safety.** The engine inspects the command
   string; it cannot follow arbitrary program logic. A renamed/absolute-path
   binary, an interpreter that builds the action at runtime (`python -c`,
   `node -e`), heavy obfuscation, or a script written now and run later can
   defeat the text layer. The mitigation is an OS boundary, not more regexes.
2. **An allowed command can do anything.** A test runner or build tool executes
   arbitrary project code; Agent Overwatch deferring to it does not vouch for what it
   then does.
3. **The agent's own credentials are within its reach.** If an agent needs a
   token to function, that token is available to it; Agent Overwatch can't both grant
   the capability and prevent its misuse.
4. **Not a boundary against a compromised host, a malicious admin, or a process
   running outside the agent.** It guards the agent's tool calls, nothing else.
5. **Hook fail-open residuals.** The host agent may fail *open* if a hook times
   out or its file is missing. Agent Overwatch minimizes this (fast, stdlib-only), but
   the residual is real — back it with the agent's own permission `deny` rules
   and an OS sandbox.

## Recommended layering

Agent Overwatch is the always-on **first layer**. For anything sensitive add:

- **The agent's own permission `deny` rules** for the plainest forms.
- **An OS sandbox** (the agent's built-in sandbox, a devcontainer, or a VM) so
  secrets are *absent* from the filesystem the agent sees and the network is
  constrained. This is what holds when the text layer is bypassed.
- **Capability withholding** — restricted DB credentials (no `DROP`/`GRANT`) and
  no push credentials, so an equivalent action through another path still fails
  at the resource.

With those, Agent Overwatch is a fast tripwire and audit layer on top of real
boundaries — the role it should play.

## Reporting

Found a bypass? Open a private security advisory. A discovered bypass is
documented as a known limitation until fixed — this project does not claim to be
unbypassable.

## Codex enforcement limits

Codex hooks must be enabled and reviewed/trusted through `/hooks`; project
hooks additionally require project trust. A hook launch error or timeout may
fail open even though Agent Overwatch catches evaluator exceptions and exits 2.
Policy `ask` maps to `deny`, because Codex PreToolUse does not support approval
prompts. All evaluated Codex calls are audited; malformed input exceptions emit
a blocking stderr reason but are not normal decision audit records.

Patch paths are checked, including rename destinations. Unknown built-ins still
follow the policy's `unknown_builtin_tool` value (default defer). Hosted tools
and writes to existing interactive sessions may not trigger PreToolUse. Shell
analysis remains a text tripwire, not a shell parser or OS security boundary.
