# Contributing

## Ground rules

- **Rules live in the engine; agent I/O lives in adapters.** A new rule goes in
  `policy/policy.json` (+ an `engine` test); a new agent goes in
  `interlock/adapters/` (+ an adapter test). Don't put agent-specific parsing in
  the engine, or policy logic in an adapter.
- **Every new rule needs a test** — the block *and* a legitimate command that
  must still pass. See `tests/test_engine.py`.
- **Keep it honest.** Agent Overwatch is a tripwire, not an unbypassable boundary.
  Don't describe a text rule as an OS guarantee. Document bypasses in
  `docs/SECURITY.md` rather than hiding them.
- **Stdlib only** in `interlock/` so the guard stays fast and dependency-free.
- **Fail closed.** Any new code path that can error must still block, never
  silently allow.

## Adding an agent adapter

Read [docs/ADAPTERS.md](docs/ADAPTERS.md). The hard prerequisite: the agent must
expose a hook that can *block a tool call before it runs*. Confirm that against
the agent's official docs before starting.

## Running the tests

```bash
python3 tests/test_engine.py              # portable engine
python3 tests/test_claude_code_adapter.py # Claude Code adapter, end-to-end
```

Never test against real credentials or databases — temp dirs and fake secrets
only.

## Reporting a vulnerability

Use a private security advisory, not a public issue, and allow time for a fix.
