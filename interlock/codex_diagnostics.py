"""Codex registration inspection and isolated adapter self-test.

Registration is not proof of runtime activation. Hook trust is owned by Codex.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .codex_runtime import list_hooks, summarize

ROOT = Path(__file__).resolve().parent.parent


def status():
    print("Agent Overwatch adapter: codex")
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    sources = [home / "hooks.json"]
    # Codex may load project config from parent directories too.
    sources += [p / ".codex" / "hooks.json" for p in [Path.cwd(), *Path.cwd().parents]]
    found = False
    for path in dict.fromkeys(sources):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
            for group in data.get("hooks", {}).get("PreToolUse", []):
                for hook in group.get("hooks", []):
                    if "interlock-codex" in hook.get("command", ""):
                        print(f"registered: {path}")
                        print(f"  command: {hook['command']}")
                        found = True
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            print(f"cannot inspect {path}: {exc}")
    if not found:
        print("No Agent Overwatch registration found in hooks.json files.")
    try:
        code, verdict, hooks = summarize(list_hooks(Path.cwd()))
        print(verdict)
        for hook in hooks:
            print(f"  source={hook.get('sourcePath')} enabled={hook.get('enabled')} trust={hook.get('trustStatus')}")
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        code = 2
        print(f"UNKNOWN: unable to query Codex hook activation: {exc}")
    print("Project hooks also require project trust; features.hooks must not be false.")
    print("Audit directory:", os.environ.get("INTERLOCK_AUDIT_DIR", str(Path.home() / ".interlock/audit")))
    print("Policy ask decisions block on Codex (no PreToolUse approval prompt).")
    return code


def selftest():
    cases = [
        ("secret read", "Bash", {"command": "cat .env.interlock-smoke"}, "deny"),
        ("approval rule", "Bash", {"command": "sudo true"}, "deny"),
        ("protected patch", "apply_patch", {"command": "*** Begin Patch\n*** Delete File: .codex/hooks.json\n*** End Patch"}, "deny"),
        ("ordinary command", "Bash", {"command": "echo interlock-smoke"}, None),
    ]
    with tempfile.TemporaryDirectory(prefix="interlock-selftest-") as tmp:
        env = dict(os.environ, INTERLOCK_AUDIT_DIR=tmp + "/audit",
                   INTERLOCK_STATE=tmp + "/state.json")
        for name, tool, inputs, expected in cases:
            event = dict(hook_event_name="PreToolUse", session_id="selftest", cwd=tmp,
                         tool_name=tool, tool_input=inputs)
            p = subprocess.run([sys.executable, str(ROOT / "bin/interlock-codex")],
                               input=json.dumps(event), text=True, capture_output=True,
                               env=env, timeout=15)
            decision = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None
            if p.returncode or decision != expected:
                print(f"FAIL: {name}: exit={p.returncode}, decision={decision}; {p.stderr}")
                return 1
            print(f"PASS: {name}: {decision or 'defer'}")
    print("Adapter checks passed. No requested command or patch was executed.")
    print("This does not verify Codex hook activation. Review /hooks and run a live smoke test.")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "status":
        sys.exit(status())
    else:
        sys.exit(selftest())
