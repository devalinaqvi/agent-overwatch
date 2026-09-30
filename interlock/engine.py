"""Agent Overwatch policy engine — portable and agent-agnostic.

It evaluates an abstract **Action** against a policy and returns a decision. It
knows nothing about Claude Code, stdin/stdout, or any agent's wire format — an
*adapter* is responsible for turning an agent event into an Action and turning
the returned decision back into that agent's response.

An Action is a plain dict:
    {
      "kind":    "file" | "files" | "bash" | "mcp" | "tool",
      "access":  "read" | "write",   # file only
      "path":    "<path>",           # file only
      "command": "<shell command>",  # bash only
      "tool":    "<original tool name>",
      "params":  { ... },            # the tool's input params
      "cwd":     "<working dir>",
    }

A decision is a tuple: (decision, rule_id, reason, target) where decision is one
of "deny" | "ask" | "defer".  "defer" means "no opinion — let the agent's normal
permission flow decide". The engine never returns "allow"; it only blocks, asks,
or steps aside.
"""
import fnmatch
import json
import os
import re

# Repo root (…/interlock). Used to self-protect Agent Overwatch's own files on writes.
TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_POLICY = os.environ.get("INTERLOCK_POLICY") or os.path.join(TOOL_ROOT, "policy", "policy.json")


def load_policy(path=None):
    with open(path or DEFAULT_POLICY, encoding="utf-8") as fh:
        policy = json.load(fh)
    if policy.get("version") != 1:
        raise ValueError("unsupported policy version")
    return policy


# ---- path handling -------------------------------------------------------

def _resolve(path, cwd):
    """Expand and resolve a path (symlink-safe) without reading its contents."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(cwd or "/", p)
    return os.path.realpath(p)


def _match_basename(path_raw, path_real, rule):
    for candidate in (os.path.basename(path_raw), os.path.basename(path_real)):
        if fnmatch.fnmatch(candidate, rule["pattern"]):
            if any(fnmatch.fnmatch(candidate, ex) for ex in rule.get("exclude", [])):
                return False
            parent = rule.get("parent")
            if parent and os.path.basename(os.path.dirname(path_real)) != parent:
                continue
            return True
    return False


def _match_prefix(path_real, prefix):
    base = os.path.realpath(os.path.expanduser(prefix))
    return path_real == base or path_real.startswith(base + os.sep)


def check_path(policy, raw_path, cwd, is_write):
    """Return (decision, rule_id, reason) or None for one filesystem path."""
    real = _resolve(raw_path, cwd)
    pr = policy["protected_read"]
    for rule in pr.get("basenames", []):
        if _match_basename(raw_path, real, rule):
            return ("deny", rule["id"], rule["reason"])
    for rule in pr.get("prefixes", []):
        if _match_prefix(real, rule["path"]):
            return ("deny", rule["id"], rule["reason"])
    if is_write:
        # Built-in self-protection: never let a write land inside Agent Overwatch itself,
        # nor in its runtime state dir (pause flag + audit log are human-only).
        if _match_prefix(real, TOOL_ROOT):
            return ("deny", "OVW-000", "Agent Overwatch's own files are change-only by a human")
        if _match_prefix(real, os.path.expanduser("~/.interlock")):
            return ("deny", "OVW-001", "Agent Overwatch's runtime state (pause flag, audit log) is human-only")
        codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
        if any(real == _resolve(os.path.join(codex_home, name), cwd)
               for name in ("hooks.json", "config.toml")):
            return ("deny", "OVW-007", "Codex hook and permission wiring is human-change-only")
        pw = policy.get("protected_write", {})
        for rule in pw.get("prefixes", []):
            if _match_prefix(real, rule["path"]):
                return ("deny", rule["id"], rule["reason"])
        for rule in pw.get("basenames", []):
            if _match_basename(raw_path, real, rule):
                return ("deny", rule["id"], rule["reason"])
    return None


# ---- bash handling -------------------------------------------------------

_SPLIT = re.compile(r"(?:\|\||&&|[;|\n]|\$\(|`)")
_TOKEN = re.compile(r"""[^\s'"]+|'[^']*'|"[^"]*\"""")
_WRITE_HINT = re.compile(r"(^|\s)(tee|sed\s+-i|>>?|cp|mv|rm|install|ln|truncate|chmod|chown|rsync)(\s|$)")


def _git_subcommand(tokens):
    """Return git's subcommand, skipping option/value pairs like -C <dir>, -c k=v."""
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t.strip("'\"")
    return None


def _config_guard(cwd, guard):
    """Generic 'safe test config' guard. True = safe marker present; False =
    present but unsafe; None = no config file here. Fully policy-driven."""
    path = os.path.join(cwd or ".", guard["config_file"])
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return False
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return all(re.search(m, text) for m in guard["safe_markers"])


def check_bash(policy, command, cwd):
    """Return (decision, rule_id, reason) or None. Best-effort text analysis —
    a tripwire, not proof of safety (see docs/SECURITY.md)."""
    bash = policy.get("bash", {})

    for rule in bash.get("deny", []):
        if rule["kind"] == "regex" and re.search(rule["pattern"], command):
            return ("deny", rule["id"], rule["reason"])
    for segment in _SPLIT.split(command):
        tokens = [t.strip("'\"") for t in _TOKEN.findall(segment)]
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "git":
            sub = _git_subcommand(tokens)
            for rule in bash.get("deny", []):
                if rule["kind"] == "git_subcommand" and sub in rule["subcommands"]:
                    return ("deny", rule["id"], rule["reason"])
        for tok in tokens:
            if "/" in tok or tok.startswith("~") or tok.startswith("."):
                hit = check_path(policy, tok, cwd, is_write=bool(_WRITE_HINT.search(segment)))
                if hit:
                    return hit

    guard = bash.get("test_config_guard", {})
    if guard.get("enabled") and re.search(guard["runner_pattern"], command):
        dirs = [cwd]
        for segment in _SPLIT.split(command):
            tokens = [t.strip("'\"") for t in _TOKEN.findall(segment)]
            if len(tokens) >= 2 and tokens[0] == "cd":
                dirs.append(_resolve(tokens[1], cwd))
        if any(_config_guard(d, guard) is False for d in dirs):
            return ("deny", guard["id"], guard["reason"])

    for rule in bash.get("ask", []):
        if rule["kind"] == "regex" and re.search(rule["pattern"], command):
            return ("ask", rule["id"], rule["reason"])
        if rule["kind"] == "git_subcommand":
            for segment in _SPLIT.split(command):
                tokens = [t.strip("'\"") for t in _TOKEN.findall(segment)]
                if tokens and os.path.basename(tokens[0]) == "git" \
                        and _git_subcommand(tokens) in rule["subcommands"]:
                    return ("ask", rule["id"], rule["reason"])
    return None


def _check_mcp(policy, tool):
    parts = tool.split("__")
    server = parts[1] if len(parts) > 2 else ""
    mcp = policy.get("mcp", {"default": "deny", "default_reason": "unclassified MCP tool", "servers": {}})
    cfg = mcp["servers"].get(server)
    if cfg is None:
        return (mcp.get("default", "deny"), "MCP-001", mcp.get("default_reason", "unclassified MCP tool"), tool)
    tool_short = parts[2] if len(parts) > 2 else ""
    decision = cfg.get("tool_overrides", {}).get(tool_short) or cfg.get("decision", mcp.get("default"))
    if decision in ("deny", "ask"):
        return (decision, "MCP-002", f"policy for MCP server '{server}'", tool)
    return ("defer", None, "", tool)


# ---- the entry point -----------------------------------------------------

def evaluate(policy, action):
    """Evaluate an abstract Action. Return (decision, rule_id, reason, target)."""
    tool = action.get("tool", "")
    params = action.get("params") or {}
    cwd = action.get("cwd", "")

    for rule in policy.get("dangerous_tool_params", []):
        if tool == rule["tool"] and params.get(rule["param"]) == rule["equals"]:
            return (rule["decision"], rule["id"], rule["reason"], rule["param"])

    kind = action.get("kind")
    if kind == "files":
        for path in action["paths"]:
            hit = check_path(policy, path, cwd, is_write=True)
            if hit:
                return (*hit, path)
        return ("defer", None, "", action["paths"])

    if kind == "file":
        path = action.get("path") or ""
        if path:
            hit = check_path(policy, path, cwd, is_write=action.get("access") == "write")
            if hit:
                return (*hit, path)
        return ("defer", None, "", path)

    if kind == "bash":
        command = action.get("command") or ""
        hit = check_bash(policy, command, cwd)
        if hit:
            return (*hit, command)
        return ("defer", None, "", command)

    if kind == "mcp":
        return _check_mcp(policy, tool)

    return (policy.get("unknown_builtin_tool", "ask"), None, "tool not classified in policy", tool)
