# DuckyGuard 2.0 features

The canonical list. Every line is something the code in this repo does today;
the "where" column names the screen it appears on. Marketing copy, the website
and the launch video should not claim anything that is not on this list.
Simulation numbers come from `docs/EVALUATION.md`; nothing here is a hardware
measurement.

| feature | honest one-liner | where |
|---|---|---|
| Keystroke-timing detection | Judges each burst of hardware keystrokes by rate, gap regularity, key hold time, burst length and payload text; machine-like bursts are blocked. | Runs in the background; verdict shown on Overview > Test pad |
| Real blocking | Dropped keys never reach any app: the CGEvent tap returns the event as None. Needs the Accessibility permission. Keys typed before the decision (median 8 at injector speed, in simulation) do reach the front app. | Overview status "Protected" / "Blocking a burst" |
| Observe-only fallback | With Input Monitoring but no Accessibility, DuckyGuard still detects and records bursts but can only warn. | Status "Observing only", notice on Overview |
| Plain-English explanation | Every block says what happened in one sentence ("A keyboard typed 12 keys in 0.2 s (70 keys/s), about 9x faster than a fast typist...") plus the reasons and the numbers behind them. | Timeline (expanded incident), Overview > Last incident |
| Incident timeline | Every blocked burst is saved locally with the text that reached the app, the text that was dropped, the attributed keyboard and the decision rule. | Timeline |
| Export incident report | One click writes a Markdown report (explanation, measurements, captured text, indicators, MITRE ATT&CK rows, a YARA rule only when the text contained a URL or IP) and reveals it in Finder. | Timeline > Export report, Overview > Last incident |
| Keyboard inventory | Lists connected keyboards (name, maker, vendor/product id, transport, serial) from IOKit, with a note for vendor ids used by common injector boards. | Devices |
| Trusted keyboards | "Trust this keyboard" remembers a keyboard so plugging it in no longer raises suspicion. Trusted keyboards that type like a machine are still blocked. The list persists in a 0600 file. | Devices, Timeline (from an incident) |
| New-keyboard alert | When an untrusted keyboard appears, DuckyGuard notifies and opens the Devices screen; a fast burst within 10 s of that is judged more strictly. | Notification + Devices |
| Software-typed input is left alone | Keystrokes synthesized by local programs (password managers, text expanders, dictation, scripts) carry a process id and are labelled "software-typed", not blocked. | Overview > Keystroke rhythm legend; Settings expert toggle |
| Safe test | Types a harmless sentence into DuckyGuard's own window at 12 ms per key so you can watch the block happen. No hardware, nothing executes. | Overview > Test it safely, menu bar > Test it safely, onboarding step 3 |
| Keystroke rhythm strip | Bars for the gap between recent keys; red bars are blocked keys, grey bars software-typed keys. | Overview |
| Menu bar status | Pixel duck icon: colour = protected, grey = paused, red shield = blocking. Menu: status line, Open, Test, Pause/Resume, Quiet mode, Quit. | Menu bar |
| Onboarding | First run explains what DuckyGuard does and does not do, checks both permissions live, deep-links to the right System Settings pages, then runs the safe test. | First launch |
| Permission checks | Live `IOHIDCheckAccess` and `AXIsProcessTrusted` checks with "Open System Settings" buttons. | Onboarding, Overview notice, Settings |
| Quiet mode | Still blocks and logs; no sound, no notification. | Settings, menu bar |
| Launch at login | Writes a per-user LaunchAgent (works unsigned). | Settings |
| Update notice (opt-in) | At most one HTTPS request a day to GitHub's releases API; shows a notice, never downloads. Off by default. | Settings |
| Quarantine length | How long keys keep being dropped after the last blocked key (0.5-10 s, default 2 s). | Settings |
| Private local storage | Everything lives in `~/Library/Application Support/DuckyGuard` (mode 0700, files 0600). No network use except the opt-in update check. | Settings > Your data |
| Graceful failures | Missing permission, tap failure, export failure and update failure each show a message instead of silently doing nothing. Corrupt settings are set aside, not fatal. | Overview notices, toasts |
| Command line | `duckyguard start / status / simulate / incidents / export / bench`. | Terminal |
| Unsigned build + DMG | `packaging/build.sh` produces `dist/DuckyGuard.app` and a DMG with SHA-256; install script and Homebrew cask template included. | Not a screen |

## Not features (do not claim)

- No hardware test has been run yet (no Rubber Ducky / Flipper on hand during development).
- No per-keystroke device attribution: macOS does not tag key events with their source device; incidents say "attributed by time".
- Slow, randomised payloads (80-120 ms per key with jitter) are not detected (0% in simulation) by design of the thresholds; they take a minute to type.
- No PCAP, no hex viewer, no "enterprise exporter", no Pro tier, no license keys.
- Not notarized; see `docs/NOTARIZATION.md`.
- Not an antivirus: DuckyGuard only looks at keystroke timing.

## Screenshots

`docs/screens/*@2x.png`, captured with `screencapture` from the running app
(748 x 560 pt window, Retina 2x). `10-menubar-icon-states@2x.png` is rendered
from the three icon files because the status item sits under the notch on
the Mac used for capture.

| file | screen |
|---|---|
| 01-onboarding-welcome | first-run step 1: what it does / does not do |
| 02-onboarding-permissions | first-run step 2: live permission checks |
| 03-overview-test-typing | safe test mid-way: first keys landing in the test pad |
| 04-overview-blocking | status "Blocking a burst", red rhythm bar, explanation |
| 05-overview-protected | resting state |
| 06-timeline | incident list |
| 07-incident-expanded | reasons, measurements, text that reached the app vs dropped |
| 08-devices | keyboard inventory with trust controls |
| 09-settings | settings |
| 10-menubar-icon-states | protected / alert / paused icons |
