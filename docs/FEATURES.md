# DuckyGuard 2.2 features

The canonical list. Every line is something the code in this repo does today;
the "where" column names the screen it appears on. Marketing copy, the website
and the launch video should not claim anything that is not on this list.
Hardware numbers are from one Flipper Zero on one Mac; simulation numbers
come from `docs/EVALUATION.md` and are labelled there.

Words used the same way everywhere: keys are **blocked** or **got through**;
a new keyboard is **held**; you **Trust** a keyboard (permanent) or **Allow
once**; **key press** is how long a key is down.

| feature | one-liner | where |
|---|---|---|
| Keystroke-timing detection | Judges each burst of hardware keystrokes by rate, rhythm, key press time, burst length and the text of the burst; machine-like bursts are blocked. | Runs in the background; Overview shows the verdict |
| Key press rules | Injectors let go of each key within 1-2 ms. A run of such keys is blocked at any typing speed, including randomised delays. | Background |
| Launcher and dropper sequence rules | A hardware `Cmd+Space` chord followed by a fast terminal name (rule P1) is blocked at 6 characters before Return opens the app, and jittered shell/dropper commands at `>= 18` keys/s (rule P2: `curl`, `python -c`, `security find-*-password`, `xattr -d com.apple.quarantine`, `launchctl`, `osascript`) are blocked up to 25% timing variation. | Background |
| Real blocking | Blocked keys never get through to any app: the CGEvent tap returns the event as None. Needs the Accessibility permission. Keys typed before the decision (1 to 5 on a Flipper Zero in hardware runs; up to 20 without key press timing) do get through to the front app. | Overview status "Protected" / "Blocking" |
| Can't block fallback | With Input Monitoring but no Accessibility, DuckyGuard still detects and records bursts but can only warn. A permission switched on later takes effect within about a second; the tap is rebuilt, no relaunch. | Status "Can't block" with an Open System Settings button |
| Status words | One word per state, the same in the window and the menu: Protected, Keyboard held, Blocking, Paused, Can't block, Recording only, Not protected. Only Protected is drawn in the neutral colour. Before the first data arrives the window says "Starting…", never "Protected". | Overview, menu bar |
| Sentence for every block | Every block says what happened in a sentence ("A keyboard pressed 6 keys in a row and let go of each within 1 ms...") plus the numbers behind it. | Overview, Timeline (opened incident) |
| Incident timeline | Every blocked burst is saved locally with the text that got through, the text that was blocked, the keyboard it probably came from and the reason. Delete and Clear all can be undone for 8 seconds. The badge counts incidents since you last opened the Timeline. | Timeline |
| "Was this you?" | An opened block offers Pause for 1 minute, with one line explaining that trusting a keyboard does not exempt it from the timing rules. | Timeline |
| Export incident report | One click writes a Markdown report (explanation, measurements, captured text, indicators, MITRE ATT&CK rows, a YARA rule only when the text contained a URL or IP) and reveals it in Finder. | Timeline > Export report |
| Keyboard inventory | Lists connected keyboards (name, maker, vendor/product id, transport, serial) from IOKit, and trusted keyboards that are not connected. | Devices |
| Hold new keyboards | From the moment an untrusted keyboard appears, every hardware key (your own keyboard included) is blocked until you choose Keep blocked, Allow once or Always allow, or unplug it. If nobody chooses, the hold ends after the hold length and the keyboard may type; it stays untrusted and the timing rules still apply. Keep blocked lasts until the keyboard is unplugged. On the first key after a pause DuckyGuard rescans keyboards, so a device the background scan has not seen yet is still held. 0 of 124 characters got through on a Flipper Zero in three runs. Only the number of blocked keys is stored, never the keys. | Overview prompt, Devices, menu bar menu |
| Hold length | 20 s (default), 1 min or 2 min. | Settings > Protection |
| Lookalike check | A second device with the same identity as a connected keyboard, a trusted keyboard whose serial number or SHA-256 descriptor fingerprint changed, and a different device with the model numbers of a keyboard you trust are flagged. Duplicates, changed serials and fingerprint mismatches are held even though the name is trusted. USB identity strings can be set to anything, so this is a tripwire, not proof. | Devices, hold prompt |
| Lockdown mode | Holds every external keyboard plugged in while Lockdown is on, trusted ones included, and never lets the hold expire. If an untrusted external keyboard is already connected when Lockdown is switched on, it is held at once. | Menu bar, Settings > Protection, `duckyguard lockdown` |
| Away mode | Holds never run out: nothing new can type until you are back to choose. | Settings > Protection |
| Record only | Notes what it would have blocked and blocks nothing. The status reads "Recording only" and the menu bar shows the attention icon while it is on. | Settings > Advanced |
| Lock the screen on a block | Optionally locks the screen when scripted typing is blocked (not for the safe test). Uses a private macOS call (no public one exists); not exercised on a live screen. | Settings > Protection |
| Restart if it stops | With Open at login, starts DuckyGuard again after a crash or a kill, not after a normal Quit. | Settings > General |
| Timed pause | Pause for 5 minutes, for 1 hour, or until you resume. A timed pause ends on its own and is not remembered: quitting and reopening during one starts protected. "Until I resume" is remembered. The window shows "Protection is off until 10:42." with Resume now. | Pause button, menu bar menu |
| Mouse only for turning protection down | Pause, turning Record only on, turning Hold new keyboards off, Trust and Always allow ignore activation from the keyboard and ask for the trackpad or mouse, because a device that was just plugged in can press Tab and Space. | Window |
| Secure Input notice | Reports when macOS Secure Input is on (a password field has focus). DuckyGuard cannot see or block keys while it is. | Notice bar |
| Injector identity table | Matches a keyboard against the default identities of known injection boards, curated from firmware sources and vendor docs with a source link per entry: definite (P4wnP1, Bash Bunny, Digispark, Flipper over Bluetooth, anything naming itself Flipper, Hak5's documented Apple spoof), likely (Flipper factory identity: Logitech ids with no name strings) and hobby boards (Pico, Arduino, Teensy, ESP32). Identities can be changed by the attacker, so a miss means nothing. | Devices, hold prompt, incidents |
| Vendor names | Shows the registered owner of a keyboard's vendor id from the USB ID database shipped with the app (3,430 vendors, about 100 KB), and flags an Apple, Logitech or Microsoft vendor id that carries another maker's name. | Devices |
| Script reconstruction | Incident reports rebuild what the device was typing as a Ducky-style script (STRING, ENTER, TAB...). An approximation from the captured keys, not the device's file. | Export |
| JSON and OCSF output | `incidents --json` for scripts; `export --format ocsf` writes an OCSF Detection Finding (class 2004). Hand-built, not validated against an OCSF server. | Terminal only |
| Test-payload pack | Five harmless scripts and one JavaScript payload in `test-payloads/` that only type a sentence, so you can check protection with your own device. | Repo |
| Trusted keyboards | Trust remembers a keyboard so plugging it in is not held. Trusted keyboards that type like a machine are still blocked. First run offers to trust the keyboards connected at that moment. The list persists in a 0600 file. | First run, Devices, Timeline (from a held-keyboard incident) |
| One notification per plug-in | A held keyboard gets one notification ("New Keyboard on Hold") and the window comes to the front. An untrusted keyboard that is not held gets one notification and the window stays where it is. A hold-ended notification is sent only when the hold ran out unanswered. Sent through `rumps` (NSUserNotification); delivery on macOS 26 has not been checked. | Notification |
| Software-typed input is left alone | Keystrokes synthesized by local programs (password managers, text expanders, dictation, scripts) carry a process id and are labelled, not blocked. "Also judge typing from apps" changes that and will block password managers. | Settings > Advanced |
| Safe test | Types one harmless sentence at 12 ms per key so you can watch the block happen. No command in the sentence, never presses Return, types only while DuckyGuard's own window is the key window and stops if it loses focus. The button is disabled while a test runs. | Overview > Run safe test, menu bar > Run Safe Test, Settings > About, empty Timeline |
| The duck | A 3D duck head (three.js) that turns toward the pointer and can be dragged. Six readings sit on it, each tied by a line to the part that shows it: Burst, Key press, Reads as, Rate, Last keys, Rhythm. The halo behind it has one spoke per recent key. On a hold or a block its eyes turn red; on a block the picture inverts. The readings are timing only, never which key. | Overview |
| Key tape | One bar per key under the duck, as tall as the key press was long; a blocked key is a red cross. | Overview |
| ASCII view | Shows the same live picture as characters. Also used on the first-run screen and the empty Timeline. | Overview > View as ASCII |
| Menu bar icon | Template duck glyph in four states: protected (solid), attention (with "!", shown for Can't block, Not protected, Recording only and errors), alert (inverted tile, for a hold or a block) and paused (dimmed). | Menu bar |
| Menu bar menu | Status line, Keep "name" Blocked and Allow "name" Once while a keyboard is held, Open DuckyGuard, Run Safe Test, Pause for 5 Minutes, Pause for 1 Hour, Pause Until I Resume (Resume Protection while paused), Mute Alerts, Settings…, About DuckyGuard, Quit DuckyGuard. | Menu bar |
| Keyboard shortcuts | Cmd+W closes the window, Cmd+M minimises, Cmd+C copies selected text, Cmd+A selects all, Cmd+, opens Settings, Cmd+1 to Cmd+4 switch tabs, Esc closes an opened incident. There is no Cmd+Q, on purpose (see `docs/THREAT_MODEL.md`). | Window |
| Window | One fixed-size, dark-only window. The bar with the tabs moves the window. Closing it does not stop protection. | Window |
| First run | Explains what DuckyGuard does and does not do, including that it saves the text of bursts it blocks; shows both permissions live with a button to the right System Settings page; offers to trust the keyboards connected now. Start protecting needs both permissions; "Start without blocking" appears when only Input Monitoring is on. It does not run the safe test for you. | First launch |
| Permission checks | Live `IOHIDCheckAccess` and `AXIsProcessTrusted` checks every second, with Open System Settings buttons. The Accessibility button also asks macOS to list DuckyGuard in that pane. | First run, Overview, Settings > Access |
| Mute alerts | Still blocks and records; no sound, no notification. | Settings > General, menu bar menu |
| Open at login | Writes a per-user LaunchAgent (works unsigned). | Settings > General |
| Update notice (opt-in) | At most one HTTPS request a day to GitHub's releases API; shows a notice and the result under the switch, never downloads. Off by default. | Settings > General |
| Private local storage | Everything lives in `~/Library/Application Support/DuckyGuard` (mode 0700, files 0600). No network use except the opt-in update check. The incident list is kept in memory and re-read only when the folder changes. | Settings > About |
| Failures are shown | Missing permission, tap failure, export failure and update failure each show a sentence instead of silently doing nothing. An error after start shows a notice with Restart protection. A window that loses contact with the app says "Not connected". Errors on the page are written to the app's log. Corrupt settings are set aside, not fatal. | Overview, notice bar, toasts |
| Command line | `duckyguard start / status / devices / audit / lockdown / simulate / incidents / export / bench / selftest`. | Terminal |
| Tamper-evident audit log | Security events (starts, pauses, keyboard attachments, holds, blocks, lockdown changes) are appended to `audit.jsonl` (mode 0600, 5 MB rotation) with a SHA-256 hash chain verified by `duckyguard audit --verify`. | Terminal (`duckyguard audit`) |
| Ad-hoc signed build + DMG | `packaging/build.sh` produces `dist/DuckyGuard.app` and a DMG with SHA-256; install script and Homebrew cask template included. | Not a screen |

How long keys stay blocked after the last blocked key of a burst is 2 s. It
is the `quarantine_seconds` value in `settings.json`; there is no control for
it in the window.

## Not features (do not claim)

- Hardware-tested on a Flipper Zero only (one Mac, one run per case). No Rubber Ducky, Pico or O.MG test yet.
- No per-keystroke device attribution: macOS does not tag key events with their source device; incidents say "Probably from".
- A payload scripted to hold each key 60 ms or more, with random 80-120 ms gaps, is not detected. Default injector behaviour (keys let go in 1-2 ms) is caught by the key press rules even with random gaps.
- Security keys that type a code, barcode scanners and macro keys type the way injectors do. DuckyGuard will hold or block them; there is no exemption for them, and none has been tested.
- No notification buttons: the choice for a held keyboard is made in the window or the menu bar menu.
- No PCAP, no hex viewer, no "enterprise exporter", no Pro tier, no license keys.
- Not signed with a Developer ID, not notarized; see `docs/NOTARIZATION.md`.
- Not an antivirus: DuckyGuard only looks at keystrokes and keyboards. It does save the text of bursts it blocks, on this Mac only.

## Screenshots

`docs/screens/*.png`, the 820 x 560 pt window at Retina 2x.

| file | screen |
|---|---|
| `overview.png` | Protected, the resting state |
| `hold.png` | a new keyboard held, with the three choices |
| `blocking.png` | the safe test being blocked |
| `timeline.png` | the incident list with one incident opened |
| `devices.png` | keyboard inventory with trust controls |
| `settings.png` | settings |
| `first-run.png` | the first-run screen |
