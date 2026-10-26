"""
DuckyGuard - Core Detection Engine
Analyzes keystroke dynamics (speed, jitter, entropy) and correlates USB events
to detect non-human Human Interface Device (HID) injection attacks in real time.
"""

import collections
import math
import re
import statistics
import threading
import time
from typing import Callable, Deque, List, Optional, Tuple


class KeystrokeAnomalyDetector:
    """
    Evaluates keystroke dynamics in real time using a multi-factor confidence scoring model:
    1. Keystroke Velocity (Chars per second)
    2. Timing Jitter / Entropy (Low variance in inter-keystroke intervals)
    3. Temporal USB Attachment Correlation (Keyboard enumerated in last N seconds)
    4. Payload Signature Pre-matching (Known dangerous shell command prefixes)
    """

    SUSPICIOUS_PATTERNS = [
        re.compile(r"curl\s+-[sSLf]*\s*http", re.IGNORECASE),
        re.compile(r"wget\s+http", re.IGNORECASE),
        re.compile(r"powershell\s+(-enc|-w\s+hidden)", re.IGNORECASE),
        re.compile(r"chmod\s+\+x", re.IGNORECASE),
        re.compile(r"/bin/(ba)?sh", re.IGNORECASE),
        re.compile(r"nc\s+-e", re.IGNORECASE),
        re.compile(r"base64\s+-d", re.IGNORECASE),
        re.compile(r"/dev/tcp/", re.IGNORECASE),
        re.compile(r"open\s+-a\s+Terminal", re.IGNORECASE),
    ]

    def __init__(
        self,
        window_size: int = 12,
        rate_threshold_cps: float = 20.0,
        jitter_threshold_sec: float = 0.012,
        confidence_threshold: float = 0.70,
        usb_watcher_callback: Optional[Callable[[], float]] = None,
    ):
        """
        :param window_size: Number of keystrokes in rolling analysis buffer.
        :param rate_threshold_cps: Characters per second that trigger high-speed suspicion.
        :param jitter_threshold_sec: Maximum standard deviation of timing for synthetic input.
        :param confidence_threshold: Aggregate score (0.0 - 1.0) required to trigger defense.
        :param usb_watcher_callback: Returns seconds since last USB keyboard connection.
        """
        self.window_size = window_size
        self.rate_threshold_cps = rate_threshold_cps
        self.jitter_threshold_sec = jitter_threshold_sec
        self.confidence_threshold = confidence_threshold
        self.get_time_since_last_usb = usb_watcher_callback

        self._history: Deque[Tuple[float, str]] = collections.deque(maxlen=window_size)
        self._lock = threading.Lock()
        self.total_keys_inspected = 0
        self.anomalies_detected = 0

    def record_keystroke(self, char: str, timestamp: Optional[float] = None) -> Tuple[bool, float, dict]:
        """
        Process an incoming keystroke event.
        Returns:
            is_anomaly (bool): True if confidence exceeds threshold.
            confidence (float): Calculated threat score between 0.0 and 1.0.
            metrics (dict): Breakdown of telemetry (cps, jitter, usb_age, patterns).
        """
        now = timestamp or time.time()
        with self._lock:
            self._history.append((now, char))
            self.total_keys_inspected += 1

            if len(self._history) < self.window_size:
                return False, 0.0, {"keys": len(self._history), "status": "buffering"}

            # Compute timing spans and intervals
            timestamps = [t for t, _ in self._history]
            span = timestamps[-1] - timestamps[0]
            if span <= 0.0001:
                span = 0.0001

            cps = (len(timestamps) - 1) / span
            intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]

            mean_interval = statistics.mean(intervals)
            try:
                jitter = statistics.stdev(intervals)
            except statistics.StatisticsError:
                jitter = 0.0

            # 1. Speed Score (0.0 to 0.40)
            if cps >= self.rate_threshold_cps * 2.0:  # > 40 chars/sec
                speed_score = 0.40
            elif cps >= self.rate_threshold_cps:       # > 20 chars/sec
                speed_score = 0.25 + (0.15 * (cps - self.rate_threshold_cps) / self.rate_threshold_cps)
            elif cps >= 14.0:                         # fast human boundary
                speed_score = 0.10
            else:
                speed_score = 0.0

            # 2. Synthetic Jitter Score (0.0 to 0.30)
            # Microcontrollers have near-zero jitter (delay loops or identical sleep calls)
            if jitter < 0.004:
                jitter_score = 0.30
            elif jitter < self.jitter_threshold_sec:
                jitter_score = 0.20
            elif jitter < 0.025:
                jitter_score = 0.08
            else:
                jitter_score = 0.0

            # 3. USB Insertion Correlation Score (0.0 to 0.35)
            usb_score = 0.0
            usb_age = None
            if self.get_time_since_last_usb:
                usb_age = self.get_time_since_last_usb()
                if usb_age is not None:
                    if usb_age <= 5.0:
                        usb_score = 0.35  # Keyboard attached within 5s and typing immediately
                    elif usb_age <= 15.0:
                        usb_score = 0.20

            # 4. Dangerous Payload Pattern Score (0.0 to 0.25)
            pattern_score = 0.0
            recent_text = "".join(c for _, c in self._history)
            matched_pattern = None
            for pattern in self.SUSPICIOUS_PATTERNS:
                if pattern.search(recent_text):
                    pattern_score = 0.25
                    matched_pattern = pattern.pattern
                    break

            # Aggregate confidence
            confidence = min(1.0, speed_score + jitter_score + usb_score + pattern_score)
            is_anomaly = confidence >= self.confidence_threshold

            if is_anomaly:
                self.anomalies_detected += 1

            metrics = {
                "cps": round(cps, 1),
                "jitter_ms": round(jitter * 1000, 2),
                "mean_interval_ms": round(mean_interval * 1000, 2),
                "usb_age_sec": round(usb_age, 1) if usb_age is not None else None,
                "speed_score": round(speed_score, 2),
                "jitter_score": round(jitter_score, 2),
                "usb_score": round(usb_score, 2),
                "pattern_score": round(pattern_score, 2),
                "matched_pattern": matched_pattern,
                "confidence": round(confidence, 2),
            }

            return is_anomaly, confidence, metrics

    def reset(self):
        """Clear rolling buffer."""
        with self._lock:
            self._history.clear()
