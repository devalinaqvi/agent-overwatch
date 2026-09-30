#!/usr/bin/env bash
# Agent Overwatch uninstaller. Removes only this adapter from one scope per run.
# Backups and unrelated hooks are preserved. Add --codex for Codex hooks.
#   ./uninstall.sh            # from ./.claude/settings.json
#   ./uninstall.sh --user     # from ~/.claude/settings.json
set -euo pipefail
ADAPTER="claude-code"; USER_SCOPE=false
for arg in "$@"; do
  case "$arg" in
    --codex) ADAPTER="codex" ;;
    --user) USER_SCOPE=true ;;
    *) echo "usage: $0 [--codex] [--user]" >&2; exit 2 ;;
  esac
done
if [ "$ADAPTER" = codex ]; then
  if $USER_SCOPE; then SETTINGS="${CODEX_HOME:-$HOME/.codex}/hooks.json"; else SETTINGS="$PWD/.codex/hooks.json"; fi
else
  if $USER_SCOPE; then SETTINGS="$HOME/.claude/settings.json"; else SETTINGS="$PWD/.claude/settings.json"; fi
fi
[ -f "$SETTINGS" ] || { echo "no settings file at $SETTINGS"; exit 0; }

# Surgical removal keeps any other settings changes you made after installing.
jq --arg entry "interlock-$ADAPTER" '
  if .hooks.PreToolUse then
    .hooks.PreToolUse |= map(
      .hooks |= map(select((.command // "") | contains($entry) | not))
      | select(.hooks | length > 0))
  else . end' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
echo "removed Agent Overwatch hook entries from $SETTINGS"

BACKUP="$(ls -t "$SETTINGS".pre-interlock.* 2>/dev/null | head -1 || true)"
[ -n "$BACKUP" ] && echo "a pre-install backup is also available if you prefer a full restore: $BACKUP"
echo "Audit records kept at ${INTERLOCK_AUDIT_DIR:-$HOME/.interlock/audit}."
echo "Restart your $ADAPTER sessions."
