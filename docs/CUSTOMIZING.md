# Customizing the policy

The policy is one file: [`policy/policy.json`](../policy/policy.json). Edit it,
re-run `./bin/interlock selftest` and `python3 tests/test_engine.py`, and restart
your Claude Code sessions. Point at a different file with `INTERLOCK_POLICY`; move
the audit log with `INTERLOCK_AUDIT_DIR`.

Every rule has a stable **id** (shown in the message and the audit log) and a
**reason**. Keep ids unique.

## Protect more files from reads

```jsonc
"protected_read": {
  "basenames": [ { "id": "SEC-050", "pattern": "*.secret", "exclude": [], "reason": "Project secrets" } ],
  "prefixes":  [ { "id": "SEC-051", "path": "~/.config/myapp", "reason": "App credentials" } ]
}
```
`basenames` match the file name (glob) anywhere; `exclude` lets safe siblings
through (how `.env.example` stays readable). `prefixes` match a path and
everything under it. `~` and relative paths are resolved symlink-safe first.

## Block more writes

`protected_write` has the same shape and is checked only for write actions.
Agent Overwatch always protects its own directory regardless of policy.

## Bash rules

```jsonc
// regex — matched against the whole command
{ "id": "OPS-001", "kind": "regex", "pattern": "\\brm\\s+-rf\\s+/(?!tmp)", "reason": "Recursive delete outside /tmp" }
// git_subcommand — matched after parsing git's real subcommand (skips -C/-c)
{ "id": "GIT-010", "kind": "git_subcommand", "subcommands": ["tag"], "reason": "Tags are a release action" }
```
Python `re` syntax; escape backslashes for JSON (`\\b`, `\\s`, `\\.`). Use `deny`
for hard boundaries, `ask` for "a human should decide". A regex catches the form
you wrote, not every equivalent (see [SECURITY.md](SECURITY.md)).

## The optional isolated-test-DB guard

Off by default. Blocks a test runner when the config file in the working dir
lacks markers proving it points at an isolated database:

```jsonc
"test_config_guard": {
  "id": "DB-010", "enabled": true,
  "config_file": "phpunit.xml",
  "runner_pattern": "(artisan\\s+test\\b|vendor/bin/pest\\b|vendor/bin/phpunit\\b)",
  "safe_markers": ["<env\\s+name=\"DB_CONNECTION\"\\s+value=\"sqlite\"",
                   "<env\\s+name=\"DB_DATABASE\"\\s+value=\":memory:\""],
  "reason": "Test runner blocked: config isn't an isolated test DB"
}
```
It follows a leading `cd`. Adapt `config_file` / `runner_pattern` / `safe_markers`
to your stack (a Node project might check a jest config or `.env.test`).

## MCP servers

```jsonc
"mcp": { "default": "deny", "default_reason": "unclassified MCP tool",
  "servers": {
    "playwright":   { "decision": "defer" },
    "some-db-tool": { "decision": "ask", "tool_overrides": { "read_query": "defer", "write_query": "deny" } }
  } }
```
`decision` is `defer` / `ask` / `deny`; `tool_overrides` set per-tool exceptions.

## Stricter or looser

Move an `ask` rule to `deny` for a hard boundary a conversational "yes" can't
lift, or a `deny` to `ask` if it's too strict — deliberately, and never for
secret reads or database destruction.
