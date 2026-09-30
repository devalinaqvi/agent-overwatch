"""Shared audit + redaction. Agent-agnostic: the adapter hands in a context dict
and the decision; this writes a sanitized JSONL line. Raises on write failure so
the caller can fail closed."""
import json
import os
import re
import time

AUDIT_DIR = os.environ.get("INTERLOCK_AUDIT_DIR") or os.path.expanduser("~/.interlock/audit")
MAX_TARGET = 500

_REDACT = [
    (re.compile(r"(-p)[^\s'\"]{3,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*)[^\s'\";&|]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"\b(sk-[A-Za-z0-9]{6})[A-Za-z0-9\-_]+"), r"\1[REDACTED]"),
    (re.compile(r"\b(ghp_|gho_|github_pat_)[A-Za-z0-9_]+"), r"\1[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA[REDACTED]"),
]


def redact(text):
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text[:MAX_TARGET]


def audit(ctx, decision, rule_id, reason, target=""):
    os.makedirs(AUDIT_DIR, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "adapter": ctx.get("adapter", "unknown"),
        "session_id": ctx.get("session_id", "unknown"),
        "agent_id": ctx.get("agent_id"),
        "agent_type": ctx.get("agent_type"),
        "event": ctx.get("hook_event", "unknown"),
        "tool": ctx.get("tool", "unknown"),
        "cwd": ctx.get("cwd", ""),
        "target": redact(str(target)),
        "decision": decision,
        "rule": rule_id,
        "reason": reason,
    }
    path = os.path.join(AUDIT_DIR, time.strftime("%Y-%m-%d") + ".jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
