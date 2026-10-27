# DuckyGuard 2.0 evaluation

**Everything in this document is either a simulation or a measurement of the
code on one Mac.** No keystroke-injection hardware was available while this
was written. Nothing here is a hardware result, and the README does not claim
one. Reproduce with:

```bash
.venv/bin/python bench/simulate.py --n 1000 --seed 2026
.venv/bin/python -m pytest -q
```

Machine: MacBook Pro, Apple silicon (arm64), macOS 26.6, Python 3.14.8,
2026-10-26.

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

Hardest case: the same humans typing within 10 s of plugging in an untrusted
keyboard (rule E is armed). 100 runs each: 0% for five profiles, **2%** for
the 210 WPM record burst and **3%** for rhythmic WASD spam. In other words a
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
| Rubber Ducky default (~8 ms/key) | 100% | 8 | 57 |
| Flipper BadUSB 12 ms/key | 100% | 8 | 84 |
| Pico ducky 20 ms/key | 100% | 8 | 140 |
| evasion: even 30 ms, no shell pattern (claims-audit gap) | 100% | 8 | 210 |
| evasion: even 40 ms, no shell pattern | 100% | 8 | 280 |
| evasion: 60 ms +-3 ms jitter | 100% | 12 | 660 |
| slow payload: even 100 ms (DEFAULT_DELAY 100) | 100% | 20 | 1900 |
| slow + randomised 80-120 ms | **0%** | - | - |
| Spotlight then Terminal, 15 ms | 100% | 8 | 105 |

Without key-up information (hold times unknown) the results are identical,
so detection does not depend on hold-time data.

**The miss is deliberate.** A payload typed at 8-12 keys/s with randomised
gaps is inside the human range on every signal DuckyGuard measures. Such a
payload takes a minute or more to type and the attacker has to stand there;
the threat model (`docs/THREAT_MODEL.md`) says so. Lowering the thresholds to
catch it would block fast human typists.

### Before / after (v1.0.0 detector, same harness, 300 runs)

| profile | v1.0.0 | v2.0.0 |
|---|---|---|
| all seven human profiles | 0% FP | 0% FP |
| Rubber Ducky 8 ms / Flipper 12 ms / Pico 20 ms | caught, 12 keys | caught, 8 keys |
| even 30 ms, no pattern, no new USB | **missed (0%)** | caught, 8 keys |
| even 40 ms, no pattern | **missed** | caught, 8 keys |
| 60 ms +-3 ms | **missed** | caught, 12 keys |
| even 100 ms | **missed** | caught, 20 keys |
| randomised 80-120 ms | missed | missed |

v1 also had two bugs fixed in v2: `timestamp=0.0` was treated as "no
timestamp", and the 12-key text window could never match the 13-character
`curl -sL http` pattern (`tests/test_detector.py::test_pattern_matches_across_long_text_window`).

## 4. How many keys get through

DuckyGuard decides on the Nth key of a burst, so N-1 keys reach the front
application before the block (the Nth is dropped). In simulation N is 8 at
injector speed; in the live safe test on this Mac N was 8 to 12 (the first
keys land while the window is still activating, which adds jitter). A payload
that opens Spotlight and types `terminal` + Return has sent 9 key events;
with N = 8 the Return is blocked, with N = 12 it is not. **DuckyGuard does not
guarantee that the first command never runs.** The v1 report text
"NEUTRALIZED & CONTAINED (Zero Command Execution)" was removed for that
reason; v2 reports list exactly which characters reached the app.

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

`dist/DuckyGuard.app` built by `packaging/build.sh`, window hidden, idle for
60 s, `ps` cputime delta: **0.80% CPU, RSS 121 MB**. Running from source in
the venv with the window hidden: 1.9% CPU, 84 MB. The RSS is mostly the
Python runtime plus the AppKit/WebKit bridges loaded into the process; the
web view's rendering lives in a separate WebKit process not counted here.
Targets for a later release: under 0.3% idle, under 60 MB.

## 7. Tests

`.venv/bin/python -m pytest -q`: 44 tests pass (unit tests for the detector,
store, devices, incidents; replay of `captures/sample-flipper-attack.txt` at 12
and 30 ms per key; hypothesis property tests for timing edge cases such as
zero and negative gaps, clock going backwards, infinite rates, short fast
bursts separated by pauses, and "every block has reasons").

## 8. Not verified

- Any real Rubber Ducky, Flipper Zero, Pico, O.MG cable or Bash Bunny.
- That hardware key events on every macOS version carry source pid 0 (Apple
  documents it; pynput relies on it; checked here only with synthetic events).
- Intel Macs, macOS 12-14 (built and run on macOS 26 / arm64 only).
- Behaviour with a second physical keyboard attached (none available).
