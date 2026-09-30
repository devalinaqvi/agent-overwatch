"""Human-controlled, time-boxed pause.

When a pause is active, `deny`/`ask` decisions in scope are downgraded to
`defer` AND logged as `paused-bypass`, so you keep a record of exactly what ran
during the window. The pause auto-expires — you can't forget to re-enable it.

Safety properties:
  - Fail-safe: any error reading the state means NOT paused (stay enforcing).
  - The agent cannot set it: the state file is write-protected by the engine,
    and the `interlock pause/resume` command is denied to the agent by policy.
    Only a human, in their own terminal (not a hook'd tool call), can pause.
"""
import fnmatch
import json
import os
import re
import sys
import time

STATE_FILE = os.environ.get("INTERLOCK_STATE") or os.path.expanduser("~/.interlock/state.json")
# Root-owned master-bypass flag, set only by `sudo interlock bypass` (managed
# tier). The hook reads it but the user/agent cannot write it. Env override is
# for tests only.
BYPASS_FILE = os.environ.get("INTERLOCK_BYPASS") or "/etc/claude-code/interlock-bypass.json"


def _read_active(path):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        if float(st.get("paused_until", 0)) > time.time():
            return st
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return None


def active_pause():
    """Return the active pause/bypass dict, else None. The root-owned master
    bypass takes precedence over a user pause. Fail-safe: any read error means
    NOT paused (stay enforcing)."""
    return _read_active(BYPASS_FILE) or _read_active(STATE_FILE)


def rule_in_scope(rule_id, pause):
    scope = pause.get("scope") or "all"
    if scope == "all":
        return True
    if not rule_id:
        return False
    pats = scope if isinstance(scope, list) else [scope]
    return any(fnmatch.fnmatch(rule_id, p) for p in pats)


def set_pause(seconds, scope="all", reason=""):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    st = {"paused_until": time.time() + seconds, "started": time.time(),
          "scope": scope, "reason": reason, "by": "cli"}
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh)
    os.replace(tmp, STATE_FILE)
    return st


def clear_pause():
    try:
        os.remove(STATE_FILE)
        return True
    except OSError:
        return False


def parse_duration(s):
    m = re.fullmatch(r"(\d+)\s*([smhSMH]?)", s.strip())
    if not m:
        raise ValueError(f"bad duration '{s}' — use e.g. 30s, 30m, 2h")
    n, unit = int(m.group(1)), (m.group(2) or "m").lower()
    secs = n * {"s": 1, "m": 60, "h": 3600}[unit]
    if not 1 <= secs <= 12 * 3600:
        raise ValueError("duration must be between 1s and 12h (pauses auto-expire on purpose)")
    return secs


def _fmt(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def main(argv):
    if not argv or argv[0] in ("-h", "help"):
        print("usage: interlock pause <duration> [rule-scope...]   |   interlock resume   |   interlock show")
        return 0
    cmd = argv[0]
    if cmd == "pause":
        if len(argv) < 2:
            print("usage: interlock pause <duration> [rule-scope...]  (e.g. 30m, or 1h GIT-* DEPLOY-*)")
            return 2
        try:
            secs = parse_duration(argv[1])
        except ValueError as e:
            print(f"error: {e}")
            return 2
        scope = argv[2:] or "all"
        st = set_pause(secs, scope)
        print(f"⏸  Agent Overwatch PAUSED until {_fmt(st['paused_until'])}  (scope: {st['scope']}).")
        print("   In-scope deny/ask rules now DEFER — and are logged as 'paused-bypass'.")
        print("   It re-arms automatically at expiry. Resume early with: interlock resume")
        return 0
    if cmd == "resume":
        clear_pause()
        print("▶  Agent Overwatch resumed — enforcing normally.")
        return 0
    if cmd == "show":
        p = active_pause()
        if p:
            print(f"PAUSED until {_fmt(p['paused_until'])} (scope: {p['scope']})")
        else:
            print("enforcing (not paused)")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
