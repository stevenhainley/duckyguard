# DuckyGuard threat model (v2)

## What DuckyGuard defends against

A device that enumerates as a USB or Bluetooth keyboard and types a scripted
payload: Hak5 USB Rubber Ducky, Flipper Zero BadUSB, Raspberry Pi Pico with
pico-ducky, Arduino/Teensy `Keyboard.h` sketches, O.MG cables, Bash Bunny in
HID mode. These type at 8-40 ms per key with near-constant gaps and release
each key almost instantly; a hand cannot.

Scenarios it is built for:

- **Dropped USB stick / "free gift"**: the victim plugs it in; it opens
  Spotlight or Terminal and types a one-line dropper.
- **Walk-by / evil maid**: someone plugs a Flipper into an unlocked laptop
  for a few seconds.
- **Trojanized cable or dongle**: an O.MG-style cable injects remotely.

In every case DuckyGuard sees the first keys, decides on the 8th to 12th, and
drops the rest. It tells the user what was typed before the decision and what
was dropped, and which keyboard appeared shortly before (attributed by time).

## What it does not defend against

| attack | why not | mitigation outside DuckyGuard |
|---|---|---|
| Payloads short enough to finish in 7 keys | the decision needs a burst to measure | none from DuckyGuard; keep Spotlight shortcuts and Terminal access in mind |
| Slow payloads with randomised gaps (8-12 keys/s, jittered) | they look human on every timing signal; lowering thresholds would block fast typists | they take a minute at the keyboard and are visible on screen |
| Mass-storage or network BadUSB (USB Ethernet gadgets, fake drives with autorun-style tricks) | DuckyGuard only looks at keystrokes | USB device policies, no auto-mount |
| Mouse-only injection | mouse events are not scored | none |
| Software keystroke injection by malware already on the Mac | events from local processes are labelled, not blocked, by default (password managers need this); the expert setting can score them | that malware already has your session; DuckyGuard is not an antivirus |
| A device that first waits, then types one key per second | below every rule | the attacker needs minutes |
| Attacks while DuckyGuard is paused or not granted Accessibility | obvious | the menu bar icon shows paused (grey) and the Overview says "Observing only" |
| Disabling DuckyGuard by typing into it | the tap drops keys before any app, including DuckyGuard's own window, during quarantine; but a payload could Cmd+Q the app before the decision (that is a 2-key burst) | launch at login restarts it next session only; a future version could refuse Cmd+Q while a burst is in progress |

## Assumptions

- macOS 26+ (release build; older versions untested) with Input Monitoring (to see keystrokes) and Accessibility (to
  drop them) granted to DuckyGuard. Without Accessibility it only warns.
- Hardware key events carry source pid 0 and synthesized events carry the
  poster's pid (documented by Apple; pynput depends on it; not verified here
  against every macOS release).
- The attacker does not have root or a kernel extension; at that level the
  tap can be removed.
- A CGEvent tap that takes too long is disabled by macOS; DuckyGuard keeps
  the callback under a millisecond and re-enables the tap if it is turned off.

## Data handling

Captured text (both the part that reached an app and the dropped part) is
stored locally in `~/Library/Application Support/DuckyGuard/incidents/`, mode
0600. It can contain whatever the device typed, including secrets if the
payload carried them. Nothing is uploaded. Exported reports go to
`exports/` in the same folder and are revealed in Finder, not shared.

## Verification status

No hardware test has been run. All detection figures are simulations of
published human timing and injector timing (`docs/EVALUATION.md`). The first
thing to do with a real Rubber Ducky or Flipper is to run its default
payload against a text editor with DuckyGuard on, and record which characters
arrived before the block.
