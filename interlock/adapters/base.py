"""The adapter contract. To support a new agent, subclass this and register it.

An adapter must:
  - `parse(event)`   -> an Agent Overwatch Action dict (see engine.py), or None if the
                        event is not an actionable tool call.
  - `context(event)` -> a dict of audit fields (session/agent/tool/cwd + adapter).
  - `respond(decision, rule_id, reason)` -> emit the agent's native response for
                        a deny/ask decision (and nothing for "defer").
  - `FAIL_CLOSED_EXIT` -> the process exit code that makes THIS agent hard-block
                        a call, used when the evaluator errors. For Claude Code
                        that is 2. If an agent has no blocking exit convention,
                        an adapter cannot guarantee fail-closed and must say so.

The engine and this contract are all an integrator needs; nothing here is
Claude-specific."""


class Adapter:
    name = "base"
    FAIL_CLOSED_EXIT = 1
    AUDIT_ALL = False

    def normalize_decision(self, decision, rule_id, reason):
        """Translate policy decisions before auditing and responding."""
        return decision, rule_id, reason

    def parse(self, event):
        raise NotImplementedError

    def context(self, event):
        raise NotImplementedError

    def respond(self, decision, rule_id, reason):
        raise NotImplementedError

    def is_config_event(self, event):
        """Optional: return True for non-tool config-change events to audit-only."""
        return False
