#!/usr/bin/env bash
# Agent Overwatch installer (Claude Code adapter) — wires the guard into a Claude Code
# settings file. Review before running. Timestamped backup. No sudo, no network.
#
#   ./install.sh            # guard THIS project (./.claude/settings.json)
#   ./install.sh --user     # guard every project (~/.claude/settings.json)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ENTRY="$ROOT/bin/interlock-claude-code"

command -v jq >/dev/null || { echo "error: jq is required (apt-get install jq / brew install jq)"; exit 1; }
command -v python3 >/dev/null || { echo "error: python3 is required"; exit 1; }

if [ "${1:-}" = "--user" ]; then
  SETTINGS="$HOME/.claude/settings.json"; SCOPE="user (~/.claude)"
else
  SETTINGS="$PWD/.claude/settings.json"; SCOPE="project ($PWD/.claude)"
fi
mkdir -p "$(dirname "$SETTINGS")"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"

BACKUP="$SETTINGS.pre-interlock.$(date +%Y%m%d%H%M%S)"
cp "$SETTINGS" "$BACKUP"

ENTRY_CMD="python3 $ENTRY"
HOOK_ENTRY=$(jq -n --arg cmd "$ENTRY_CMD" '{matcher:"*", hooks:[{type:"command", command:$cmd, timeout:15}]}')

jq --argjson entry "$HOOK_ENTRY" '
  .hooks.PreToolUse = (
    ((.hooks.PreToolUse // []) | map(select((.hooks[0].command // "") | contains("interlock-claude-code") | not)))
    + [$entry]
  )
' "$SETTINGS" > "$SETTINGS.tmp"
jq . "$SETTINGS.tmp" >/dev/null
mv "$SETTINGS.tmp" "$SETTINGS"

mkdir -p "${INTERLOCK_AUDIT_DIR:-$HOME/.interlock/audit}"

echo "Agent Overwatch installed into $SCOPE"
echo "  backup:  $BACKUP"
echo "  adapter: claude-code  ($ENTRY_CMD)"
echo "  audit:   ${INTERLOCK_AUDIT_DIR:-$HOME/.interlock/audit}"
echo
echo "Verify:  $ROOT/bin/interlock selftest     (expect: deny SEC-001)"
echo "Restart your Claude Code sessions to load the hook."
