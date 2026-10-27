# Installing DuckyGuard

DuckyGuard is distributed as an **unsigned** app for now (no Apple Developer
ID yet, see `docs/NOTARIZATION.md`). macOS will refuse to open it until you
tell Gatekeeper once that you trust it. The steps below are the standard ones;
nothing is bypassed permanently.

## Requirements

- macOS 12 Monterey or newer, Apple silicon or Intel (the DMG we build is for
  the architecture of the Mac that built it; see "Build it yourself").
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

macOS shows "DuckyGuard can't be opened because it is from an unidentified
developer" or "Apple could not verify...". Pick one:

**Right-click, Open**
1. In Applications, right-click (or Control-click) DuckyGuard.
2. Choose **Open**, then **Open** again in the dialog.

**Or, on macOS 15 and newer**
1. Double-click DuckyGuard, dismiss the warning.
2. System Settings, Privacy & Security, scroll to Security, click **Open Anyway**.

**Or, from Terminal** (removes the quarantine flag the browser attached):
```bash
xattr -dr com.apple.quarantine /Applications/DuckyGuard.app
```

You only need to do this once per download.

## 4. Grant the two permissions

DuckyGuard's first-run screen walks you through it, with buttons that open
the right page of System Settings:

- **Input Monitoring**: lets DuckyGuard see keystrokes system-wide so it can
  time them. Without it DuckyGuard sees nothing.
- **Accessibility**: lets DuckyGuard *drop* keystrokes. Without it DuckyGuard
  can only warn.

System Settings, Privacy & Security, then each list. Turn on DuckyGuard. If
it is not listed, click **+** and pick it from Applications. After a reinstall
or upgrade of an unsigned app, macOS sometimes keeps a stale entry: remove
DuckyGuard from the list with **-** and add it again.

## 5. Check it works

Click **Test it safely** in DuckyGuard. It types a harmless sentence into its
own window at machine speed; you should see a few characters land, the menu
bar duck's shield turn red, and the rest of the sentence never arrive.

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
python3 -m venv .venv            # a framework build of Python 3.12+ (Homebrew or python.org)
.venv/bin/pip install -e . py2app pytest hypothesis pillow
./packaging/build.sh             # tests, icons, py2app, ad-hoc signature, DMG + SHA-256
```

`dist/DuckyGuard.app` and `dist/DuckyGuard-<version>.dmg` are the outputs.
The build is reproducible in the sense that the same checkout, Python and
package versions give the same app contents; the DMG's timestamp differs.

## Uninstall

1. Quit DuckyGuard from its menu bar icon.
2. Delete `/Applications/DuckyGuard.app`.
3. Optional: delete `~/Library/Application Support/DuckyGuard` (incidents,
   trusted keyboards, settings) and
   `~/Library/LaunchAgents/co.shindustries.duckyguard.plist` if you turned on
   launch at login.
4. Remove DuckyGuard from Input Monitoring and Accessibility in System Settings.
