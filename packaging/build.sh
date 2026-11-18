#!/bin/bash
# Reproducible build of DuckyGuard.app and DuckyGuard-<version>.dmg into dist/. Ad-hoc signed, not notarized.
# Requires: the repo venv (.venv) for the tests and icons, and a Python with py2app for the bundle. py2app 0.28
# needs Python 3.14 or older and setuptools < 80; point DUCKYGUARD_BUILD_PYTHON at one if .venv is newer.
# No Apple Developer account needed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
BUILD_PY="${DUCKYGUARD_BUILD_PYTHON:-$PY}"
VERSION="$("$PY" -c 'import sys; sys.path.insert(0,"src"); import duckyguard; print(duckyguard.__version__)')"

echo "== tests"
"$PY" -m pytest -q

echo "== icons"
"$PY" packaging/make_icons.py

echo "== py2app"
rm -rf build/py2app dist/DuckyGuard.app
"$BUILD_PY" packaging/setup_py2app.py py2app --dist-dir dist --bdist-base build/py2app > build/py2app.log 2>&1 || { tail -40 build/py2app.log; exit 1; }
APP="dist/DuckyGuard.app"
test -d "$APP"

echo "== leave the retired v1 code out of the bundle (the repo keeps it for an old launcher; the app never loads it)"
find "$APP/Contents/Resources" \( -type d -name "_v1" -path "*duckyguard*" -o -name "server.py*" -path "*duckyguard*" \) -prune -exec rm -rf {} +

echo "== scrub build-machine path from Info.plist (py2app records the builder's python path)"
/usr/libexec/PlistBuddy -c 'Set :PythonInfoDict:PythonExecutable /usr/bin/python3' "$APP/Contents/Info.plist"
if grep -rIl "/Users/" "$APP/Contents/Info.plist" "$APP/Contents/Resources" 2>/dev/null | grep -v "\\.pyc$"; then echo "WARNING: absolute /Users/ path left in bundle"; fi

echo "== ad-hoc signature (macOS still needs Open Anyway in Privacy & Security; replace with Developer ID and notarization later)"
find "$APP" -type l ! -exec test -e {} \; -delete          # py2app leaves a dangling site.pyo link, which breaks the seal
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

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
