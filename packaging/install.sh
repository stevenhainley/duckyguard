#!/bin/bash
# Copies dist/DuckyGuard.app to /Applications, clears the quarantine flag, opens it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/dist/DuckyGuard.app"
DST="/Applications/DuckyGuard.app"
[ -d "$SRC" ] || { echo "build first: ./packaging/build.sh"; exit 1; }
if pgrep -x DuckyGuard >/dev/null; then osascript -e 'tell application "DuckyGuard" to quit' || true; sleep 1; fi
rm -rf "$DST"
cp -R "$SRC" "$DST"
xattr -dr com.apple.quarantine "$DST" 2>/dev/null || true
echo "installed $DST"
echo "If macOS still refuses to open it: right-click DuckyGuard in Applications and choose Open."
open "$DST"
