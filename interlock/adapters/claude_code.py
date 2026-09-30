"""Claude Code adapter. Maps Claude Code's PreToolUse hook event to an Agent Overwatch
Action and maps decisions back to Claude Code's `permissionDecision` output.

Claude Code's contract (verified against its hooks docs): exit code 2 hard-blocks
a tool call; a `permissionDecision` of "deny"/"ask" in stdout JSON blocks/prompts;
anything else defers to the normal permission flow. That is why FAIL_CLOSED_EXIT
is 2 — an evaluator error becomes a hard block, not a silent pass-through.
"""
import json

from .base import Adapter

FILE_TOOLS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path",
              "NotebookEdit": "notebook_path", "Grep": "path", "Glob": "path"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
BASH_TOOLS = {"Bash", "PowerShell"}


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"
    FAIL_CLOSED_EXIT = 2

    def is_config_event(self, event):
        return event.get("hook_event_name") == "ConfigChange"

    def parse(self, event):
        tool = event.get("tool_name", "")
        tin = event.get("tool_input") or {}
        cwd = event.get("cwd", "")
        if tool in FILE_TOOLS:
            return {"kind": "file",
                    "access": "write" if tool in WRITE_TOOLS else "read",
                    "path": tin.get(FILE_TOOLS[tool]) or "",
                    "tool": tool, "params": tin, "cwd": cwd}
        if tool in BASH_TOOLS:
            return {"kind": "bash", "command": tin.get("command") or "",
                    "tool": tool, "params": tin, "cwd": cwd}
        if tool.startswith("mcp__"):
            return {"kind": "mcp", "tool": tool, "params": tin, "cwd": cwd}
        return {"kind": "tool", "tool": tool, "params": tin, "cwd": cwd}

    def context(self, event):
        return {"adapter": self.name,
                "session_id": event.get("session_id", "unknown"),
                "agent_id": event.get("agent_id"),
                "agent_type": event.get("agent_type"),
                "hook_event": event.get("hook_event_name", "unknown"),
                "tool": event.get("tool_name", "unknown"),
                "cwd": event.get("cwd", "")}

    def respond(self, decision, rule_id, reason):
        if decision == "deny":
            self._emit("deny", f"[Agent Overwatch {rule_id}] {reason}. This is a policy "
                               "boundary; do not retry through another tool or wrapper.")
        elif decision == "ask":
            self._emit("ask", f"[Agent Overwatch {rule_id or 'ASK'}] {reason}")

    @staticmethod
    def _emit(decision, reason):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }}))
