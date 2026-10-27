"""Replay tests: payloads from captures/ fed at the timings the capture was made with."""

import glob
import os
import re

import pytest

from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector
from duckyguard.incidents import analyze_text

CAPTURES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "captures", "sample-*.txt")))


def load_payload(path):
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if not l.startswith("#")]
    text = "\n".join(lines).strip("\n")
    # strip v1 token noise such as [<75>] from the raw log
    return re.sub(r"\[<\d+>\]", "", text)


@pytest.mark.parametrize("path", CAPTURES, ids=[os.path.basename(p) for p in CAPTURES])
@pytest.mark.parametrize("interval_ms", [12, 30])
def test_capture_replay_is_blocked(path, interval_ms):
    payload = load_payload(path)
    assert payload, "capture is empty"
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for i, ch in enumerate(payload):
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.004))
        if v.block:
            assert i + 1 <= 8
            break
        t += interval_ms / 1000.0
    else:
        pytest.fail("capture replay was never blocked")


@pytest.mark.parametrize("path", CAPTURES, ids=[os.path.basename(p) for p in CAPTURES])
def test_capture_analysis_extracts_indicators(path):
    an = analyze_text(load_payload(path))
    assert an["urls"] or an["ips"]
    assert an["mitre"][0]["id"] == "T1200"
    assert an["yara"] and "rule DuckyGuard_HID_payload" in an["yara"]
