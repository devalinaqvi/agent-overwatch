"""Agent Overwatch — a deterministic, agent-agnostic guard for AI coding agents.

Two parts:
  - engine:   portable policy evaluation over an abstract Action (no agent I/O)
  - adapters: translate a specific agent's events <-> Action, and decisions out

Ships one adapter today (Claude Code). Adding another agent means writing an
adapter, not changing the engine. See docs/ADAPTERS.md.
"""
__version__ = "0.1.0"
