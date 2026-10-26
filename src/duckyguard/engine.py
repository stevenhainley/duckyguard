"""
DuckyGuard - Core Orchestration Engine
Wires together the USB Watcher, Keystroke Dynamics Detector, Decoy Sink,
and Threat Analyzer into a unified real-time endpoint protection service.
"""

import os
import sys
import threading
import time
from typing import Callable, Optional
from pynput import keyboard

from .detector import KeystrokeAnomalyDetector
from .usb_watcher import USBDeviceWatcher
from .decoy_sink import DecoyQuarantineSink
from .analyzer import ForensicThreatAnalyzer


class DuckyGuardEngine:
    """
    Main protection controller that monitors keystrokes, triggers decoy sinks,
    and coordinates post-incident forensic analysis.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.captures_dir = os.path.join(self.base_dir, "captures")
        self.reports_dir = os.path.join(self.base_dir, "reports")

        # Initialize sub-components
        self.usb_watcher = USBDeviceWatcher(poll_interval=1.0)
        self.analyzer = ForensicThreatAnalyzer(reports_dir=self.reports_dir)

        self.sink = DecoyQuarantineSink(
            captures_dir=self.captures_dir,
            cooldown_sec=3.5,
            on_capture_complete=self._handle_capture_completed,
        )

        self.detector = KeystrokeAnomalyDetector(
            window_size=12,
            rate_threshold_cps=20.0,
            jitter_threshold_sec=0.014,
            confidence_threshold=0.70,
            usb_watcher_callback=self.usb_watcher.get_seconds_since_last_connection,
        )

        self.listener: Optional[keyboard.Listener] = None
        self._running = False
        self.last_incident_summary: Optional[dict] = None
        self.on_incident_callback: Optional[Callable[[dict], None]] = None

    def start(self, blocking: bool = True):
        """Starts real-time protection."""
        if self._running:
            return

        self._running = True
        self.usb_watcher.start()

        print("[*] DuckyGuard Real-Time Protection Armed.")
        print(f"    Captures Directory: {self.captures_dir}")
        print(f"    Reports Directory:  {self.reports_dir}")
        print("    Monitoring keystrokes & USB bus for HID anomalies...")

        self.listener = keyboard.Listener(on_press=self._on_key_press)
        self.listener.start()

        if blocking:
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        """Disarms protection and releases hooks."""
        self._running = False
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.usb_watcher.stop()
        print("\n[!] DuckyGuard Protection Disarmed.")

    def _on_key_press(self, key):
        """Global keypress handler."""
        if not self._running:
            return

        now = time.time()

        # Format key representation
        try:
            char = key.char if hasattr(key, "char") and key.char else ""
        except AttributeError:
            char = ""

        if not char:
            if key == keyboard.Key.space:
                char = " "
            elif key == keyboard.Key.enter:
                char = "\n"
            elif key == keyboard.Key.backspace:
                char = "[BKSP]"
            else:
                char = f"[{str(key).replace('Key.', '')}]"

        # If Decoy Sink is already active, sink input directly into the quarantine
        if self.sink.is_active():
            self.sink.touch(char)
            return

        # Evaluate against detection heuristics
        is_anomaly, confidence, metrics = self.detector.record_keystroke(char, timestamp=now)

        if is_anomaly:
            # Query last attached device info
            dev_info = self.usb_watcher.get_last_device_info()
            dev_name = dev_info["name"] if dev_info else "Unknown USB HID Device"

            metrics["device_name"] = dev_name
            metrics["confidence"] = confidence

            print(f"\n[🚨 ALARM] HID INJECTION INTERCEPTED! Velocity: {metrics['cps']} chars/s (Conf: {int(confidence*100)}%)", file=sys.stderr)
            print(f"          Attacker Device: {dev_name}", file=sys.stderr)

            # Trigger immediate focus-stealing decoy sink
            self.sink.trigger(trigger_meta=metrics)
            # Feed current character to decoy
            self.sink.touch(char)
            # Reset detector buffer
            self.detector.reset()

    def _handle_capture_completed(self, capture_file_path: str, telemetry: dict):
        """Called by decoy sink once the injection burst finishes."""
        print(f"\n[*] Attack stream concluded. Sunk to: {capture_file_path}")
        print("[*] Initiating automated forensic threat triage...")

        report_path, yara_path, summary = self.analyzer.analyze_capture(capture_file_path, telemetry)
        self.last_incident_summary = summary

        print(f"[✓] Incident Report Generated: {report_path}")
        print(f"[✓] YARA Detection Rule Synthesized: {yara_path}")
        print(f"    - IOCs Extracted: {summary['urls_detected']} URLs, {summary['ips_detected']} IPs")
        print(f"    - MITRE ATT&CK TTPs Mapped: {summary['mitre_techniques']}\n")

        if self.on_incident_callback:
            self.on_incident_callback(summary)
