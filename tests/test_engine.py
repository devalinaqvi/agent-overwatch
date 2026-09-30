#!/usr/bin/env python3
"""Engine unit tests — the PORTABLE core, evaluated directly on abstract Actions
with no adapter and no subprocess. This proves the policy logic is agent-agnostic:
any future adapter that produces these Action dicts gets the same decisions."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from interlock import engine

POL = engine.load_policy()


def act(**kw):
    base = {"kind": None, "tool": "", "params": {}, "cwd": "/tmp"}
    base.update(kw)
    return base


def decide(**kw):
    return engine.evaluate(POL, act(**kw))[0]


class EngineTests(unittest.TestCase):
    def test_read_env_denied(self):
        self.assertEqual(decide(kind="file", access="read", path="/tmp/.env", tool="Read"), "deny")

    def test_env_example_defers(self):
        self.assertEqual(decide(kind="file", access="read", path="/tmp/.env.example", tool="Read"), "defer")

    def test_write_settings_denied(self):
        self.assertEqual(decide(kind="file", access="write", path="/p/.claude/settings.json", tool="Write"), "deny")

    def test_read_source_defers(self):
        self.assertEqual(decide(kind="file", access="read", path="/tmp/app.py", tool="Read"), "defer")

    def test_bash_git_push_denied(self):
        self.assertEqual(decide(kind="bash", command="git push origin main", tool="Bash"), "deny")

    def test_bash_git_C_push_denied(self):
        self.assertEqual(decide(kind="bash", command="git -C /r push", tool="Bash"), "deny")

    def test_bash_drop_denied(self):
        self.assertEqual(decide(kind="bash", command='mysql -e "DROP DATABASE x;"', tool="Bash"), "deny")

    def test_bash_npm_publish_denied(self):
        self.assertEqual(decide(kind="bash", command="npm publish", tool="Bash"), "deny")

    def test_bash_sudo_asks(self):
        self.assertEqual(decide(kind="bash", command="sudo apt-get install x", tool="Bash"), "ask")

    def test_bash_commit_defers(self):
        self.assertEqual(decide(kind="bash", command="git commit -m x", tool="Bash"), "defer")

    def test_mcp_unknown_denied(self):
        self.assertEqual(decide(kind="mcp", tool="mcp__x__y"), "deny")

    def test_unknown_tool_defers(self):
        self.assertEqual(decide(kind="tool", tool="FutureTool"), "defer")

    def test_dangerous_param_asks(self):
        self.assertEqual(decide(kind="bash", command="make", tool="Bash",
                                params={"dangerouslyDisableSandbox": True}), "ask")

    def test_engine_is_adapter_free(self):
        """A hand-built Action (as any future adapter would emit) is evaluated
        the same way — no Claude Code types involved."""
        d = engine.evaluate(POL, {"kind": "file", "access": "read",
                                  "path": os.path.expanduser("~/.aws/config"),
                                  "tool": "read_file", "params": {}, "cwd": "/tmp"})
        self.assertEqual(d[0], "deny")
        self.assertEqual(d[1], "SEC-021", "the ~/.aws prefix rule should catch it")


if __name__ == "__main__":
    unittest.main(verbosity=2)
