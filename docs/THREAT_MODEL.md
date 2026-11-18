# DuckyGuard threat model (v2.1)

## What DuckyGuard defends against

A device that enumerates as a USB or Bluetooth keyboard and types a scripted
payload: Hak5 USB Rubber Ducky, Flipper Zero BadUSB, Raspberry Pi Pico with
pico-ducky, Arduino/Teensy `Keyboard.h` sketches, O.MG cables, Bash Bunny in
HID mode. These type at 8-40 ms per key with near-constant gaps and let go
of each key almost instantly; a hand cannot.

Scenarios it is built for:

- **Dropped USB stick / "free gift"**: the victim plugs it in; it opens
  Spotlight or Terminal and types a one-line dropper.
- **Walk-by / evil maid**: someone plugs a Flipper into an unlocked laptop
  for a few seconds.
- **Trojanized cable or dongle**: an O.MG-style cable injects remotely.

If the device is a keyboard you have not trusted, it is held the moment it
appears and nothing it types gets through until you choose (0 of 124
characters in three Flipper Zero runs). If it is not held (the hold is off,
it ran out unanswered, or the keyboard was allowed), DuckyGuard sees the first
keys, decides on the 3rd to 7th (Flipper Zero hardware runs; 6th to 20th when
key press timing is unavailable), and blocks the rest. It tells the user what
got through before the decision and what was blocked, and which keyboard it
probably came from (the untrusted keyboard connected shortly before; macOS
does not say).

## What it does not defend against

| attack | why not | mitigation outside DuckyGuard |
|---|---|---|
| Payloads short enough to finish in 4 keys, from a keyboard that is already trusted or was allowed | the timing decision needs a few keys to measure; the hold stops these outright for untrusted keyboards | do not allow a keyboard you did not plug in |
| A held keyboard nobody answers for | the hold ends after the hold length (20 s by default) and the keyboard may type; only the timing rules stand between it and the Mac after that | turn on Away mode when you leave the Mac unlocked, or lock the screen |
| A device that copies a trusted keyboard's name and model numbers exactly while that keyboard is unplugged | identity strings are whatever the device says; only duplicates and serial changes are detectable | the timing and key press rules still apply to it |
| Typing into a password field (macOS Secure Input) | event taps receive no keys while Secure Input is on | DuckyGuard shows a notice; the hold cannot block keys during it |
| Slow payloads with randomised gaps **and** a scripted 60 ms+ key press | they look human on every signal; default injector firmware lets go of keys in 1-2 ms and is caught by the key press rules | they take a minute at the keyboard and are visible on screen |
| Mass-storage or network BadUSB (USB Ethernet gadgets, fake drives with autorun-style tricks) | DuckyGuard only looks at keystrokes and keyboards | USB device policies, no auto-mount |
| Mouse-only injection | mouse events are not scored | none |
| Software keystroke injection by malware already on the Mac | events from local processes are labelled, not blocked, by default (password managers need this); "Also judge typing from apps" in Settings can score them | that malware already has your session; DuckyGuard is not an antivirus |
| A device that first waits, then types one key per second | below every rule | the attacker needs minutes |
| Attacks while DuckyGuard is paused, in Record only, or not granted Accessibility | nothing is blocked in those states | the menu bar icon is dimmed when paused and shows the attention glyph when DuckyGuard cannot block or is in Record only; the window says "Paused", "Recording only" or "Can't block". A timed pause ends on its own |
| Disabling DuckyGuard by typing into it | reduced, not eliminated. During a hold or a block the tap blocks keys before any app, DuckyGuard's own window included. Outside those, the controls that turn protection down (Pause, turning Record only on, turning Hold new keyboards off, Trust, Always allow) ignore activation from the keyboard and need the trackpad or mouse, and DuckyGuard's menus carry no Cmd+Q. None of this has been tested against a live payload, and a device that also acts as a mouse could click | "Restart if it stops" (with Open at login) starts DuckyGuard again after a kill, not after Quit |
| Legitimate devices that type like injectors: security keys that type a code, barcode scanners, macro keys | they are indistinguishable from an injector by timing, so DuckyGuard holds or blocks them; trusting one stops the hold but not the timing rules | pause for a minute while you use one; not tested with any of these |

## Assumptions

- macOS 26+ (release build; older versions untested) with Input Monitoring (to see keystrokes) and Accessibility (to
  drop them) granted to DuckyGuard. Without Accessibility it only warns.
- Hardware key events carry source pid 0 and synthesized events carry the
  poster's pid (documented by Apple; pynput depends on it; not verified here
  against every macOS release).
- The attacker does not have root or a kernel extension; at that level the
  tap can be removed.
- A CGEvent tap that takes too long is disabled by macOS; DuckyGuard re-enables
  the tap if it is turned off. The measured callback cost is a median of 14 us
  (`docs/EVALUATION.md`). Sounds, notifications and the dashboard snapshot are
  handed to the main thread and do not run inside the callback. The exception
  is the first key after a pause, when the callback rescans keyboards (an
  IOKit read, measured at 3.5 ms) at most once a second.

## Data handling

DuckyGuard times every key and checks which keyboards are connected. To do
that it sees every key, and it keeps the characters of the current burst in
memory (up to 256) while the burst lasts.

When it blocks a burst it saves that burst's text, both the part that got
through and the blocked part, in
`~/Library/Application Support/DuckyGuard/incidents/`, mode 0600. That text
is whatever was typed: a payload, secrets the payload carried, or your own
typing if DuckyGuard blocked you by mistake. For a held keyboard only the
number of blocked keys is saved, not the keys. Nothing is uploaded. Exported
reports go to `exports/` in the same folder and are revealed in Finder, not
shared. Deleting an incident in the Timeline deletes its file after an
8-second Undo window.

The safe test types one fixed sentence with no command in it, never presses
Return, and types only while DuckyGuard's own window is the key window.

## Verification status

Hardware-tested on one device: a Flipper Zero on one Mac (`docs/EVALUATION.md`, section 0). Its Bad KB
app, a Rubber Ducky, a Pico and an O.MG cable have not been tested; figures for those are
simulations of published injector timing.
