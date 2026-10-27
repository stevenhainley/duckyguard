"""
DuckyGuard - keystroke timing detector (v2).

Decides, for every key-down, whether the stream of recent keystrokes looks like a
human or like a microcontroller replaying a script (Rubber Ducky, Flipper Zero,
Pico, O.MG cable...). The decision is explainable: every verdict carries the
measured features and the plain-English reasons that produced it.

Design notes
------------
* Only *hardware* key-downs are scored by default. Keystrokes synthesized by a
  process on this Mac (password managers, text expanders, dictation, our own
  simulator) carry a source PID in the event and are reported as "software
  typed" instead of being blocked, unless test mode is on.
* Key auto-repeat and modifier keys are excluded from timing: holding a key
  down produces perfectly regular ~30 ms events and would otherwise look like
  a machine.
* Features are computed on the current *burst*: the run of keystrokes with no
  gap longer than ``burst_gap_sec``. A new burst starts after any pause, so
  a human pausing to think never inherits a machine-like history.

Human reference ranges (published keystroke-dynamics work, see
docs/EVALUATION.md): mean inter-key interval 120-300 ms, coefficient of
variation 0.3-0.7, fastest sustained typists ~14-17 keys/s in short bursts,
key hold time 60-150 ms. Scripted injectors: 8-40 ms per key, CV < 0.1,
hold time 0-10 ms, constant for the whole payload.
"""

from __future__ import annotations

import collections
import re
import statistics
import threading
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class KeyEvent:
    """One key-down as seen by the engine."""

    timestamp: float                  # seconds (monotonic or wall clock, must be consistent)
    char: str = ""                    # printable char, or "[enter]"-style token
    injected: bool = False            # synthesized by a process on this Mac (has a source PID)
    repeat: bool = False              # key auto-repeat
    modifier: bool = False            # shift/ctrl/alt/cmd/fn
    hold_time: Optional[float] = None # seconds the *previous* key was held, if known
    source_pid: int = 0
    device_id: Optional[str] = None   # HID identity when known (not available via CGEvent)


@dataclass
class Verdict:
    block: bool
    score: float                      # 0.0 - 1.0, explainability only, not a probability
    reasons: List[str] = field(default_factory=list)
    features: Dict[str, object] = field(default_factory=dict)
    kind: str = "human"               # human | machine | software | buffering | ignored
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "block": self.block,
            "score": round(self.score, 2),
            "reasons": list(self.reasons),
            "features": dict(self.features),
            "kind": self.kind,
            "explanation": self.explanation,
        }


# Shell/dropper prefixes that make a fast burst far more suspicious.
SUSPICIOUS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"curl\s+(-[a-zA-Z]+\s+)*['\"]?https?://", re.IGNORECASE), "curl download"),
    (re.compile(r"wget\s+['\"]?https?://", re.IGNORECASE), "wget download"),
    (re.compile(r"powershell(\.exe)?\s+(-\w+\s+)*-(enc|e|ec|encodedcommand)\b", re.IGNORECASE), "encoded PowerShell"),
    (re.compile(r"chmod\s+\+x", re.IGNORECASE), "chmod +x"),
    (re.compile(r"/bin/(ba|z)?sh", re.IGNORECASE), "shell path"),
    (re.compile(r"\bnc\s+(-\w+\s+)*-e\b", re.IGNORECASE), "netcat shell"),
    (re.compile(r"base64\s+(-d|--decode)", re.IGNORECASE), "base64 decode"),
    (re.compile(r"/dev/tcp/", re.IGNORECASE), "bash reverse shell"),
    (re.compile(r"open\s+-a\s+Terminal", re.IGNORECASE), "opening Terminal"),
    (re.compile(r"osascript\s+-e", re.IGNORECASE), "osascript"),
    (re.compile(r"\|\s*(ba|z)?sh\b", re.IGNORECASE), "pipe to shell"),
]

MODIFIER_TOKENS = {"[shift]", "[shift_r]", "[ctrl]", "[ctrl_r]", "[alt]", "[alt_r]",
                   "[cmd]", "[cmd_r]", "[caps_lock]", "[fn]"}


class KeystrokeAnomalyDetector:
    """
    Rolling keystroke-timing analyser. Thread-safe. ``observe`` is the hot path
    and does a handful of arithmetic operations per key (see docs/EVALUATION.md
    for the measured cost).
    """

    def __init__(
        self,
        burst_gap_sec: float = 0.35,
        history: int = 64,
        text_window: int = 96,
        min_burst_for_verdict: int = 6,
        usb_recent_sec: float = 10.0,
        usb_age_callback=None,          # () -> Optional[float]: seconds since an *untrusted* keyboard appeared
        test_mode: bool = False,        # treat software-synthesized keys as hardware (for "Test it safely")
        score_software: bool = False,   # score software keys as if hardware (expert setting)
    ):
        self.burst_gap_sec = burst_gap_sec
        self.history = history
        self.text_window = text_window
        self.min_burst_for_verdict = min_burst_for_verdict
        self.usb_recent_sec = usb_recent_sec
        self.usb_age_callback = usb_age_callback
        self.test_mode = test_mode
        self.score_software = score_software

        self._lock = threading.Lock()
        self._burst: Deque[KeyEvent] = collections.deque(maxlen=history)
        self._text: Deque[str] = collections.deque(maxlen=text_window)
        self._holds: Deque[float] = collections.deque(maxlen=history)
        self._last_ts: Optional[float] = None
        self._burst_blocked = False     # current burst already flagged: stay blocked until a pause

        # Counters surfaced in the UI
        self.total_keys = 0
        self.software_keys = 0
        self.repeats_ignored = 0
        self.blocks = 0
        self.recent_events: Deque[dict] = collections.deque(maxlen=120)

    # ------------------------------------------------------------------ public

    def reset(self) -> None:
        with self._lock:
            self._burst.clear()
            self._text.clear()
            self._holds.clear()
            self._last_ts = None
            self._burst_blocked = False

    def observe(self, ev: KeyEvent) -> Verdict:
        """Score one key-down. Returns a Verdict; ``verdict.block`` is the decision."""
        with self._lock:
            self.total_keys += 1

            if ev.modifier or (ev.char and ev.char.lower() in MODIFIER_TOKENS):
                return Verdict(False, 0.0, kind="ignored", explanation="modifier key, not timed")
            if ev.repeat:
                self.repeats_ignored += 1
                return Verdict(False, 0.0, kind="ignored", explanation="key auto-repeat, not timed")

            if ev.injected and not (self.test_mode or self.score_software):
                self.software_keys += 1
                v = Verdict(False, 0.0, kind="software",
                            reasons=[f"typed by a program on this Mac (pid {ev.source_pid or '?'}), not by a USB device"],
                            explanation="Software-typed keystroke (password manager, text expander, dictation or a script). "
                                        "Not blocked: only hardware keyboards are scored.")
                v.features = {"source_pid": ev.source_pid}
                return v

            # Burst bookkeeping
            if self._last_ts is not None and (ev.timestamp - self._last_ts) > self.burst_gap_sec:
                self._burst.clear()
                self._holds.clear()
                self._burst_blocked = False
            elif self._last_ts is not None and ev.timestamp < self._last_ts:
                # Clock went backwards: never let a negative interval poison the stats.
                self._burst.clear()
                self._holds.clear()
                self._burst_blocked = False
            self._last_ts = ev.timestamp
            self._burst.append(ev)
            if ev.hold_time is not None and ev.hold_time >= 0:
                self._holds.append(ev.hold_time)
            if ev.char and not ev.char.startswith("["):
                self._text.append(ev.char)
            elif ev.char in ("\n", "\r"):
                self._text.append("\n")
            elif ev.char == " ":
                self._text.append(" ")

            verdict = self._score()
            if verdict.block:
                self._burst_blocked = True
            elif self._burst_blocked and verdict.kind != "buffering":
                # Same burst was already flagged as a machine and no pause has happened:
                # keep dropping it even if the attacker slows down or adds jitter mid-payload.
                verdict.block = True
                verdict.kind = "machine"
                verdict.features["rule"] = "S: continuation of a burst already blocked"
                verdict.reasons.append("this burst was already flagged as machine-typed and has not paused")
                verdict.explanation = "Continuation of a keystroke burst DuckyGuard already blocked."
                verdict.score = max(verdict.score, 0.75)
            if verdict.block:
                self.blocks += 1
            self.recent_events.append({
                "t": round(ev.timestamp, 3),
                "cps": verdict.features.get("cps", 0.0),
                "cv": verdict.features.get("cv"),
                "burst": verdict.features.get("burst_len", 0),
                "score": round(verdict.score, 2),
                "kind": verdict.kind,
                "block": verdict.block,
            })
            return verdict

    # Backwards-compatible shim used by the legacy web dashboard and old tests.
    def record_keystroke(self, char: str, timestamp: Optional[float] = None):
        import time as _t
        ts = _t.time() if timestamp is None else timestamp
        v = self.observe(KeyEvent(timestamp=ts, char=char))
        metrics = dict(v.features)
        metrics["confidence"] = round(v.score, 2)
        metrics["reasons"] = v.reasons
        return v.block, v.score, metrics

    # ----------------------------------------------------------------- scoring

    @staticmethod
    def features_from_intervals(intervals: List[float], holds: List[float]) -> Dict[str, object]:
        n = len(intervals)
        f: Dict[str, object] = {"burst_len": n + 1}
        if n == 0:
            return f
        mean = statistics.fmean(intervals)
        med = statistics.median(intervals)
        sd = statistics.pstdev(intervals) if n > 1 else 0.0
        cv = (sd / mean) if mean > 0 else 0.0
        span = sum(intervals)
        f.update({
            "cps": round(min(999.0, n / span), 1) if span > 1e-6 else 999.0,
            "mean_iki_ms": round(mean * 1000, 1),
            "median_iki_ms": round(med * 1000, 1),
            "sd_iki_ms": round(sd * 1000, 1),
            "cv": round(cv, 3),
            "min_iki_ms": round(min(intervals) * 1000, 1),
            "max_iki_ms": round(max(intervals) * 1000, 1),
            "span_ms": round(span * 1000, 1),
        })
        if holds:
            f["median_hold_ms"] = round(statistics.median(holds) * 1000, 1)
            f["hold_samples"] = len(holds)
        return f

    def _score(self) -> Verdict:
        burst = list(self._burst)
        intervals = [burst[i].timestamp - burst[i - 1].timestamp for i in range(1, len(burst))]
        holds = list(self._holds)
        feats = self.features_from_intervals(intervals, holds)
        n_keys = len(burst)

        text = "".join(self._text)
        pattern_name = None
        for pat, name in SUSPICIOUS_PATTERNS:
            if pat.search(text):
                pattern_name = name
                break
        feats["pattern"] = pattern_name

        usb_age = None
        if self.usb_age_callback is not None:
            try:
                usb_age = self.usb_age_callback()
            except Exception:
                usb_age = None
        feats["new_keyboard_age_s"] = round(usb_age, 1) if usb_age is not None else None
        new_keyboard = usb_age is not None and usb_age <= self.usb_recent_sec

        if n_keys < self.min_burst_for_verdict:
            return Verdict(False, 0.0, kind="buffering", features=feats,
                           explanation=f"{n_keys} keys in this burst, need {self.min_burst_for_verdict} to judge timing")

        cps = float(feats["cps"])
        cv = float(feats["cv"])
        med_hold = feats.get("median_hold_ms")
        reasons: List[str] = []
        score = 0.0

        # 1. Sustained speed beyond the human range.
        if cps >= 25:
            score += 0.45
            reasons.append(f"{n_keys} keys at {cps:.0f} keys/s, about {cps / 8:.0f}x a fast typist")
        elif cps >= 16:
            score += 0.25
            reasons.append(f"{n_keys} keys at {cps:.0f} keys/s, past the fastest sustained human typing")
        elif cps >= 12:
            score += 0.08

        # 2. Timing too regular for a human.
        if cv < 0.06 and n_keys >= 8:
            score += 0.40
            reasons.append(f"every key {feats['median_iki_ms']:.0f} ms apart (variation {cv * 100:.0f}%); humans vary 30-70%")
        elif cv < 0.12 and n_keys >= 8:
            score += 0.25
            reasons.append(f"keys {feats['median_iki_ms']:.0f} ms apart with only {cv * 100:.0f}% variation")
        elif cv < 0.20 and n_keys >= 10:
            score += 0.10

        # 3. Hold time: injectors release keys almost instantly.
        if med_hold is not None and feats.get("hold_samples", 0) >= 6:
            if med_hold < 15:
                score += 0.20
                reasons.append(f"keys held for {med_hold:.0f} ms each; humans hold 60-150 ms")
            elif med_hold < 35:
                score += 0.08

        # 4. Payload looks like a dropper / shell.
        if pattern_name:
            score += 0.25
            reasons.append(f"the text looks like a {pattern_name}")

        # 5. An unknown keyboard appeared seconds ago.
        if new_keyboard:
            score += 0.25
            reasons.append(f"an untrusted keyboard was plugged in {usb_age:.0f} s ago")

        # Human discounts: high variance proves a hand on the keys even at speed.
        if cv >= 0.30 and n_keys >= 6 and not pattern_name:
            score -= 0.30
            reasons.append(f"timing varies {cv * 100:.0f}% between keys, like a hand")

        score = max(0.0, min(1.0, score))

        # Decision rules (deliberately simple so they can be explained and tested).
        block = False
        rule = None
        if cps >= 35 and n_keys >= 12:
            block, rule = True, "A1: >=35 keys/s for 12 keys"          # no hand does this, even mashing
        elif cps >= 25 and n_keys >= 12 and cv < 0.25:
            block, rule = True, "A2: >=25 keys/s for 12 keys, low variation"
        elif cps >= 20 and cv < 0.08 and n_keys >= 8:
            block, rule = True, "B: >=20 keys/s, metronomic, 8 keys"
        elif cps >= 16 and cv < 0.08 and n_keys >= 12:
            block, rule = True, "C: >=16 keys/s, metronomic, 12 keys"
        elif cps >= 6 and cv < 0.05 and n_keys >= 20:
            block, rule = True, "D: slow but perfectly regular for 20 keys"   # DEFAULT_DELAY payloads
        elif cps >= 40 and cv < 0.10 and n_keys >= 6:
            block, rule = True, "G: >=40 keys/s with low variation, 6 keys"
        elif new_keyboard and cps >= 22 and cv < 0.08 and n_keys >= 6:
            block, rule = True, "H: >=22 keys/s, metronomic burst seconds after an untrusted keyboard appeared, 6 keys"
        elif (pattern_name or new_keyboard) and score >= 0.75 and n_keys >= 8 and cv < 0.15:
            block, rule = True, "E: corroborated by payload text or a fresh untrusted keyboard"
        elif score >= 0.90 and n_keys >= 8:
            block, rule = True, "F: every signal at once"
        feats["rule"] = rule

        kind = "machine" if block else "human"
        if block:
            explanation = self._explain_block(feats, reasons)
        else:
            explanation = "Looks like a person typing." if not reasons else "Fast, but still within human range."
        return Verdict(block, score, reasons, feats, kind, explanation)

    @staticmethod
    def _explain_block(feats: Dict[str, object], reasons: List[str]) -> str:
        n = feats.get("burst_len", 0)
        span = float(feats.get("span_ms", 0)) / 1000.0
        cps = float(feats.get("cps", 0))
        head = f"A keyboard typed {n} keys in {span:.1f} s ({cps:.0f} keys/s"
        head += f", about {max(1, round(cps / 8))}x faster than a fast typist)" if cps >= 16 else ")"
        rest = [r[0].upper() + r[1:] for r in reasons if "keys/s" not in r][:2]
        why = ("; ".join(rest) + ". ") if rest else ""
        return f"{head}. {why}DuckyGuard blocked it."
