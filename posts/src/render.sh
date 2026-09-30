#!/usr/bin/env bash
# Regenerate every Agent Overwatch image (README diagrams + LinkedIn cards) from
# the HTML sources in this folder. Runs a local headless Chrome — nothing is
# uploaded. Output: ../../docs/images (README) and ../ (posts/ LinkedIn cards).
#
#   bash posts/src/render.sh
#
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
POSTS="$(cd "$SRC/.." && pwd)"
IMAGES="$(cd "$SRC/../.." && pwd)/docs/images"
mkdir -p "$IMAGES"

CHROME=""
for c in google-chrome google-chrome-stable chromium chromium-browser; do
  command -v "$c" >/dev/null 2>&1 && { CHROME="$c"; break; }
done
[ -n "$CHROME" ] || { echo "need Chrome/Chromium on PATH"; exit 1; }

shot(){ # name w h srcfile outdir
  "$CHROME" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --force-device-scale-factor=2 --window-size="$2","$3" \
    --screenshot="$4/$1.png" "file://$SRC/$5" 2>/dev/null
  echo "  $4/$1.png"
}

echo "LinkedIn cards → $POSTS"
shot 01-hero          1200 1200 "$POSTS" 01-hero.html
shot 02-architecture  1200 1200 "$POSTS" 02-architecture.html
shot 03-proof         1200 1200 "$POSTS" 03-proof.html

echo "README images → $IMAGES"
shot architecture     1600 1180 "$IMAGES" architecture-wide.html
shot proof-codex      1240 820  "$IMAGES" proof-codex.html
shot proof-claude     1240 1180 "$IMAGES" proof-claude.html

echo "done."
