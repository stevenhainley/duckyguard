#!/bin/bash
# Reproducible, unsigned build of DuckyGuard.app and DuckyGuard-<version>.dmg into dist/.
# Requires: the repo venv (.venv) with py2app installed. No Apple Developer account needed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
VERSION="$($PY -c 'import sys; sys.path.insert(0,"src"); import duckyguard; print(duckyguard.__version__)')"

echo "== tests"
"$PY" -m pytest -q

echo "== icons"
"$PY" packaging/make_icons.py

echo "== py2app"
rm -rf build/py2app dist/DuckyGuard.app
"$PY" packaging/setup_py2app.py py2app --dist-dir dist --bdist-base build/py2app > build/py2app.log 2>&1 || { tail -40 build/py2app.log; exit 1; }
APP="dist/DuckyGuard.app"
test -d "$APP"

echo "== scrub build-machine path from Info.plist (py2app records the builder's python path)"
/usr/libexec/PlistBuddy -c 'Set :PythonInfoDict:PythonExecutable /usr/bin/python3' "$APP/Contents/Info.plist"
if grep -rIl "/Users/" "$APP/Contents/Info.plist" "$APP/Contents/Resources" 2>/dev/null | grep -v "\\.pyc$"; then echo "WARNING: absolute /Users/ path left in bundle"; fi

echo "== ad-hoc signature (lets macOS run it after the Gatekeeper override; replace with Developer ID later)"
codesign --force --deep --sign - "$APP" 2>/dev/null || true

echo "== dmg"
DMG="dist/DuckyGuard-$VERSION.dmg"
rm -f "$DMG"
STAGE="build/dmg"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp docs/INSTALL.md "$STAGE/INSTALL.md"
hdiutil create -quiet -volname "DuckyGuard $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
shasum -a 256 "$DMG" | tee "$DMG.sha256"
du -sh "$APP" "$DMG"
echo "== done: $APP, $DMG"
