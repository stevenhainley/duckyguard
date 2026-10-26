"""
DuckyGuard - macOS Menu Bar Status Application
Provides a native macOS menu bar interface with real-time telemetry,
quick arm/disarm controls, and instant access to incident response reports.
"""

import os
import subprocess
import threading
import time
import rumps

from .engine import DuckyGuardEngine
from .simulator import BadUSBSimulator


class DuckyGuardTrayApp(rumps.App):
    """Native macOS Menu Bar application for DuckyGuard."""

    def __init__(self, engine: DuckyGuardEngine):
        super(DuckyGuardTrayApp, self).__init__(name="DuckyGuard", title="🛡 DuckyGuard")
        self.engine = engine
        self.simulator = BadUSBSimulator()

        # Build Menu Items
        self.status_item = rumps.MenuItem(f"Status: Armed 🟢", callback=None)
        self.telemetry_keys = rumps.MenuItem(f"Keys Analyzed: 0", callback=None)
        self.telemetry_blocked = rumps.MenuItem(f"Attacks Blocked: 0", callback=None)

        self.menu = [
            self.status_item,
            self.telemetry_keys,
            self.telemetry_blocked,
            None,  # Separator
            rumps.MenuItem("⚡ Test Defense (Simulator)", callback=self.on_run_simulation),
            rumps.MenuItem("📂 Open Incident Reports", callback=self.on_open_reports),
            rumps.MenuItem("📜 Open Raw Captures", callback=self.on_open_captures),
            None,
            rumps.MenuItem("Toggle Protection (Arm/Disarm)", callback=self.on_toggle_protection),
        ]

        # Register callback for incident desktop notifications
        self.engine.on_incident_callback = self._on_incident_notification

        # Start periodic telemetry refresh
        self.timer = rumps.Timer(self._update_telemetry, 2)
        self.timer.start()

    def _update_telemetry(self, _sender):
        keys = self.engine.detector.total_keys_inspected
        blocked = self.engine.detector.anomalies_detected
        self.telemetry_keys.title = f"Keys Analyzed: {keys:,}"
        self.telemetry_blocked.title = f"Attacks Blocked: {blocked}"

    def _on_incident_notification(self, summary: dict):
        rumps.notification(
            title="🚨 BadUSB Injection Blocked!",
            subtitle=f"{summary['mitre_techniques']} MITRE TTPs Identified",
            message=f"Neutralized & logged to reports. Zero commands executed.",
            sound=True,
        )

    def on_toggle_protection(self, sender):
        if self.engine._running:
            self.engine.stop()
            self.status_item.title = "Status: Disarmed 🔴"
            self.title = "🛡 [OFF]"
            rumps.notification("DuckyGuard", "Protection Disarmed", "Real-time HID monitoring paused.")
        else:
            threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()
            self.status_item.title = "Status: Armed 🟢"
            self.title = "🛡 DuckyGuard"
            rumps.notification("DuckyGuard", "Protection Armed", "Monitoring USB and keystroke dynamics.")

    def on_run_simulation(self, _sender):
        rumps.notification(
            "DuckyGuard Simulator",
            "Firing synthetic BadUSB attack in 3 seconds",
            "Watch DuckyGuard intercept and quarantine the stream!",
        )
        threading.Thread(
            target=self.simulator.run_simulation,
            kwargs={"preset_name": "resume_dropper", "initial_countdown_sec": 3},
            daemon=True,
        ).start()

    def on_open_reports(self, _sender):
        subprocess.run(["open", self.engine.reports_dir])

    def on_open_captures(self, _sender):
        subprocess.run(["open", self.engine.captures_dir])


def launch_tray():
    engine = DuckyGuardEngine()
    # Start engine in background thread
    threading.Thread(target=engine.start, kwargs={"blocking": False}, daemon=True).start()
    app = DuckyGuardTrayApp(engine)
    app.run()
