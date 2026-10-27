<p align="center">
  <img src="assets/duck_isolated_usb.png" alt="DuckyGuard" width="120" />
</p>

<h1 align="center">DuckyGuard.</h1>

<p align="center"><strong>Keyboards that type too fast get stopped.</strong><br>
A free macOS menu bar app that blocks keystroke-injection devices (Rubber Ducky, Flipper Zero BadUSB, pico-ducky, O.MG cable) by the rhythm of their typing.</p>

---

## What it does

A USB device can claim to be a keyboard and type a command in under a second.
macOS, like every OS, trusts keyboards. DuckyGuard watches the timing of every
keystroke on the Mac. When a burst is faster and more even than any hand, it
drops the rest of that burst inside the system event tap, before the keys
reach an application, and tells you why in plain English:

> A keyboard typed 12 keys in 0.2 s (70 keys/s), about 9x faster than a fast typist. Keys held for 0 ms each; humans hold 60-150 ms. DuckyGuard blocked it.

- **Blocks, not just warns.** With the Accessibility permission, dropped keys never reach any app. With only Input Monitoring, it observes and warns.
- **Explains every block.** Rate, gap regularity, key hold time, burst length, payload text and whether an unknown keyboard just appeared, each as a sentence and a number.
- **Knows your keyboards.** Lists connected keyboards from IOKit; "Trust this keyboard" stops a known keyboard from raising suspicion when plugged in.
- **Leaves software typing alone.** Password managers, text expanders and dictation type like machines on purpose; their events carry a process id and are labelled, not blocked.
- **Test it safely.** One click types a harmless sentence into DuckyGuard's own window at 12 ms per key so you can watch the block happen. No hardware needed.
- **Private.** Incidents, trusted keyboards and settings live in `~/Library/Application Support/DuckyGuard` with owner-only permissions. The only network request is an opt-in, once-a-day update check.
- **Exportable.** One click writes a Markdown incident report; indicators, a MITRE ATT&CK mapping and a YARA rule are included only when the captured text actually contains something to base them on.

## What it does not do

Honesty is the product. Read this before relying on it.

- **The first keys get through.** DuckyGuard decides on the 8th to 12th key of a burst (simulation and the live test on one Mac; see `docs/EVALUATION.md`). A payload short enough to finish before that is not stopped.
- **Slow, randomised payloads are not caught.** A device typing at 8-12 keys/s with random gaps looks human on every signal DuckyGuard measures. It also needs a minute at the keyboard.
- **No hardware test has been run yet.** Every number in this repo is a simulation or a measurement of the code itself; see `docs/EVALUATION.md` for exactly what was measured and how to reproduce it.
- **It cannot prove which device typed.** macOS does not tag key events with their source device. Incidents say "attributed by time" when an untrusted keyboard appeared shortly before.
- **Not an antivirus, not a firewall.** It only looks at keystroke timing.
- **Not signed or notarized yet.** See `docs/INSTALL.md` for the one-time Gatekeeper step.

## Install

Download the DMG from a release (or build it: `./packaging/build.sh`), drag
DuckyGuard to Applications, right-click, Open. Then grant **Input Monitoring**
and **Accessibility** in System Settings, Privacy & Security; the first-run
screen walks you through it. Full steps: [`docs/INSTALL.md`](docs/INSTALL.md).

Requirements: macOS 12 or newer. Python and all libraries are inside the app.

## Run from source

```bash
git clone https://github.com/stevenhainley/DuckyGuard.git && cd DuckyGuard
python3 -m venv .venv && .venv/bin/pip install -e . pytest hypothesis
.venv/bin/python -m duckyguard app        # menu bar app
.venv/bin/python -m duckyguard start      # protection in the terminal, JSON events
.venv/bin/python -m duckyguard status     # permissions, keyboards, trusted devices
.venv/bin/python -m pytest -q             # 44 tests
.venv/bin/python bench/simulate.py        # simulation harness behind docs/EVALUATION.md
```

The terminal you run it from needs the two permissions instead of the app.

## Numbers (simulation and code measurements, not hardware)

| what | result |
|---|---|
| False positives on 7 simulated human profiles, 7000 runs | 0 |
| Injectors at 8-40 ms per key, even timing | 100% caught, median 8 keys before the block |
| Even 100 ms per key (DEFAULT_DELAY 100) | 100% caught at 20 keys |
| Randomised 80-120 ms per key | 0% caught, by design |
| Tap callback: key event to verdict | median 14 us, p99 0.7 ms (live engine, one Mac) |
| Idle cost of the built app | 0.8% CPU, 121 MB RSS (60 s, window hidden) |

Details, method and the v1-to-v2 comparison: [`docs/EVALUATION.md`](docs/EVALUATION.md).

## How it is built

Python 3 with PyObjC: a `rumps` status item, one AppKit window hosting a
local HTML dashboard in a WKWebView (no web server, no open port), a pynput
CGEvent tap for keystrokes, IOKit registry reads for keyboards. No kernel
extension, no helper daemon, no root. Packaged with py2app into a
self-contained unsigned `.app`. The v1 Swift window host and HTTP server are
kept under `legacy/` for reference only.

Docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md),
[`docs/FEATURES.md`](docs/FEATURES.md) (the canonical feature list),
[`docs/EVALUATION.md`](docs/EVALUATION.md),
[`docs/INSTALL.md`](docs/INSTALL.md),
[`docs/NOTARIZATION.md`](docs/NOTARIZATION.md),
[`CHANGELOG.md`](CHANGELOG.md).

## Support

DuckyGuard is free and will stay free. If it earned a place in your menu
bar, a pay-what-you-want contribution keeps it maintained (link coming with
the first public release).

## Author and license

Steven Hainley, sh. industries. MIT License, see `LICENSE`.
