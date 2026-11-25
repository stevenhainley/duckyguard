# DuckyGuard architecture (v2)

One Python process, no helper, no daemon, no kernel extension, no open port.

```
 menu bar (rumps NSStatusItem)      window (AppKit NSWindow + WKWebView, local HTML)
          \                                  /   JS <-> Python via WKScriptMessageHandler
           \                                /
            +------------ app.py ----------+
                            |
                        engine.py
          +-----------------+------------------+
          |                 |                  |
   CGEvent tap         detector.py         devices.py
   (pynput, active)    burst statistics    IOKit registry
   drop = return None  -> Verdict          keyboards, trust
          |
      incidents.py  ->  store.py  (~/Library/Application Support/DuckyGuard, 0700/0600)
```

## The hot path

`engine._intercept` is the CGEvent tap callback (pynput's `darwin_intercept`).
For every key event it:

1. Re-enables the tap if macOS disabled it for a timeout (`kCGEventTapDisabledByTimeout`).
2. Reads the kernel event timestamp, keycode, auto-repeat flag and source
   process id from the `CGEvent`.
3. On key-up: records the hold time; drops the event if quarantine is active.
4. On key-down: if quarantine is active, records the character and drops the
   event. Otherwise builds a `KeyEvent` and asks the detector for a `Verdict`.
   If `verdict.block`, starts quarantine and drops this event.

No file I/O happens in the callback. The measured cost is 14 us median, 0.7
ms p99 on an M-series Mac (`docs/EVALUATION.md`); macOS disables taps that
take longer than about a second.

Events whose source pid is non-zero were synthesized by a process on this
Mac. They are labelled `software` and let through unless test mode (the safe
test) or the expert setting is on.

## Detector

`KeystrokeAnomalyDetector.observe(KeyEvent) -> Verdict`. State is the
current burst (keys with gaps under 350 ms), recent hold times and the last
96 characters. Features: keys/s, mean/median/stdev of gaps, coefficient of
variation, min/max gap, median hold, burst length, payload pattern, seconds
since an untrusted keyboard appeared. Seven decision rules, listed in
`docs/EVALUATION.md`, produce `block`, a 0-1 score (for display, not a
probability), a list of reasons and a one-sentence explanation.

## Quarantine

`Engine._begin_quarantine` records the text that already reached the front
app (the burst before the decision), then drops every hardware key-down and
key-up until the stream has been quiet for `quarantine_seconds` (default 2).
A watchdog thread then finalizes the incident: analysis of the full text
(URLs, IPs, base64, MITRE rows, optional YARA), a summary, and a JSON file in
`incidents/`. The status item shows the alert state for ten seconds.

## Keyboards

`devices.py` reads IOHIDDevice entries straight from the IOKit registry with
ctypes (`IOServiceGetMatchingServices` + `IORegistryEntryCreateCFProperty`),
keeps keyboards (usage page 1, usage 6/7), and polls every 2 s (3.5 ms per
poll). A keyboard that appears after startup and is neither built in nor in
the trust list starts a 10-second window in which bursts are judged more
strictly (rule E). Trusting a keyboard clears that window. macOS does not
expose the source device of a `CGEvent`, so incidents only *attribute* a
burst to the most recent untrusted keyboard.

## Storage

`store.py`: one folder, created 0700, every file written atomically with
0600. `settings.json`, `trusted_devices.json` (with SHA-256 descriptor pins),
`audit.jsonl` (SHA-256 hash-chained event log with 5 MB rotation),
`incidents/*.json`, `exports/*.md`. `DUCKYGUARD_HOME` overrides the location
(used by tests and development). Corrupt JSON is renamed `*.corrupt` and
defaults are used.

## UI

`ui/index.html`, `app.css`, `app.js`, `plate.js`, three bundled fonts and the
icons are loaded with `loadFileURL` from inside the bundle. `plate.js` is the
3D duck: three.js plus `ui-src/plate.src.js`, bundled with esbuild and checked
in. It renders a depth-displaced mesh to an offscreen target, then prints it
through an ordered dither. The page sends
`{cmd: ...}` messages through `window.webkit.messageHandlers.dg`; Python
replies with `dg.receive({type, data})` via `evaluateJavaScript` on the main
thread. A snapshot (status, permissions, settings, keyboards, recent timing,
incidents) is pushed once a second while the window is visible and
immediately on engine events. Engine events can arrive on the keyboard tap's
thread; `on_engine_event` only hands them to the main thread, where sounds,
notifications and snapshots are made. Messages for the page that are sent
before it has loaded are queued until it says `ready`. Incidents are kept in
memory and re-read only when their folder changes. Page errors are sent back
with a `log` command and printed to stderr.

## Permissions

`permissions.py` uses `IOHIDCheckAccess` (Input Monitoring) and
`AXIsProcessTrusted` (Accessibility). The active tap needs Accessibility;
without it the engine starts a listen-only tap and reports `observing`.
The app's one-second tick calls `Engine.refresh_permissions()`, which rebuilds
the tap when a permission is granted or revoked after launch.

## Packaging

`packaging/setup_py2app.py` builds a self-contained app (Python framework,
PyObjC, rumps, pynput, the `duckyguard` package with its `ui/` folder) with
`LSUIElement` set so there is no Dock icon. `packaging/build.sh` runs the
tests, regenerates icons, builds, ad-hoc signs and produces a DMG with a
SHA-256. See `docs/INSTALL.md` and `docs/NOTARIZATION.md`.

## Legacy

`legacy/` holds the v1 Swift WKWebView host, the localhost HTTP server, the
`ioreg`-based watcher, the focus-stealing "decoy sink" and the rumps-only
tray. They are not built or imported by v2. The installed v1 bundle at
`~/Applications/DuckyGuard.app` ran `python3 -m duckyguard.server` from this
checkout. `src/duckyguard/server.py` and `src/duckyguard/_v1/` are kept in the
repository only for that old launcher; `packaging/build.sh` removes both from
the app bundle, and the v2 app never imports them.
