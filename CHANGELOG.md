# Changelog

## 2.0.0 (2026-10-27)

- Detector: rule G (>= 40 keys/s, CV < 0.10 blocks at 6 keys), rule H (untrusted keyboard + >= 22 keys/s metronomic blocks at 6 keys), rule S (a burst already blocked stays blocked until a pause). Simulation only; see docs/EVALUATION.md.

A rebuild around one idea: only claim what the code does, and make what it
does visible.

### Detection
- New burst-based detector: keys per second, coefficient of variation of the
  gaps, key hold time, burst length, payload text and "untrusted keyboard just
  appeared", combined by seven readable rules. Every verdict carries its
  reasons and numbers.
- Fixes the evasion gap found in the 2026-10-26 claims audit: evenly spaced
  25-40 ms payloads from an already-present keyboard with no shell pattern are
  now blocked at 8 keys (v1 scored them 0.65 and let them through).
- Slow but perfectly regular payloads (DEFAULT_DELAY 100) are blocked at 20 keys.
- Keystrokes synthesized by local programs (password managers, text
  expanders, dictation) are labelled "software-typed" and not blocked.
- Key auto-repeat and modifier keys no longer count as timing samples.
- Fixed: `timestamp=0.0` was ignored; the 12-key text window could never
  match the `curl -sL http` pattern.
- Decision cost: median 49 us per key in isolation, 14 us median in the live
  tap callback (measured, see `docs/EVALUATION.md`).

### Blocking
- Keys in a blocked burst are dropped inside the CGEvent tap (returned as
  None) and never reach an application. v1 only activated its own window and
  logged the keys. Needs Accessibility; with only Input Monitoring the app
  observes and warns and says so.
- Quarantine length is a setting (0.5-10 s, default 2 s).

### Keyboards
- Keyboard inventory from IOKit registry reads (3.5 ms) instead of an
  `ioreg` subprocess (200-400 ms).
- "Learn this device": trusted keyboards persist in
  `~/Library/Application Support/DuckyGuard/trusted_devices.json` (0600).
- Notification and Devices screen when an untrusted keyboard appears; vendor
  id notes for common injector boards.

### App
- New menu bar app: pixel duck icon with protected / paused / alert states,
  native window with a local HTML dashboard (Funnel fonts bundled), no HTTP
  server and no open port (v1 listened on 127.0.0.1:4848 with CORS `*`).
- First-run onboarding: what it does and does not do, live permission checks,
  deep links to the two System Settings pages, then the safe test.
- Overview with status, keystroke rhythm strip and a test pad; incident
  timeline with plain-English explanations and measurements; Devices;
  Settings (quiet mode, launch at login, opt-in update check, quarantine
  length, expert toggle); graceful error notices and toasts.
- "Test it safely" types a harmless sentence into the app's own window via
  Quartz events so the block can be watched without hardware.
- Export incident report (Markdown). Indicators, MITRE ATT&CK rows and a YARA
  rule appear only when the captured text contains something to base them on;
  v1 always emitted a rule with a generic `curl` string and a hard-coded
  "NEUTRALIZED & CONTAINED (Zero Command Execution)" line.
- All state in one owner-only folder; corrupt files are set aside, not fatal.

### Packaging and docs
- `packaging/build.sh`: tests, icons, py2app, ad-hoc signature, DMG with
  SHA-256, all into `dist/`. Install script and Homebrew cask template.
- `docs/INSTALL.md`, `docs/NOTARIZATION.md`, `docs/EVALUATION.md`,
  `docs/FEATURES.md`; README rewritten with a "what it does not do" section.
- Version is 2.0.0 everywhere (the marketing draft said 2.4.0; the code was 1.0.0).
- The app is Python + PyObjC; the earlier "Swift 5 + Python 3.12" description
  referred to the v1 WKWebView host, now under `legacy/`.

### Removed
- v1 Swift window host, localhost HTTP API, tkinter desktop app and rumps
  tray (moved to `legacy/`, not built).
- Claims that were not backed by code: "sub-100 ms interception", "zero
  command execution", "sandbox", PCAP/hex viewer, enterprise exporter, Pro tier.

## 1.0.0 (2026-10-26)

Initial release: pynput keystroke listener with a 12-key velocity/jitter
score, `ioreg` USB polling, focus-stealing "decoy" window, incident Markdown
and YARA generation, Swift WKWebView host with a localhost dashboard.
