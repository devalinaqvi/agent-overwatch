"""Installer lifecycle in isolated directories; never touches real hook trust."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which('jq'), 'jq required for installer')
class CodexInstallTests(unittest.TestCase):
    def test_user_install_idempotent_quoted_and_surgical_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='interlock-install-') as tmp:
            tmp = Path(tmp)
            repo = tmp / "checkout with spaces and 'quote'"
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns('.git', '.codex', '.agents', '__pycache__'))
            config = tmp / 'custom-codex-home'; config.mkdir()
            hooks = config / 'hooks.json'
            other = {'type': 'command', 'command': 'echo keep-me'}
            hooks.write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [other, {'type': 'command', 'command': 'python3 old/interlock-codex'}]}], 'Stop': [{'hooks': [other]}]}}))
            env = dict(os.environ, CODEX_HOME=str(config), INTERLOCK_AUDIT_DIR=str(tmp/'audit'), INTERLOCK_STATE=str(tmp/'state'))
            for _ in range(2):
                p = subprocess.run(['bash', str(repo/'install-codex.sh'), '--user'], cwd=tmp, env=env, text=True, capture_output=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn('/hooks', p.stdout)
            data = json.loads(hooks.read_text())
            entries = [h for g in data['hooks']['PreToolUse'] for h in g['hooks']]
            installed = [h for h in entries if 'interlock-codex' in h['command']]
            self.assertEqual(len(installed), 1)
            self.assertIn(other, entries)
            event = {'hook_event_name':'PreToolUse','session_id':'install-test','cwd':str(tmp),'tool_name':'Bash','tool_input':{'command':'git push'}}
            p = subprocess.run(installed[0]['command'], shell=True, input=json.dumps(event), text=True, capture_output=True, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
            p = subprocess.run(['bash', str(repo/'uninstall.sh'), '--codex', '--user'], cwd=tmp, env=env, text=True, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            data = json.loads(hooks.read_text())
            self.assertEqual(data['hooks']['PreToolUse'], [{'matcher':'Bash','hooks':[other]}])
            self.assertEqual(data['hooks']['Stop'], [{'hooks':[other]}])
            self.assertTrue(list(config.glob('hooks.json.pre-interlock.*')))

    def test_project_install_and_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix='interlock-project-') as tmp:
            env = dict(os.environ, CODEX_HOME=tmp+'/home', INTERLOCK_AUDIT_DIR=tmp+'/audit')
            p = subprocess.run(['bash', str(ROOT/'install-codex.sh')], cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            for operation in ('status','selftest'):
                p = subprocess.run([str(ROOT/'bin/interlock'),'--adapter','codex',operation], cwd=tmp, env=env, capture_output=True, text=True)
                if operation == 'status':
                    self.assertIn(p.returncode, (1, 2), p.stdout + p.stderr)
                else:
                    self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn('registered:' if operation=='status' else 'Adapter checks passed',p.stdout)


if __name__ == '__main__':
    unittest.main()
