"""Codex PreToolUse adapter. Contract: https://learn.chatgpt.com/docs/hooks

Codex normalizes shell/exec_command to Bash + tool_input.command, and apply_patch
also uses tool_input.command. Raw aliases are accepted for other transports.
Unsupported ask decisions become deny. Hook launch failures and timeouts remain
outside this process's fail-closed exception handler.
"""
import json
import shlex

from .base import Adapter

SHELL_TOOLS = {"Bash", "shell", "local_shell", "exec", "container.exec",
               "exec_command", "shell_command"}
FILE_TOOLS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path",
              "NotebookEdit": "notebook_path", "Grep": "path", "Glob": "path",
              "view_image": "path"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}


def patch_paths(patch):
    """Extract all add/update/delete/move paths without logging patch content.

    Only unprefixed headers identify paths; hunk content starts with space/+/−.
    Reject unknown syntax rather than skipping unchecked targets. Codex itself
    validates hunk contents and file existence before applying.
    """
    if not isinstance(patch, str):
        raise ValueError("apply_patch requires a string command")
    lines = patch.strip().splitlines()
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise ValueError("unrecognized apply_patch envelope")
    paths = []
    operation = None
    for line in lines[1:-1]:
        if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
            operation, path = line.split(": ", 1)
        elif line.startswith("*** Move to: "):
            if operation != "*** Update File":
                raise ValueError("move without update")
            path = line[len("*** Move to: "):]
        else:
            if operation is None or not (line.startswith((" ", "+", "-", "@@"))
                                         or line == "*** End of File" or line == ""):
                raise ValueError("unrecognized apply_patch line")
            continue
        if not path.strip() or "\x00" in path:
            raise ValueError("invalid apply_patch path")
        paths.extend(dict.fromkeys((path, path.strip())))
    if not paths:
        raise ValueError("apply_patch contains no file targets")
    return paths


class CodexAdapter(Adapter):
    name = "codex"
    FAIL_CLOSED_EXIT = 2
    AUDIT_ALL = True

    def parse(self, event):
        if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
            raise ValueError("expected a PreToolUse event")
        tool = event.get("tool_name")
        if not isinstance(tool, str) or not tool:
            raise ValueError("missing tool_name")
        tin = event.get("tool_input")
        if tool == "apply_patch" and isinstance(tin, str):
            tin = {"command": tin}
        if not isinstance(tin, dict):
            raise ValueError("expected tool_input object")
        cwd = tin.get("workdir") or tin.get("cwd") or event.get("cwd", "")
        if not isinstance(cwd, str):
            raise ValueError("expected string cwd")
        base = {"tool": tool, "params": tin, "cwd": cwd}
        if tool in SHELL_TOOLS:
            command = tin.get("command", tin.get("cmd"))
            if isinstance(command, list) and command and all(isinstance(s, str) for s in command):
                if len(command) == 3 and command[1] in ("-c", "-lc", "-ic"):
                    command = command[2]
                else:
                    command = " ".join(shlex.quote(s) for s in command)
            if not isinstance(command, str) or not command.strip():
                raise ValueError("shell command missing or malformed")
            return dict(base, kind="bash", command=command)
        if tool == "apply_patch":
            return dict(base, kind="files", paths=patch_paths(tin.get("command", tin.get("patch"))))
        if tool in FILE_TOOLS:
            return dict(base, kind="file", access="write" if tool in WRITE_TOOLS else "read",
                        path=tin.get(FILE_TOOLS[tool]) or "")
        return dict(base, kind="mcp" if tool.startswith("mcp__") else "tool")

    def context(self, event):
        return {"adapter": self.name, "session_id": event.get("session_id", "unknown"),
                "agent_id": event.get("turn_id"), "agent_type": "codex",
                "hook_event": event.get("hook_event_name", "unknown"),
                "tool": event.get("tool_name", "unknown"), "cwd": event.get("cwd", "")}

    def normalize_decision(self, decision, rule_id, reason):
        if decision == "ask":
            return ("deny", rule_id, reason + "; Codex PreToolUse cannot request approval. "
                    "A human must perform this action or explicitly pause this rule from their own terminal")
        return decision, rule_id, reason

    def respond(self, decision, rule_id, reason):
        decision, rule_id, reason = self.normalize_decision(decision, rule_id, reason)
        if decision == "deny":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"[Agent Overwatch {rule_id or 'POLICY'}] {reason}. "
                "This is a policy boundary; do not retry through another tool or wrapper.",
            }}))
