"""Headless self-test: no GUI, no permissions, no files outside a temp dir.

    DuckyGuard.app/Contents/MacOS/DuckyGuard --self-test     (inside the packaged app)
    python -m duckyguard selftest                            (from source)

Checks that the detector blocks an 8 ms and a 30 ms synthetic burst, does not
block a human-paced one, that the store works in a temp dir, and that the
package imports without needing anything from the machine that built it.
This is a software check. It does not prove anything about USB hardware.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

from . import __version__


def run() -> int:
    from .detector import KeyEvent, KeystrokeAnomalyDetector

    def first_block(gap, n=40):
        det = KeystrokeAnomalyDetector()
        for i in range(n):
            if det.observe(KeyEvent(timestamp=i * gap, char="abcdefgh"[i % 8])).block:
                return i + 1
        return None

    def spotlight_opener_block():
        det = KeystrokeAnomalyDetector()
        det.observe(KeyEvent(timestamp=0.0, char="[cmd]", modifier=True))
        det.observe(KeyEvent(timestamp=0.010, char=" "))
        t = 0.350
        for idx, ch in enumerate("terminal\n"):
            t += 0.025
            if det.observe(KeyEvent(timestamp=t, char=ch)).block:
                return idx + 1
        return None

    results = {
        "version": __version__,
        "python": sys.version.split()[0],
        "package_path_is_inside_app": "Contents/Resources" in os.path.abspath(__file__),
        "ducky_8ms_blocked_at_key": first_block(0.008),
        "even_30ms_blocked_at_key": first_block(0.030),
        "spotlight_opener_blocked_at_key": spotlight_opener_block(),
        "human_240ms_blocked_at_key": first_block(0.240),
    }
    ok = (results["ducky_8ms_blocked_at_key"] is not None
          and results["even_30ms_blocked_at_key"] is not None
          and results["spotlight_opener_blocked_at_key"] is not None
          and results["spotlight_opener_blocked_at_key"] <= 6
          and results["human_240ms_blocked_at_key"] is None)
    try:
        from .store import Store
        with tempfile.TemporaryDirectory() as d:
            s = Store(d)
            s.append_audit("selftest", {"version": __version__})
            audit_ok = s.verify_audit()["ok"]
            results["store"] = "ok" if (s.settings() is not None and audit_ok) else "empty"
            ok = ok and audit_ok
    except Exception as e:  # report, do not hide
        results["store"] = f"error: {e}"
        ok = False
    results["ok"] = ok
    print(json.dumps(results, indent=2))
    return 0 if ok else 1
