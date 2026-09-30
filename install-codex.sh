#!/usr/bin/env bash
# Agent Overwatch installer for OpenAI Codex CLI — registers the guard as a Codex
# PreToolUse hook. Review before running. Backup kept. No sudo, no network.
#
#   ./install-codex.sh            # guard THIS project (./.codex/hooks.json)
#   ./install-codex.sh --user     # guard every project (~/.codex/hooks.json)
#
# Verified against the Codex hooks contract (developers.openai.com/codex/hooks).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ENTRY="$ROOT/bin/interlock-codex"

command -v jq >/dev/null || { echo "error: jq is required (apt-get install jq / brew install jq)"; exit 1; }
command -v python3 >/dev/null || { echo "error: python3 is required"; exit 1; }

case "${1:-}" in ""|--user) ;; *) echo "usage: $0 [--user]" >&2; exit 2 ;; esac
if [ "${1:-}" = "--user" ]; then
  HOOKS="${CODEX_HOME:-$HOME/.codex}/hooks.json"; SCOPE="user (${CODEX_HOME:-$HOME/.codex})"
else
  HOOKS="$PWD/.codex/hooks.json"; SCOPE="project ($PWD/.codex)"
fi
mkdir -p "$(dirname "$HOOKS")"
[ -f "$HOOKS" ] || echo '{}' > "$HOOKS"

BACKUP="$HOOKS.pre-interlock.$(date +%Y%m%d%H%M%S)"
cp "$HOOKS" "$BACKUP"

# POSIX shell quoting also handles spaces and apostrophes in the checkout path.
ENTRY_CMD=$(python3 -c 'import shlex,sys; print(shlex.join([sys.executable, sys.argv[1]]))' "$ENTRY")
HOOK_ENTRY=$(jq -n --arg cmd "$ENTRY_CMD" '{matcher:"*", hooks:[{type:"command", command:$cmd, timeout:15}]}')

jq --argjson entry "$HOOK_ENTRY" '
  .hooks.PreToolUse = (
    ((.hooks.PreToolUse // []) | map(
      .hooks |= map(select((.command // "") | contains("interlock-codex") | not))
      | select(.hooks | length > 0)))
    + [$entry]
  )
' "$HOOKS" > "$HOOKS.tmp"
jq . "$HOOKS.tmp" >/dev/null
mv "$HOOKS.tmp" "$HOOKS"

mkdir -p "${INTERLOCK_AUDIT_DIR:-$HOME/.interlock/audit}"

echo "Agent Overwatch installed into Codex $SCOPE"
echo "  backup:  $BACKUP"
echo "  adapter: codex  ($ENTRY_CMD)"
echo "  audit:   ${INTERLOCK_AUDIT_DIR:-$HOME/.interlock/audit}"
echo
echo "Restart Codex. In the CLI, open /hooks and review/trust this hook definition."
echo "Project installs also require the project to be trusted; hooks must be enabled."
echo "Verify the adapter: $ROOT/bin/interlock --adapter codex selftest"
echo "Inspect registration: $ROOT/bin/interlock --adapter codex status"
echo "Then ask Codex to run: cat .env.interlock-smoke (use a fake file in a scratch project)."
echo "Expect an Agent Overwatch SEC-001 or SEC-030 denial; confirm a matching audit record."
echo "Policy ask decisions BLOCK on Codex, whose PreToolUse does not support ask."
echo "Watch decisions with: $ROOT/bin/interlock tail"
