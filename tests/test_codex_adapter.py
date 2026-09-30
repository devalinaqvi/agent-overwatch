#!/usr/bin/env python3
"""Codex adapter subprocess tests (no Codex runtime). Runs bin/interlock-codex
with Codex-shaped PreToolUse events (session_id, turn_id, model, permission_mode,
tool_name, tool_input.command). Checks the shared engine and Codex adapter contract. Runtime enforcement
is checked separately by codex_live_smoke.py. FAKE secrets and temp dirs only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "bin", "interlock-codex")
FAKE = "FAKE_NOT_A_REAL_SECRET_12345"


def run(event, audit_dir):
    env = dict(os.environ, INTERLOCK_AUDIT_DIR=audit_dir, INTERLOCK_STATE=os.path.join(audit_dir, "no-pause.json"))
    p = subprocess.run([sys.executable, ENTRY], input=json.dumps(event), text=True,
                       capture_output=True, env=env, timeout=15)
    decision = None
    if p.stdout.strip():
        try:
            decision = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]
        except (json.JSONDecodeError, KeyError):
            decision = "MALFORMED"
    return p.returncode, decision


def codex_bash(cmd, cwd="/tmp"):
    """A Codex PreToolUse event for a shell tool call."""
    return {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t1",
            "cwd": cwd, "model": "gpt-x", "permission_mode": "auto",
            "tool_name": "Bash", "tool_use_id": "call_1",
            "tool_input": {"command": cmd}}


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="ilx-")
        self.audit = os.path.join(self.ws, "audit")
        self.env = os.path.join(self.ws, ".env")
        with open(self.env, "w") as fh:
            fh.write(f"TOKEN={FAKE}\n")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def d(self, event):
        return run(event, self.audit)

    def audit_text(self):
        out = ""
        if os.path.isdir(self.audit):
            for n in os.listdir(self.audit):
                with open(os.path.join(self.audit, n)) as fh:
                    out += fh.read()
        return out

    def test_shell_cat_env_denied(self):
        self.assertEqual(self.d(codex_bash(f"cat {self.env}")), (0, "deny"))

    def test_shell_git_push_denied(self):
        self.assertEqual(self.d(codex_bash("git push origin main")), (0, "deny"))

    def test_shell_drop_denied(self):
        self.assertEqual(self.d(codex_bash('psql -c "DROP TABLE users;"')), (0, "deny"))

    def test_shell_interpreter_env_denied(self):
        self.assertEqual(self.d(codex_bash("python3 -c \"print(open('.env').read())\"", cwd=self.ws)), (0, "deny"))

    def test_shell_sudo_asks(self):
        self.assertEqual(self.d(codex_bash("sudo true")), (0, "deny"))

    def test_shell_normal_defers(self):
        self.assertEqual(self.d(codex_bash("npm run build")), (0, None))

    def test_named_bash_tool_also_works(self):
        ev = codex_bash("git push"); ev["tool_name"] = "Bash"
        self.assertEqual(self.d(ev), (0, "deny"))

    def test_agent_cannot_pause(self):
        self.assertEqual(self.d(codex_bash("interlock pause 1h")), (0, "deny"))

    def test_audit_records_codex_adapter(self):
        self.d(codex_bash("git push"))
        self.assertIn('"adapter": "codex"', self.audit_text())

    def test_fail_closed_on_garbage(self):
        env = dict(os.environ, INTERLOCK_AUDIT_DIR=self.audit)
        p = subprocess.run([sys.executable, ENTRY], input="not json{{{", text=True,
                           capture_output=True, env=env, timeout=15)
        self.assertEqual(p.returncode, 2)

    def patch(self, body):
        return {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": self.ws,
                "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n" + body + "\n*** End Patch"}}

    def test_patch_protected_targets(self):
        for op in ("Add File", "Update File", "Delete File"):
            for path in (".env", ".codex/hooks.json", ".codex/config.toml",
                         os.path.join(ROOT, "policy/policy.json")):
                with self.subTest(op=op, path=path):
                    self.assertEqual(self.d(self.patch(f"*** {op}: {path}")), (0, "deny"))

    def test_patch_checks_every_file_and_move_destination(self):
        self.assertEqual(self.d(self.patch("*** Add File: safe.txt\n+ok\n*** Delete File: .env")), (0, "deny"))
        self.assertEqual(self.d(self.patch("*** Update File: safe.txt\n*** Move to: .codex/hooks.json\n@@\n-old\n+new")), (0, "deny"))
        self.assertEqual(self.d(self.patch("*** Update File: .env\n*** Move to: safe.txt\n@@\n-old\n+new")), (0, "deny"))

    def test_patch_symlink_target_denied(self):
        os.symlink(self.env, os.path.join(self.ws, "alias.txt"))
        self.assertEqual(self.d(self.patch("*** Delete File: alias.txt")), (0, "deny"))

    def test_safe_patch_audited_without_content(self):
        self.assertEqual(self.d(self.patch("*** Add File: safe.txt\n+" + FAKE)), (0, None))
        log = self.audit_text()
        self.assertIn('"decision": "defer"', log)
        self.assertIn('safe.txt', log)
        self.assertNotIn(FAKE, log)

    def test_patch_header_inside_content_is_not_a_target(self):
        self.assertEqual(self.d(self.patch("*** Add File: safe.txt\n+*** Delete File: .env")), (0, None))

    def test_patch_bad_syntax_fails_closed(self):
        for patch in ("...", "*** Begin Patch\n*** Unknown: .env\n*** End Patch", "", None):
            ev = self.patch("*** Add File: safe.txt")
            ev["tool_input"]["command"] = patch
            self.assertEqual(self.d(ev), (2, None))

    def test_shell_aliases_and_argv(self):
        for tool, inputs in (("exec_command", {"cmd": "git push"}),
                             ("shell_command", {"command": "git push"}),
                             ("shell", {"command": ["bash", "-lc", "git push"]}),
                             ("local_shell", {"command": ["git", "push"]})):
            ev = codex_bash("unused"); ev.update(tool_name=tool, tool_input=inputs)
            self.assertEqual(self.d(ev), (0, "deny"))

    def test_missing_command_fails_closed(self):
        ev = codex_bash("x"); ev["tool_input"] = {"wrong": "git push"}
        self.assertEqual(self.d(ev), (2, None))

    def test_unknown_tool_is_audited(self):
        ev = codex_bash("x"); ev.update(tool_name="FutureTool", tool_input={})
        self.assertEqual(self.d(ev), (0, None))
        self.assertIn("FutureTool", self.audit_text())

    def test_approval_audit_matches_effective_denial(self):
        self.assertEqual(self.d(codex_bash("sudo true")), (0, "deny"))
        log = self.audit_text()
        self.assertIn('"decision": "deny"', log)
        self.assertIn('ESC-001', log)
        self.assertNotIn('"decision": "ask"', log)

    def test_shell_cannot_remove_codex_config(self):
        for path in ("/tmp/project/.codex/hooks.json", "/tmp/project/.codex/config.toml"):
            self.assertEqual(self.d(codex_bash("rm " + path)), (0, "deny"))

    def test_command_workdir_is_used(self):
        os.symlink(self.env, os.path.join(self.ws, "alias.txt"))
        ev = codex_bash("cat ./alias.txt")
        ev["tool_input"]["workdir"] = self.ws
        self.assertEqual(self.d(ev), (0, "deny"))

    def test_pause_still_applies_before_ask_conversion(self):
        import time
        state_file = os.path.join(self.ws, "paused.json")
        with open(state_file, "w") as fh:
            json.dump({"paused_until": time.time() + 60, "scope": ["ESC-001"]}, fh)
        env = dict(os.environ, INTERLOCK_AUDIT_DIR=self.audit, INTERLOCK_STATE=state_file)
        p = subprocess.run([sys.executable, ENTRY], input=json.dumps(codex_bash("sudo true")),
                           text=True, capture_output=True, env=env, timeout=15)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertIn('"decision": "paused-bypass"', self.audit_text())

    def test_custom_codex_home_protected(self):
        home = os.path.join(self.ws, "custom-config")
        env = dict(os.environ, CODEX_HOME=home, INTERLOCK_AUDIT_DIR=self.audit,
                   INTERLOCK_STATE=os.path.join(self.ws, "no-state"))
        for name in ("hooks.json", "config.toml"):
            p = subprocess.run([sys.executable, ENTRY],
                               input=json.dumps(self.patch("*** Delete File: " + os.path.join(home, name))),
                               text=True, capture_output=True, env=env, timeout=15)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_unknown_mcp_denied(self):
        ev = codex_bash("x"); ev.update(tool_name="mcp__unknown__write", tool_input={})
        self.assertEqual(self.d(ev), (0, "deny"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
