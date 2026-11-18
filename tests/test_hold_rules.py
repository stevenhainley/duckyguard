"""Hold-time rules, tested against recordings of a real Flipper Zero (captures/hardware/).

A keystroke injector presses and releases each key within a millisecond or two; a finger holds a key
for 60-150 ms. These tests replay hardware recordings through the same HoldTracker the engine uses and
check how many printable keys get through before the first block.
"""

import json
import os
import random

import pytest
from hypothesis import given, settings, strategies as st

from duckyguard.detector import HoldTracker, KeyEvent, KeystrokeAnomalyDetector

HW = os.path.join(os.path.dirname(__file__), "..", "captures", "hardware")


def load(name):
    with open(os.path.join(HW, name + ".json"), encoding="utf-8") as f:
        return json.load(f)["events"]


def replay(events, det, tracker=None, start=0):
    """Feed recorded [ms, d/u, key] events the way the engine does.

    Returns (printable keys that got through before the first block, index of the blocking event),
    or (None, None) if nothing was blocked.
    """
    tr = tracker or HoldTracker()
    passed = 0
    for i in range(start, len(events)):
        ms, kind, key = events[i]
        ts = ms / 1000.0
        if kind == "u":
            tr.key_up(key, ts)
            continue
        tr.key_down(key, ts)
        mod = key.startswith("Key.shift")
        ch = " " if key == "Key.space" else key
        ev = KeyEvent(timestamp=ts, char="[shift]" if mod else ch, modifier=mod,
                      hold_time=None if mod else tr.take())
        if det.observe(ev).block:
            return passed, i
        if not mod:
            passed += 1
    return None, None


def synth(keys):
    """Build an event list from (gap_ms, hold_ms) pairs, one key after another."""
    events, t = [], 0.0
    for n, (gap, hold) in enumerate(keys):
        t += gap
        events.append([t, "d", f"k{n}"])
        events.append([t + hold, "u", f"k{n}"])
    events.sort(key=lambda e: e[0])
    return events


# ------------------------------------------------------------------ HoldTracker

def test_tracker_reports_each_hold_once():
    tr = HoldTracker()
    tr.key_down("a", 1.000)
    tr.key_up("a", 1.002)
    assert tr.take() == pytest.approx(0.002)
    assert tr.take() is None


def test_tracker_has_nothing_while_the_previous_key_is_still_down():
    tr = HoldTracker()
    tr.key_down("a", 1.000)
    tr.key_down("b", 1.050)       # rollover: a is still held
    assert tr.take() is None
    tr.key_up("a", 1.110)
    assert tr.take() == pytest.approx(0.110)


# ------------------------------------------------------------- hardware replays

def test_full_speed_flipper_is_blocked_by_the_fifth_key():
    passed, _ = replay(load("flipper-fullspeed"), KeystrokeAnomalyDetector())
    assert passed is not None and passed <= 4


def test_jittered_flipper_is_blocked_within_six_keys():
    passed, _ = replay(load("flipper-jitter-60-140ms"), KeystrokeAnomalyDetector())
    assert passed is not None and passed <= 6


def test_jittered_flipper_right_after_plug_in_is_blocked_within_four_keys():
    det = KeystrokeAnomalyDetector(usb_age_callback=lambda: 2.0)
    passed, _ = replay(load("flipper-jitter-60-140ms"), det)
    assert passed is not None and passed <= 4


def test_100ms_flipper_without_a_new_keyboard_is_blocked_within_six_keys():
    passed, _ = replay(load("flipper-100ms"), KeystrokeAnomalyDetector())
    assert passed is not None and passed <= 6


def test_25ms_flipper_is_blocked_within_six_keys():
    passed, _ = replay(load("flipper-25ms"), KeystrokeAnomalyDetector())
    assert passed is not None and passed <= 6


def test_block_explains_the_instant_release():
    det = KeystrokeAnomalyDetector()
    events = load("flipper-jitter-60-140ms")
    _, i = replay(events, det)
    assert i is not None
    last = det.recent_events[-1]
    assert last["block"] is True
    # replay once more to read the verdict itself
    det2, tr, verdict = KeystrokeAnomalyDetector(), HoldTracker(), None
    for ms, kind, key in events[: i + 1]:
        if kind == "u":
            tr.key_up(key, ms / 1000.0)
            continue
        tr.key_down(key, ms / 1000.0)
        mod = key.startswith("Key.shift")
        verdict = det2.observe(KeyEvent(timestamp=ms / 1000.0, char="[shift]" if mod else key, modifier=mod,
                                        hold_time=None if mod else tr.take()))
    assert verdict.block
    assert str(verdict.features["rule"]).startswith("K")
    assert any("released" in r for r in verdict.reasons)
    assert "DuckyGuard blocked it" in verdict.explanation


def test_instant_release_typing_that_resumes_after_a_block_is_stopped_within_two_keys():
    det, tr = KeystrokeAnomalyDetector(), HoldTracker()
    events = load("flipper-jitter-60-140ms")
    _, i = replay(events, det, tr)
    assert i is not None
    det.reset()                                   # what the engine does when quarantine starts
    resume_at = events[i][0] + 2500               # quarantine is 2 s; the payload is still typing
    j = next(n for n, e in enumerate(events) if e[0] >= resume_at and e[1] == "d")
    passed, _ = replay(events, det, tr, start=j)
    assert passed is not None and passed <= 2


def test_slow_instant_release_injector_is_blocked_across_pauses():
    # 450 ms between keys: every key starts a new burst, so only the hold time gives it away.
    events = synth([(450, 1.5)] * 20)
    passed, _ = replay(events, KeystrokeAnomalyDetector())
    assert passed is not None and passed <= 6


# ------------------------------------------------------------------- human side

def test_fast_roll_with_normal_holds_is_not_blocked_early():
    rng = random.Random(7)
    events = synth([(rng.uniform(12, 19), rng.uniform(70, 130)) for _ in range(8)])
    passed, _ = replay(events, KeystrokeAnomalyDetector())
    assert passed is None


def test_five_instant_release_keys_at_typing_speed_are_not_blocked():
    # e.g. a firmware tap key (QMK mod-tap) typing a short word; five in a row is under the threshold.
    rng = random.Random(11)
    keys = [(rng.uniform(90, 170), 1.0) for _ in range(5)] + [(rng.uniform(90, 170), rng.uniform(70, 130)) for _ in range(10)]
    passed, _ = replay(synth(keys), KeystrokeAnomalyDetector())
    assert passed is None


def test_one_normal_hold_resets_the_instant_release_run():
    rng = random.Random(13)
    short = lambda: (rng.uniform(90, 170), 1.0)
    keys = [short() for _ in range(5)] + [(120, 95.0)] + [short() for _ in range(5)] + [(120, 95.0)]
    passed, _ = replay(synth(keys), KeystrokeAnomalyDetector())
    assert passed is None


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.floats(5, 500), st.floats(30, 300)), min_size=1, max_size=80))
def test_keys_held_30ms_or_longer_never_trigger_a_hold_rule(keys):
    det, t = KeystrokeAnomalyDetector(usb_age_callback=lambda: 1.0), 0.0
    for gap, hold in keys:
        t += gap / 1000.0
        v = det.observe(KeyEvent(timestamp=t, char="a", hold_time=hold / 1000.0))
        rule = str(v.features.get("rule") or "")
        assert not rule.startswith(("J", "K", "L", "M")), rule
