"""
DuckyGuard - safe injection simulator.

Types a harmless payload through macOS's own event API (pynput Controller) at
the timing of a scripted keyboard. The keys are *software* events (they carry
this process's PID), so the engine only scores them while test mode is on;
``Engine.begin_test()`` turns that on for a few seconds. Nothing in the
payloads executes anything: they are plain sentences with no command, no
address and no Return, and the simulator refuses to press Return at all. The
app also stops the test the moment its own window loses focus (``keep_going``).
"""

from __future__ import annotations

import random
import time
from typing import Optional

PRESETS = {
    "harmless": "This is a harmless DuckyGuard test sentence, typed faster than any hand could type it.",
    "plain": "this is a plain sentence typed at machine speed with no command in it",
    "human": "The quick brown fox jumps over the lazy dog at a human pace.",
}


class BadUSBSimulator:
    """Replays a preset through pynput at injector or human timing."""

    def __init__(self):
        # Quartz directly (no pynput Controller: it touches Text Input Services,
        # which must not be called from a background thread).
        from Quartz import (CGEventCreateKeyboardEvent, CGEventKeyboardSetUnicodeString, CGEventPost,
                            kCGHIDEventTap)
        self._create = CGEventCreateKeyboardEvent
        self._set_str = CGEventKeyboardSetUnicodeString
        self._post = CGEventPost
        self._tap = kCGHIDEventTap

    def type_char(self, ch: str) -> None:
        if ch in "\r\n":
            return                      # the simulator never presses Return, whatever it is given
        for down in (True, False):
            ev = self._create(None, 0, down)
            self._set_str(ev, len(ch), ch)
            self._post(self._tap, ev)

    def run(self, preset: str = "harmless", interval_ms: float = 12.0, human: bool = False,
            countdown: float = 0.0, text: Optional[str] = None, on_done=None, keep_going=None) -> bool:
        """Types the payload. ``keep_going`` is asked before every key; the run stops (returning False)
        the first time it says no."""
        payload = text or PRESETS.get(preset, PRESETS["harmless"])
        if countdown > 0:
            time.sleep(countdown)
        for ch in payload:
            if keep_going is not None and not keep_going():
                return False
            self.type_char(ch)
            if human:
                time.sleep(random.uniform(0.10, 0.22))
            else:
                time.sleep(interval_ms / 1000.0)
        if on_done:
            on_done()
        return True

    # Backwards compatibility with the v1 CLI.
    def run_simulation(self, preset_name="harmless", custom_text=None, is_badusb=True, initial_countdown_sec=3):
        self.run(preset=preset_name, human=not is_badusb, countdown=initial_countdown_sec, text=custom_text)
