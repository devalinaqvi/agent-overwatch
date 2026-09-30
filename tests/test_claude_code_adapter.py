#!/usr/bin/env python3
"""Claude Code adapter end-to-end tests. Runs the real hook entrypoint as a
subprocess with Claude Code event JSON on stdin — exactly as Claude Code does —
and asserts on exit code, emitted decision, and audit side effects. Proves the
adapter + engine + fail-closed path. FAKE secrets and temp dirs only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "bin", "interlock-claude-code")
FAKE = "FAKE_NOT_A_REAL_SECRET_12345"


def run(event, audit_dir, entry=ENTRY, stdin_override=None):
    env = dict(os.environ, INTERLOCK_AUDIT_DIR=audit_dir)
    data = stdin_override if stdin_override is not None else json.dumps(event)
    p = subprocess.run([sys.executable, entry], input=data, text=True,
                       capture_output=True, env=env, timeout=15)
    decision = None
    if p.stdout.strip():
        try:
            decision = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]
        except (json.JSONDecodeError, KeyError):
            decision = "MALFORMED"
    return p.returncode, decision, p


def bash(cmd, cwd="/tmp"):
    return {"hook_event_name": "PreToolUse", "session_id": "t", "cwd": cwd,
            "tool_name": "Bash", "tool_input": {"command": cmd}}


def file_ev(tool, path, cwd="/tmp"):
    key = {"Read": "file_path", "Edit": "file_path", "Write": "file_path",
           "Grep": "path", "Glob": "path"}[tool]
    return {"hook_event_name": "PreToolUse", "session_id": "t", "cwd": cwd,
            "tool_name": tool, "tool_input": {key: path}}


class ClaudeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="il-")
        self.audit = os.path.join(self.ws, "audit")
        self.env = os.path.join(self.ws, ".env")
        with open(self.env, "w") as fh:
            fh.write(f"TOKEN={FAKE}\n")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def d(self, event, **kw):
        return run(event, self.audit, **kw)

    def audit_text(self):
        out = ""
        if os.path.isdir(self.audit):
            for n in os.listdir(self.audit):
                out += open(os.path.join(self.audit, n)).read()
        return out

    # secrets (incl. indirect)
    def test_read_env_denied(self):
        self.assertEqual(self.d(file_ev("Read", self.env))[:2], (0, "deny"))
    def test_env_example_allowed(self):
        self.assertEqual(self.d(file_ev("Read", self.env + ".example"))[:2], (0, None))
    def test_symlink_to_env_denied(self):
        link = os.path.join(self.ws, "ok.txt"); os.symlink(self.env, link)
        self.assertEqual(self.d(file_ev("Read", link))[:2], (0, "deny"))
    def test_relative_env_denied(self):
        self.assertEqual(self.d(file_ev("Read", "./.env", cwd=self.ws))[:2], (0, "deny"))
    def test_ssh_denied(self):
        self.assertEqual(self.d(file_ev("Read", "~/.ssh/id_ed25519"))[:2], (0, "deny"))
    def test_bash_cat_env_denied(self):
        self.assertEqual(self.d(bash(f"cat {self.env}"))[:2], (0, "deny"))
    def test_bash_interpreter_env_denied(self):
        self.assertEqual(self.d(bash("python3 -c \"print(open('.env').read())\"", cwd=self.ws))[:2], (0, "deny"))

    # db / push / publish
    def test_drop_denied(self):
        self.assertEqual(self.d(bash('mysql -e "DROP DATABASE app;"'))[:2], (0, "deny"))
    def test_git_push_denied(self):
        self.assertEqual(self.d(bash("git push origin main"))[:2], (0, "deny"))
    def test_git_push_chained_denied(self):
        self.assertEqual(self.d(bash("npm test && git push"))[:2], (0, "deny"))
    def test_npm_publish_denied(self):
        self.assertEqual(self.d(bash("npm publish"))[:2], (0, "deny"))
    def test_git_commit_defers(self):
        self.assertEqual(self.d(bash("git commit -m x"))[:2], (0, None))

    # escalation / self-protection / mcp
    def test_sudo_asks(self):
        self.assertEqual(self.d(bash("sudo apt-get install x"))[:2], (0, "ask"))
    def test_write_settings_denied(self):
        self.assertEqual(self.d(file_ev("Write", os.path.join(self.ws, ".claude", "settings.json")))[:2], (0, "deny"))
    def test_write_own_files_denied(self):
        self.assertEqual(self.d(file_ev("Edit", os.path.join(ROOT, "policy", "policy.json")))[:2], (0, "deny"))
    def test_unknown_mcp_denied(self):
        self.assertEqual(self.d({"hook_event_name": "PreToolUse", "session_id": "t", "cwd": "/tmp",
                                 "tool_name": "mcp__x__y", "tool_input": {}})[:2], (0, "deny"))
    def test_sandbox_escape_asks(self):
        ev = bash("make"); ev["tool_input"]["dangerouslyDisableSandbox"] = True
        self.assertEqual(self.d(ev)[:2], (0, "ask"))

    # fail-closed
    def test_garbage_stdin_exit2(self):
        rc, dec, p = self.d({}, stdin_override="not json{{{")
        self.assertEqual(rc, 2); self.assertIn("failing closed", p.stderr)
    def test_missing_policy_exit2(self):
        env = dict(os.environ, INTERLOCK_AUDIT_DIR=self.audit, INTERLOCK_POLICY="/no/such/policy.json")
        p = subprocess.run([sys.executable, ENTRY], input=json.dumps(bash("ls")),
                           text=True, capture_output=True, env=env, timeout=15)
        self.assertEqual(p.returncode, 2)
    def test_unwritable_audit_exit2(self):
        ro = os.path.join(self.ws, "ro"); os.makedirs(ro); os.chmod(ro, 0o500)
        try:
            self.assertEqual(run(file_ev("Read", self.env), ro)[0], 2)
        finally:
            os.chmod(ro, 0o700)

    # audit hygiene + config-change observe
    def test_audit_redacts(self):
        self.d(bash(f"mysql -p{FAKE} -e 'DROP DATABASE x;'"))
        self.assertNotIn(FAKE, self.audit_text()); self.assertIn("[REDACTED]", self.audit_text())
    def test_config_change_observed(self):
        ev = {"hook_event_name": "ConfigChange", "session_id": "t", "cwd": "/tmp", "file_path": "/p/.claude/settings.json"}
        rc, dec, _ = self.d(ev)
        self.assertEqual((rc, dec), (0, None))
        self.assertIn("CFG-001", self.audit_text())

    # ---- time-boxed pause ----
    def _run_paused(self, event, pause_state):
        """Run an event with a specific pause state file."""
        sf = os.path.join(self.ws, "state.json")
        if pause_state is not None:
            with open(sf, "w") as fh:
                json.dump(pause_state, fh)
        env = dict(os.environ, INTERLOCK_AUDIT_DIR=self.audit, INTERLOCK_STATE=sf)
        p = subprocess.run([sys.executable, ENTRY], input=json.dumps(event), text=True,
                           capture_output=True, env=env, timeout=15)
        dec = None
        if p.stdout.strip():
            dec = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]
        return p.returncode, dec

    def test_active_pause_downgrades_deny(self):
        import time
        rc, dec = self._run_paused(bash("git push origin main"),
                                   {"paused_until": time.time() + 3600, "scope": "all"})
        self.assertEqual((rc, dec), (0, None), "paused deny should defer")
        self.assertIn("paused-bypass", self.audit_text())
        self.assertIn("GIT-001", self.audit_text())

    def test_expired_pause_enforces(self):
        import time
        rc, dec = self._run_paused(bash("git push origin main"),
                                   {"paused_until": time.time() - 10, "scope": "all"})
        self.assertEqual((rc, dec), (0, "deny"), "expired pause must enforce again")

    def test_scoped_pause_only_matching_rules(self):
        import time
        st = {"paused_until": time.time() + 3600, "scope": ["GIT-*"]}
        # in scope: git push -> deferred
        rc, dec = self._run_paused(bash("git push"), st)
        self.assertEqual((rc, dec), (0, None))
        # out of scope: reading .env is still denied
        rc2, dec2 = self._run_paused(file_ev("Read", self.env), st)
        self.assertEqual((rc2, dec2), (0, "deny"))

    def test_agent_cannot_pause_itself(self):
        self.assertEqual(self.d(bash("interlock pause 1h"))[:2], (0, "deny"))

    def test_agent_cannot_write_state(self):
        self.assertEqual(self.d(file_ev("Write", os.path.expanduser("~/.interlock/state.json")))[:2], (0, "deny"))

    # normal dev
    def test_normal_dev_defers(self):
        for ev in [file_ev("Read", os.path.join(self.ws, "a.py")),
                   file_ev("Edit", os.path.join(self.ws, "a.py")),
                   bash("npm run build"), bash("git status && git diff"), bash("pytest -q")]:
            self.assertEqual(self.d(ev)[:2], (0, None), ev["tool_input"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
