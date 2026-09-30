#!/usr/bin/env bash
# Agent Overwatch MANAGED tier (tamper-resistant) — the equivalent of a user-level
# install, but root-owned so an agent running as you cannot disable it, plus an
# OS sandbox as a backstop for the hook. REQUIRES sudo. Review before running.
#
#   sudo ./install-managed.sh [--adapter claude-code]
#
# It writes /etc/claude-code/managed-settings.json (managed settings override
# user/project settings and cannot be turned off without root), root-owns
# Agent Overwatch's hook + policy, and enables Claude Code's bash sandbox with a
# denyRead backstop for secrets. Paths are resolved at install time, so nothing
# machine-specific lives in the repo.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo ./install-managed.sh"; exit 1; }
ROOT="$(cd "$(dirname "$0")" && pwd)"
ADAPTER="claude-code"
[ "${1:-}" = "--adapter" ] && ADAPTER="${2:-claude-code}"
ENTRY="$ROOT/bin/interlock-$ADAPTER"
[ -f "$ENTRY" ] || { echo "no entrypoint $ENTRY"; exit 1; }

REAL_USER="${SUDO_USER:?run via sudo, not as root directly}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
MANAGED="/etc/claude-code/managed-settings.json"

command -v jq >/dev/null || { echo "jq required"; exit 1; }
command -v bwrap >/dev/null || echo "note: bubblewrap not found — install it (apt-get install bubblewrap) for the sandbox layer"
command -v socat >/dev/null || echo "note: socat not found — install it for the sandbox network layer"

mkdir -p /etc/claude-code
[ -f "$MANAGED" ] && cp "$MANAGED" "$MANAGED.pre-interlock.$(date +%Y%m%d%H%M%S)"

echo "writing root-owned managed settings (hook + deny rules + sandbox backstop)"
ENTRY_CMD="python3 $ENTRY"
jq -n --arg cmd "$ENTRY_CMD" --arg h "$REAL_HOME" '{
  permissions: {
    deny: [
      "Read(**/.env)", "Read(**/.env.*)",
      "Read(//\($h)/.ssh/**)", "Read(//\($h)/.aws/**)", "Read(//\($h)/.gnupg/**)",
      "Read(//\($h)/.config/gh/**)", "Read(//\($h)/.claude/.credentials.json)",
      "Bash(git push *)", "Bash(git push)"
    ],
    disableBypassPermissionsMode: "disable"
  },
  hooks: { PreToolUse: [ { matcher: "*", hooks: [ { type: "command", command: $cmd, timeout: 15 } ] } ] },
  sandbox: {
    enabled: true, allowUnsandboxedCommands: false, failIfUnavailable: false,
    filesystem: {
      denyRead: [ "~/.ssh", "~/.aws", "~/.gnupg", "~/.config/gh",
                  "~/.claude/.credentials.json", "~/.netrc", "~/.git-credentials" ],
      denyWrite: [ "'"$ROOT"'", "~/.interlock", "/etc/claude-code" ]
    }
  }
}' > "$MANAGED.tmp"
jq . "$MANAGED.tmp" >/dev/null && mv "$MANAGED.tmp" "$MANAGED"
chown root:root "$MANAGED"; chmod 644 "$MANAGED"

echo "root-owning Agent Overwatch's hook + policy (change-only by a human with sudo)"
chown -R root:root "$ROOT/bin" "$ROOT/interlock" "$ROOT/policy"
chmod 755 "$ROOT/bin"/* 2>/dev/null || true

echo "preparing append-only audit log"
mkdir -p "$REAL_HOME/.interlock/audit"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.interlock"
chattr +a "$REAL_HOME/.interlock/audit" 2>/dev/null || echo "  (chattr +a unsupported here — audit dir is not append-only; noted)"

echo
echo "DONE — managed tier installed. Verify as $REAL_USER:"
echo "   $ROOT/bin/interlock status"
echo "   $ROOT/bin/interlock selftest        # expect deny SEC-001"
echo "Restart your Claude Code sessions to load the managed settings + sandbox."
echo "Master bypass (only you, with sudo):  sudo $ROOT/bin/interlock bypass 30m [--network]"
