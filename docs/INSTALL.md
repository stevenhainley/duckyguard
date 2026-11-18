# Installing DuckyGuard

DuckyGuard is **ad-hoc signed and not notarized** (no Apple Developer ID yet,
see `docs/NOTARIZATION.md`). macOS will refuse to open it until you tell
Gatekeeper once that you trust it. The steps below are the standard ones;
nothing is bypassed permanently.

An app that asks for Input Monitoring and Accessibility while unsigned is
asking for a lot of trust. The source is in this repository and the build is
one script (`packaging/build.sh`); building it yourself is a reasonable
choice.

## Requirements

- Apple silicon Mac on macOS 26 or newer. The released DMG is arm64 only and
  its bundled Python 3.14 has a macOS 26 minimum (`vtool -show-build`). Older
  macOS or Intel Macs: build from source (below); that is untested.
- Nothing else: Python and every library are inside the app.

## 1. Get the app

Either download `DuckyGuard-<version>.dmg` from a release and check its
checksum against the published `.sha256` file:

```bash
shasum -a 256 ~/Downloads/DuckyGuard-*.dmg
```

or build it yourself from source (below).

## 2. Install

Open the DMG and drag **DuckyGuard** to **Applications**.

## 3. Open it the first time (Gatekeeper)

macOS shows "Apple could not verify..." or a similar warning.

1. Double-click DuckyGuard and dismiss the warning.
2. Open System Settings › Privacy & Security, scroll to Security and click
   **Open Anyway**.

Control-click › Open no longer skips this warning (Apple removed it in
macOS 15).

**Or, from Terminal** (removes the quarantine flag the browser attached):
```bash
xattr -dr com.apple.quarantine /Applications/DuckyGuard.app
```

You only need to do this once per download.

## 4. Turn on the two permissions

DuckyGuard's first-run screen has a button for each that opens the right
page of System Settings:

- **Input Monitoring** is macOS's name for letting an app see every key.
  DuckyGuard uses the timing, and keeps the text only for bursts it blocks.
  Without it DuckyGuard sees nothing and the status reads "Not protected".
- **Accessibility** lets DuckyGuard block keys. Without it DuckyGuard can
  only warn and the status reads "Can't block".

When you press the Accessibility button, DuckyGuard asks macOS to add it to
the Accessibility list, so you only have to flip its switch. DuckyGuard
re-checks both permissions every second and starts blocking as soon as
Accessibility is on; no relaunch is needed for that one. After you turn on
Input Monitoring, macOS may ask you to quit and reopen DuckyGuard.

Because the build is ad-hoc signed, macOS may not recognise an updated copy
as the same app. After an update you may have to grant both permissions
again: remove DuckyGuard from each list with **-** and add it back.

The same first-run screen lists the keyboards connected at that moment with
a ticked box each ("Trust the keyboards connected now"). Leave your own
keyboards ticked, or the next time one reconnects it will be held like any
new keyboard.

## 5. Check it works

Press **Run safe test** on the Overview (it is also in the menu bar menu and
in Settings › About). DuckyGuard types one harmless sentence into its own
window at 12 ms per key. You should see the first four or five characters
appear in the test field, the status change to "Blocking", the duck's eyes
turn red and the rest of the sentence never arrive.

The test sentence contains no command and the test never presses Return. It
types only while DuckyGuard's window is in front, and stops if you click
another app.

## Install from Terminal (optional)

`packaging/install.sh` copies a built `dist/DuckyGuard.app` into
`/Applications`, strips the quarantine flag and opens it:

```bash
./packaging/install.sh
```

## Homebrew cask (plan)

Once a release with a stable download URL and SHA-256 exists, a cask like
`packaging/homebrew/duckyguard.rb` can be published to a tap
(`brew tap stevenhainley/duckyguard && brew install --cask duckyguard`). The
cask file in this repo is a template: fill in `url` and `sha256` from the
release. Homebrew does not require the app to be signed, but users still need
step 3 above until it is notarized.

## Build it yourself

```bash
git clone https://github.com/stevenhainley/DuckyGuard.git
cd DuckyGuard
python3.14 -m venv .venv         # a framework build of Python 3.12 to 3.14 (Homebrew or python.org)
.venv/bin/pip install -e . py2app pytest hypothesis pillow "setuptools<80"   # py2app 0.28 breaks on newer setuptools
./packaging/build.sh             # tests, icons, py2app, ad-hoc signature (verified), DMG + SHA-256
```

py2app 0.28 does not run on Python 3.15. If your `.venv` is newer, keep it for the tests and point the
bundling step at an older interpreter that has py2app, rumps, pynput and PyObjC installed:
`DUCKYGUARD_BUILD_PYTHON=/path/to/python3.14 ./packaging/build.sh`.

The 3D plate in the window is a bundled script, `src/duckyguard/ui/plate.js`, built from `ui-src/plate.src.js`
with three.js. It is checked in, so the app builds without Node. To change it: `cd ui-src && npm install && npm run build`.

`dist/DuckyGuard.app` and `dist/DuckyGuard-<version>.dmg` are the outputs.
The build is reproducible in the sense that the same checkout, Python and
package versions give the same app contents; the DMG's timestamp differs.

The 3D duck's script (`src/duckyguard/ui/plate.js`) is checked in already
built. To change it, edit `ui-src/plate.src.js` and run `npm install` and
`npm run build` in `ui-src/` (Node, esbuild and three.js). To rebuild its
texture, run `.venv/bin/python packaging/make_plate_texture.py`.

## Uninstall

1. Quit DuckyGuard from its menu bar icon.
2. Delete `/Applications/DuckyGuard.app`.
3. Optional: delete `~/Library/Application Support/DuckyGuard` (incidents,
   trusted keyboards, settings) and
   `~/Library/LaunchAgents/co.shindustries.duckyguard.plist` if you turned on
   Open at login.
4. Remove DuckyGuard from Input Monitoring and Accessibility in System Settings.
