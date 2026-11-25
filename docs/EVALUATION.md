# DuckyGuard evaluation (2.0 and 2.1)

**Section 0 is a hardware test on one device. Everything after it is a simulation or a
measurement of the code on one Mac**, and is labelled as such. Reproduce with:

```bash
.venv/bin/python bench/simulate.py --n 1000 --seed 2026
.venv/bin/python -m pytest -q
```

Machine: MacBook Pro, Apple silicon (arm64), macOS 26.6, Python 3.14.8,
2026-10-26 (detector rules G/H/S and re-run 2026-10-27, same machine).

## 0. Hardware results (Flipper Zero, 2026-11-10)

Device: Flipper Zero, Momentum firmware `mntm-dev` (build 2026-08-18), typing through the firmware's
JavaScript `badusb` module (same HID stack as the Bad KB app; the Bad KB app itself was not run),
VID:PID 046d:c529, connected through a USB 2.0 hub. Host: Apple silicon MacBook, macOS 26, DuckyGuard
CLI engine with Input Monitoring and Accessibility. Payload: a harmless 124-character sentence typed
into a dedicated text window; "got through" means it arrived in that window. Harness and raw
results: `bench/hardware/`. Recordings replayed by the test suite: `captures/hardware/`.

What the device actually does (listen-only recording, DuckyGuard off):

- Full speed: median 4.0 ms between key-downs, about 275 keys/s, and **irregular** (the detector
  measured CV 0.6-1.25, because USB delivers reports in uneven clumps). The simulation assumed
  CV < 0.1 at default speed, so rule G did not fire on hardware and v2.0 blocked on rule A1 at key 12.
- With a per-key delay (10-100 ms): metronomic, CV 0.002-0.1, as the simulation assumed.
- **Every key was released 1-2 ms after it was pressed, at every speed, including the jittered
  payload.** Humans hold a key 60-150 ms.
- The CGEvent tap does receive key events from this external USB keyboard on macOS 26.

| payload (124 harmless characters) | characters that got through, v2.0 | with the key press rules (2.1) |
|---|---|---|
| full speed, about 4 ms per key | 11 | 4 |
| 100 ms per key, typed right after plug-in | 7 | 1 (within 30 s of a previous block) |
| 100 ms per key, typed 15 s after plug-in | 19 | 5 |
| random 60-140 ms per key, right after plug-in | 124 (not blocked) | 3 |
| random 60-140 ms per key, 15 s after plug-in | 124 (not blocked) | 5 |

One run per row; this is a functional check, not a statistical sample. v2.0 also blocked 10, 25 and
50 ms per key (5-10 characters got through; two of those runs include stray operator keystrokes).

Rules added from these measurements (`src/duckyguard/detector.py`):

| rule | fires when | notes |
|---|---|---|
| J | 5 keys less than 20 ms apart, each released in under 10 ms | full-speed injectors, on the 5th key |
| K | 6 keys in a row each released in under 10 ms, at any speed, across pauses | catches jittered and slow payloads; decided on the 7th key |
| L | 4 such keys within 10 s of an untrusted keyboard appearing | decided on the 5th key |
| M | 2 such keys within 30 s of a key press block | a blocked device that keeps typing after the block ends |

A key pressed while the previous key is still down (rollover, which hands do constantly) ends the
run, and so does one normally held key. Known false-positive risk: firmware that emits a tap as an
instant press-release (QMK mod-tap or tap-dance keys, some macro pads) can produce runs of short
holds; six in a row at typing speed is needed before rule K fires. Not tested on such keyboards.
An attacker can defeat these rules by scripting a 60 ms+ hold per key, which also slows the payload.

New-keyboard hold (2026-11-11, same device and Mac): the Flipper presented an identity that was not on the
trust list, typed at full speed 3.5 s after connecting (one run) and 1.2 s after connecting (two runs), and
0 of 124 characters got through each time; DuckyGuard blocked all 124 keys. The hold blocks every
hardware key, including the built-in keyboard, because key events carry no device identity. A payload typing
0.3 s after connecting produced no key events at all on this Mac, with or without DuckyGuard, so the
"types the instant it enumerates" case could not be exercised; the rescan-on-first-key path is covered by
unit tests only.

Human false positives in simulation are unchanged by rules J-M: 0/7000 on seeds 2026 and 7, 2/7000
on seed 99, the same as before the change.

The tables in sections 2 to 4 were produced before rules J-M existed. Re-running
`bench/simulate.py` with them gives 5-7 keys before the block for every simulated injector that
releases keys instantly, including the "slow + randomised 80-120 ms" row (previously 0% caught);
the "no key press information" rows are unchanged.

## 1. What the detector decides on

For every hardware key-down the detector looks at the current *burst* (keys
with no gap longer than 350 ms) and computes: keys per second, median gap,
coefficient of variation (CV) of the gaps, median key hold time (when key-up
events are seen), burst length, whether the last ~96 characters look like a
dropper or shell command, and whether an untrusted keyboard appeared in the
last 10 seconds. The decision rules (`src/duckyguard/detector.py`):

| rule | fires when | meant to catch |
|---|---|---|
| A1 | >= 35 keys/s for 12 keys | any injector at default speed; no hand does this |
| A2 | >= 25 keys/s for 12 keys with CV < 0.25 | fast injectors with some jitter |
| B | >= 20 keys/s, CV < 0.08, 8 keys | metronomic injectors, the usual case |
| C | >= 16 keys/s, CV < 0.08, 12 keys | slower metronomic payloads |
| D | >= 6 keys/s, CV < 0.05, 20 keys | DEFAULT_DELAY payloads typed at human speed with machine regularity |
| E | payload pattern or fresh untrusted keyboard, score >= 0.75, 8 keys, CV < 0.15 | corroborated bursts |
| F | score >= 0.90 over 8 keys | everything at once |
| G (added before release) | >= 40 keys/s, CV < 0.10, 6 keys | Rubber Ducky / Pico default speed, blocked on the 6th key instead of the 8th |
| H (added before release) | untrusted keyboard seen in the last 10 s, >= 22 keys/s, CV < 0.08, 6 keys | fast metronomic burst right after a new keyboard appears |
| P1 (2.2) | hardware `Cmd+Space` chord followed within 5 s by a fast terminal/launcher name (`>= 16` keys/s, CV `< 0.22`, 6 keys) | Spotlight-to-Terminal openers stopped before Return |
| P2 (2.2) | shell or dropper command pattern, `>= 18` keys/s, CV `< 0.25`, 8 keys | jittered dropper commands that bypass rule E's 15% CV cap |
| S (added before release) | the current burst was already blocked and has not paused > 350 ms | an attacker who slows down or adds jitter mid-payload to shake the detector |

Human reference ranges used for the thresholds and the simulation:
Dhakal et al., CHI 2018 (136M keystrokes: mean 52 WPM, inter-key interval
~240 ms; fastest cohort ~120 WPM, ~100 ms); Killourhy & Maxion, DSN 2009
(down-down latencies 100-400 ms, hold 60-150 ms, per-person CV 0.3-0.7);
public competitive-typing replays (peak ~17 keys/s with CV still >= 0.25).

Software-synthesized keystrokes (events that carry a source process id:
password managers, text expanders, dictation, scripts, DuckyGuard's own test)
are labelled and not scored unless test mode or the expert setting is on.
Key auto-repeat and modifier keys are never timed.

## 2. False positives (simulation)

Each profile draws inter-key gaps from a log-normal distribution with the
published mean and CV; "pauses" adds thinking pauses. 1000 runs per profile.

| profile | runs | blocked | FP rate |
|---|---:|---:|---:|
| average typist 52 WPM | 1000 | 0 | 0.00% |
| fast typist 100 WPM | 1000 | 0 | 0.00% |
| very fast typist 150 WPM | 1000 | 0 | 0.00% |
| record burst 210 WPM (peak, CV 0.28) | 1000 | 0 | 0.00% |
| key mashing (two-hand roll, 20-90 ms uniform) | 1000 | 0 | 0.00% |
| rhythmic gamer spam (WASD, 70 ms, CV 0.22) | 1000 | 0 | 0.00% |
| hunt and peck 25 WPM | 1000 | 0 | 0.00% |
| **all human profiles** | **7000** | **0** | **0.000%** |

Seed 2026 gives 0/7000. Other seeds are not always zero: before rules G/H/S, seed 99 gave 2/7000 (0.029%) and the final rules give the same 2/7000
on that seed; seed 7 gives 0/7000 before and after. The new rules G and H
did not add any false positive on seeds 2026, 7 or 99 once their thresholds
were tightened (a first draft of G with CV < 0.15 blocked 1 of 1000
key-mashing runs, which is why it was tightened to CV < 0.10).

Hardest case: the same humans typing within 10 s of plugging in an untrusted
keyboard (rules E and H are armed). 100 runs each, seed 2026: 0% for five
profiles, **3%** for the 210 WPM record burst and **4%** for rhythmic WASD
spam (the pre-G/H/S build measured 2% and 3% on the same test; with 100 runs that
difference is within noise but it is not proven to be zero). In other words a
competitive typist who plugs in a new keyboard and immediately types at peak
speed with unusually even rhythm can be blocked once; trusting the keyboard
removes the extra suspicion.

Bursty human input that is not keystrokes at all:

| input | result |
|---|---|
| password manager / text expander / dictation (400 keys at 5 ms, source pid set) | 0 blocked, labelled `software` |
| Cmd+V paste | one key event, never a burst |
| key held down (auto-repeat at 30 ms x 400) | 0 blocked, labelled `ignored` |
| IME composition | committed text is not key events; the composing keystrokes are human-paced |

## 3. Detection (simulation)

Injector profiles use fixed gaps with +-1-3 ms jitter and 2-5 ms hold times,
matching DuckyScript defaults and the 12 ms timing of `captures/sample-flipper-attack.txt`.
1000 runs each.

| profile | caught | median keys before block | median ms from first key |
|---|---:|---:|---:|
| Rubber Ducky default (~8 ms/key) | 100% | 6 | 40 |
| Flipper BadUSB 12 ms/key | 100% | 6 | 60 |
| Pico ducky 20 ms/key | 100% | 6 | 100 |
| evasion: even 30 ms, no shell pattern (claims-audit gap) | 100% | 8 | 210 |
| evasion: even 40 ms, no shell pattern | 100% | 8 | 280 |
| evasion: 60 ms +-3 ms jitter | 100% | 12 | 660 |
| slow payload: even 100 ms (DEFAULT_DELAY 100) | 100% | 20 | 1900 |
| slow + randomised 80-120 ms | **0%** | - | - |
| Spotlight then Terminal, 15 ms | 100% | 6 | 75 |

Without key-up information (hold times unknown) the results are identical (re-measured after G/H/S),
so detection does not depend on key press data.

**The miss is deliberate.** A payload typed at 8-12 keys/s with randomised
gaps is inside the human range on every signal DuckyGuard measures. Such a
payload takes a minute or more to type and the attacker has to stand there;
the threat model (`docs/THREAT_MODEL.md`) says so. Lowering the thresholds to
catch it would block fast human typists.

### Before / after (v1.0.0 detector, same harness, 300 runs)

| profile | v1.0.0 | v2.0.0 |
|---|---|---|
| all seven human profiles | 0% FP | 0% FP |
| Rubber Ducky 8 ms / Flipper 12 ms / Pico 20 ms | caught, 12 keys | caught, 6 keys (before G/H/S: 8) |
| even 30 ms, no pattern, no new USB | **missed (0%)** | caught, 8 keys |
| even 40 ms, no pattern | **missed** | caught, 8 keys |
| 60 ms +-3 ms | **missed** | caught, 12 keys |
| even 100 ms | **missed** | caught, 20 keys |
| randomised 80-120 ms | missed | missed |

v1 also had two bugs fixed in v2: `timestamp=0.0` was treated as "no
timestamp", and the 12-key text window could never match the 13-character
`curl -sL http` pattern (`tests/test_detector.py::test_pattern_matches_across_long_text_window`).

## 4. How many keys get through

DuckyGuard decides on the Nth key of a burst, so N-1 keys get through to the front
application before the block (the Nth is blocked). In simulation N is 6 at
injector speed up to 25 ms/key (8 for even 30-40 ms payloads with no other signal); in the live safe test on this Mac N was 8 to 12 (the first
keys land while the window is still activating, which adds jitter). A payload
that opens Spotlight and types `terminal` + Return has sent 9 key events;
with N = 6 or 8 the Return is blocked, with N = 12 it is not. The earlier live safe test (N = 8 to 12) predates rules G/H/S and has not been repeated. **DuckyGuard does not
guarantee that the first command never runs.** The v1 report text
"NEUTRALIZED & CONTAINED (Zero Command Execution)" was removed for that
reason; v2 reports list exactly which characters got through.

## 5. Latency (measured)

Two different numbers, both measured, neither a hardware number:

- **Decision cost per key** (`observe()` in isolation, 20,000 synthetic keys,
  `bench/simulate.py --latency-only`): median 49 us, p99 150 us on this Mac.
- **Tap callback cost** (event arrives in the CGEvent tap to the drop/pass
  decision, live engine, 152 synthetic keys during a safe test): median 14 us,
  p99 691 us. The p99 is the first key of a burst, when the burst list is
  reset.

So the time from a key *event* to its verdict is well under a millisecond.
The time from the *first* key of an attack to the block is N-1 gaps, i.e.
~60-280 ms for injectors at 8-40 ms per key (table in section 3). The old
"under 100 ms" claim was never measured and is not made any more; "under
100 ms" is true only for injectors faster than ~14 ms per key.

Keyboard inventory poll (IOKit registry read every 2 s): 3.5 ms per poll,
measured. The v1 `ioreg` subprocess took 200-400 ms per poll.

## 6. Resource use (measured)

Measured on the 2.0 build, before the 3D duck and the 2.1 dashboard, and not
repeated since. The duck draws only while the window is visible, so the
hidden-window figure is the one least likely to have moved, but that is an
expectation, not a measurement.

`dist/DuckyGuard.app` built by `packaging/build.sh`, window hidden, idle for
60 s, `ps` cputime delta: **0.80% CPU, RSS 121 MB**. Running from source in
the venv with the window hidden: 1.9% CPU, 84 MB. The RSS is mostly the
Python runtime plus the AppKit/WebKit bridges loaded into the process; the
web view's rendering lives in a separate WebKit process not counted here.
Targets for a later release: under 0.3% idle, under 60 MB.

## 7. Tests

`.venv/bin/python -m pytest -q`: 123 tests pass as of 2.1 (49 at 2.0). Unit
tests for the detector, store, devices and incidents; the key press rules;
holds, the lookalike check, Record only and lock on block; injector
identities, exports and the test payloads; the safe test's sentence and its
refusal to press Return; timed pause; noticing a permission granted after
launch; replay of `captures/sample-flipper-attack.txt` and of the Flipper
recordings in `captures/hardware/`; hypothesis property tests for timing edge
cases such as zero and negative gaps, clock going backwards, infinite rates,
short fast bursts separated by pauses, and "every block has reasons". The
window, the menus and the tap itself are not covered by automated tests.

## 8. Not verified

- Any real Rubber Ducky, Pico, O.MG cable or Bash Bunny, and the Flipper Zero's own Bad KB app (section 0 covers one Flipper Zero through its JavaScript `badusb` module).
- Security keys that type a code, barcode scanners, macro pads and QMK tap keys (expected to be held or blocked; none tested).
- That hardware key events on every macOS version carry source pid 0 (Apple
  documents it; pynput relies on it; checked here only with synthetic events).
- Intel Macs and macOS before 26 (the released app is built for and run on macOS 26 / arm64 only; the bundled Python has minos 26.0).
- Behaviour with a second physical keyboard attached (none available).
