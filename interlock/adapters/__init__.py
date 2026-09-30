"""Adapters translate a specific agent's events into Agent Overwatch Actions and turn
decisions back into that agent's response. One adapter per agent."""
from .base import Adapter
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter

REGISTRY = {a.name: a for a in (ClaudeCodeAdapter, CodexAdapter)}


def get(name):
    cls = REGISTRY.get(name)
    if not cls:
        raise KeyError(f"unknown adapter '{name}' (have: {', '.join(REGISTRY)})")
    return cls()
