"""
DuckyGuard - Decoy Sink & Quarantine Subsystem
A focus-stealing containment sandbox that intercepts, isolates, and neutralizes
malicious HID keystrokes before they reach foreground applications.
"""

import datetime
import os
import subprocess
import threading
import time
from typing import Callable, Optional


class DecoyQuarantineSink:
    """
    Safely captures all raw injected keypresses into a secure forensic sandbox,
    suppresses execution, logs the attack string to disk, alerts the operator via
    native macOS notification, brings DuckyGuard to the front, and forwards the
    captured payload to the automated YARA & MITRE ATT&CK forensic analyzer.
    """

    def __init__(
        self,
        captures_dir: str,
        cooldown_sec: float = 3.5,
        on_capture_complete: Optional[Callable[[str, dict], None]] = None,
    ):
        self.captures_dir = captures_dir
        self.cooldown_sec = cooldown_sec
        self.on_capture_complete = on_capture_complete

        os.makedirs(self.captures_dir, exist_ok=True)

        self._active = threading.Event()
        self._last_event_time = 0.0
        self._current_file: Optional[str] = None
        self._captured_chars: list = []
        self._trigger_meta: dict = {}

    def is_active(self) -> bool:
        return self._active.is_set()

    def touch(self, char: str = ""):
        """Keep the quarantine alive and record character to forensic buffer."""
        now = time.time()
        self._last_event_time = now
        if char and self._active.is_set():
            self._captured_chars.append(char)
            if self._current_file:
                try:
                    with open(self._current_file, "a", encoding="utf-8") as f:
                        f.write(char)
                except Exception:
                    pass

    def trigger(self, trigger_meta: Optional[dict] = None):
        """Activates the decoy quarantine sandbox."""
        if self._active.is_set():
            self.touch()
            return

        self._trigger_meta = trigger_meta or {}
        self._captured_chars.clear()
        self._last_event_time = time.time()
        self._active.set()

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._current_file = os.path.join(self.captures_dir, f"capture-{stamp}.txt")

        # Create the initial capture file
        try:
            with open(self._current_file, "w", encoding="utf-8") as f:
                f.write(f"# DuckyGuard Decoy Quarantine Intercept - {stamp}\n")
                f.write(f"# Device: {self._trigger_meta.get('device_name', 'External USB HID')}\n")
                f.write(f"# Confidence: {self._trigger_meta.get('confidence', 1.0)}\n\n")
        except Exception:
            pass

        # Native macOS notification & focus steal in background
        threading.Thread(target=self._notify_and_focus, daemon=True, name="DuckyGuard-Alert").start()

        # Start watchdog to finalize capture when attack stream halts
        self._start_watchdog()

    def _notify_and_focus(self):
        """Send native macOS notification and bring DuckyGuard to the front."""
        dev = self._trigger_meta.get("device_name", "External USB HID")
        cps = self._trigger_meta.get("cps", 25.0)

        # Trigger native macOS User Notification
        script = (
            f'display notification "Intercepted {cps} keys/sec payload from {dev}. Keystrokes sandboxed." '
            f'with title "🛡 DuckyGuard Active Defense" subtitle "BadUSB Injection Neutralized" sound name "Basso"'
        )
        try:
            subprocess.run(["osascript", "-e", script], timeout=2, capture_output=True)
        except Exception:
            pass

        # Snatch focus to DuckyGuard to sink rogue keystrokes away from terminal/shell
        try:
            subprocess.run(
                ["osascript", "-e", 'tell application "DuckyGuard" to activate'],
                timeout=1,
                capture_output=True,
            )
        except Exception:
            pass

    def _start_watchdog(self):
        def watchdog():
            while self._active.is_set():
                elapsed = time.time() - self._last_event_time
                if elapsed >= self.cooldown_sec:
                    # Attack burst has concluded
                    self._active.clear()
                    break
                time.sleep(0.3)

            # Notify forensic threat analyzer
            if self._current_file and os.path.exists(self._current_file):
                if self.on_capture_complete:
                    try:
                        self.on_capture_complete(self._current_file, self._trigger_meta)
                    except Exception as err:
                        print(f"[!] Error in on_capture_complete: {err}")

        threading.Thread(target=watchdog, daemon=True, name="DuckyGuard-Watchdog").start()
