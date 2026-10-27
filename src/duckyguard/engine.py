"""
DuckyGuard - protection engine.

One CGEvent tap (via pynput) sees every key-down on the Mac. For each hardware
key-down the detector scores the current burst. When it says "machine", the
engine enters quarantine: that key and every following key-down/up is dropped
inside the tap callback (returned as None to macOS) until the stream has been
quiet for ``quarantine_seconds``. The dropped keys never reach any application.

What the engine honestly does and does not do:
* Keys typed *before* the decision reach the front application. With the
  default rules that is 8 keys at injector speeds (see docs/EVALUATION.md).
* Blocking needs the Accessibility permission (active tap). With only Input
  Monitoring the engine observes and warns but cannot drop keys; the status
  says "observing only".
* Keys synthesized by local programs (password managers, text expanders, our
  own test) are let through unless test mode is on.
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Callable, Deque, Dict, List, Optional

from . import __version__
from .detector import KeyEvent, KeystrokeAnomalyDetector, Verdict
from .devices import KeyboardWatcher, Keyboard
from .incidents import build_incident, finalize_incident
from .store import Store

STATUS_PROTECTED = "protected"
STATUS_OBSERVING = "observing"       # can see keys but not drop them (no Accessibility)
STATUS_PAUSED = "paused"
STATUS_ALERT = "alert"
STATUS_NO_PERMISSION = "no_permission"
STATUS_ERROR = "error"

_MODIFIER_NAMES = {"shift", "shift_r", "shift_l", "ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r",
                   "alt_gr", "cmd", "cmd_l", "cmd_r", "caps_lock", "fn"}


def _key_to_char(key) -> str:
    try:
        ch = getattr(key, "char", None)
        if ch:
            return ch
    except Exception:
        pass
    name = str(key).replace("Key.", "")
    if name == "space":
        return " "
    if name == "enter":
        return "\n"
    if name == "tab":
        return "\t"
    if name == "backspace":
        return "[BKSP]"
    return f"[{name}]"


class Engine:
    """Owns the tap, the detector, the keyboard watcher and the quarantine state."""

    def __init__(self, store: Optional[Store] = None, on_event: Optional[Callable[[dict], None]] = None,
                 enumerate_keyboards=None):
        self.store = store or Store()
        self.on_event = on_event
        self._lock = threading.RLock()

        kwargs = {}
        if enumerate_keyboards is not None:
            kwargs["enumerate"] = enumerate_keyboards
        self.keyboards = KeyboardWatcher(is_trusted=self.store.is_trusted,
                                         on_new_keyboard=self._on_new_keyboard, **kwargs)
        self.detector = KeystrokeAnomalyDetector(
            usb_age_callback=self.keyboards.seconds_since_untrusted_keyboard,
            score_software=bool(self.store.get("score_software_input", False)),
        )

        self._listener = None
        self._tap = None
        self._running = False
        self._can_block = False
        self._error: Optional[str] = None
        self.status = STATUS_PAUSED

        # Quarantine state (touched only inside the tap callback and the watchdog)
        self._quarantine_until = 0.0
        self._incident: Optional[dict] = None
        self._blocked_chars: List[str] = []
        self._burst_chars: Deque[str] = collections.deque(maxlen=256)
        self._alert_until = 0.0

        # Hold-time bookkeeping: keycode -> down timestamp
        self._down_at: Dict[int, float] = {}
        self._last_hold: Optional[float] = None
        self._pending: Optional[dict] = None     # filled by on_press, consumed by intercept

        # Test mode ("Test it safely")
        self._test_until = 0.0

        # Stats
        self.started_at: Optional[float] = None
        self.last_verdict: Optional[Verdict] = None
        self.last_incident: Optional[dict] = None
        self.callback_ns: Deque[int] = collections.deque(maxlen=2000)   # measured tap-callback cost

    # ------------------------------------------------------------- lifecycle

    def start(self) -> str:
        """Starts protection. Returns the resulting status."""
        from . import permissions
        with self._lock:
            if self._running:
                return self.status
            perms = permissions.status()
            if not perms["can_observe"]:
                self.status = STATUS_NO_PERMISSION
                self._emit("status")
                return self.status
            self._can_block = perms["can_block"]
            try:
                self._listener = self._make_listener(active=self._can_block)
                self._listener.start()
                self._listener.wait()
            except Exception as e:      # pragma: no cover - depends on OS state
                self._error = f"could not start the keyboard tap: {e}"
                self.status = STATUS_ERROR
                self._emit("status")
                return self.status
            self.keyboards.start()
            self._running = True
            self.started_at = time.time()
            self.status = STATUS_PROTECTED if self._can_block else STATUS_OBSERVING
            self.store.set("protection_enabled", True)
            self._emit("status")
            return self.status

    def stop(self, persist: bool = True) -> None:
        with self._lock:
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None
            self.keyboards.stop()
            self._running = False
            self._quarantine_until = 0.0
            self.status = STATUS_PAUSED
            if persist:
                self.store.set("protection_enabled", False)
            self._emit("status")

    def is_running(self) -> bool:
        return self._running

    def _make_listener(self, active: bool):
        from pynput import keyboard
        from Quartz import CGEventTapEnable

        engine = self

        class _Listener(keyboard.Listener):
            def _create_event_tap(self_inner):
                tap = super()._create_event_tap()
                engine._tap = tap
                return tap

        kwargs = dict(on_press=self._on_press, on_release=self._on_release)
        if active:
            kwargs["darwin_intercept"] = self._intercept
        listener = _Listener(**kwargs)
        self._CGEventTapEnable = CGEventTapEnable
        return listener

    # ------------------------------------------------------------ hot path

    def _on_press(self, key, injected=False):
        # Called by pynput just before _intercept for the same CGEvent.
        self._pending = {"key": key, "injected": bool(injected)}
        if not self._can_block:
            # Listen-only mode: no intercept callback, so score here.
            self._score_pending(None, None)

    def _on_release(self, key, injected=False):
        pass

    def _intercept(self, event_type, event):
        """Active-tap callback. Returning None drops the event."""
        t0 = time.perf_counter_ns()
        try:
            from Quartz import (CGEventGetIntegerValueField, CGEventGetTimestamp, kCGEventKeyDown, kCGEventKeyUp,
                                kCGKeyboardEventAutorepeat, kCGKeyboardEventKeycode, kCGEventSourceUnixProcessID,
                                kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput)
            if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
                if self._tap is not None:
                    self._CGEventTapEnable(self._tap, True)
                self._emit("tap_reenabled")
                return event

            now = time.time()
            ts = CGEventGetTimestamp(event) / 1e9   # kernel event time (seconds since boot)
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            pid = CGEventGetIntegerValueField(event, kCGEventSourceUnixProcessID)
            injected = pid != 0
            in_test = now < self._test_until
            in_quarantine = now < self._quarantine_until

            if event_type == kCGEventKeyUp:
                down = self._down_at.pop(keycode, None)
                if down is not None:
                    self._last_hold = max(0.0, ts - down)
                if in_quarantine and (not injected or in_test):
                    return None
                return event

            if event_type != kCGEventKeyDown:
                return event

            repeat = CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat) != 0
            if not repeat:
                self._down_at[keycode] = ts
                if len(self._down_at) > 64:
                    self._down_at.clear()

            if in_quarantine and (not injected or in_test):
                self._absorb(_key_to_char(self._pending["key"]) if self._pending else "?", now)
                return None

            verdict = self._score_pending(ts, dict(injected=injected, repeat=repeat, pid=pid, in_test=in_test))
            if verdict is not None and verdict.block:
                self._begin_quarantine(verdict, now, simulated=in_test)
                return None
            return event
        except Exception as e:  # never let an exception stall the tap
            self._error = f"tap callback error: {e}"
            return event
        finally:
            self.callback_ns.append(time.perf_counter_ns() - t0)

    def _score_pending(self, ts: Optional[float], meta: Optional[dict]) -> Optional[Verdict]:
        pending = self._pending
        self._pending = None
        if pending is None:
            return None
        key = pending["key"]
        meta = meta or {}
        injected = meta.get("injected", pending.get("injected", False))
        name = str(key).replace("Key.", "")
        ch = _key_to_char(key)
        ev = KeyEvent(
            timestamp=ts if ts is not None else time.time(),
            char=ch,
            injected=bool(injected) and not meta.get("in_test", False),
            repeat=bool(meta.get("repeat", False)),
            modifier=name in _MODIFIER_NAMES,
            hold_time=self._last_hold,
            source_pid=int(meta.get("pid", 0)),
        )
        if not ev.modifier and not ev.repeat:
            if ev.injected:
                pass
            else:
                self._burst_chars.append(ch)
        verdict = self.detector.observe(ev)
        self.last_verdict = verdict
        if verdict.kind == "buffering" and verdict.features.get("burst_len", 0) == 1:
            # new burst started: forget the old prefix text
            self._burst_chars.clear()
            self._burst_chars.append(ch)
        if verdict.block and not self._can_block:
            # Listen-only mode: we can warn but not drop.
            self._begin_quarantine(verdict, time.time(), simulated=False, can_drop=False)
        return verdict

    # ----------------------------------------------------------- quarantine

    def _begin_quarantine(self, verdict: Verdict, now: float, simulated: bool, can_drop: bool = True) -> None:
        secs = float(self.store.get("quarantine_seconds", 2.0))
        self._quarantine_until = now + secs if can_drop else 0.0
        kb = self.keyboards.last_untrusted()
        age = self.keyboards.seconds_since_untrusted_keyboard()
        keyboard = kb.as_dict() if (kb and age is not None and age < 60) else None
        prefix = "".join(self._burst_chars)
        self._blocked_chars = []
        self._incident = build_incident(verdict.as_dict(), keyboard, prefix, simulated=simulated, started_at=now)
        self._incident["can_drop"] = can_drop
        # the triggering key itself is dropped
        if can_drop and self._burst_chars:
            self._blocked_chars.append(self._burst_chars.pop())
            self._incident["prefix_text"] = "".join(self._burst_chars)
            self._incident["keys_before_block"] = max(0, self._incident["keys_before_block"] - 1)
        self.status = STATUS_ALERT
        self._alert_until = now + 10.0
        self.detector.reset()
        self._emit("block_started")
        threading.Thread(target=self._watchdog, args=(secs,), daemon=True, name="DuckyGuard-Quarantine").start()

    def _absorb(self, ch: str, now: float) -> None:
        self._blocked_chars.append(ch)
        secs = float(self.store.get("quarantine_seconds", 2.0))
        self._quarantine_until = now + secs

    def _watchdog(self, secs: float) -> None:
        while time.time() < self._quarantine_until:
            time.sleep(0.1)
        inc = self._incident
        self._incident = None
        if inc is None:
            return
        blocked = "".join(self._blocked_chars)
        finalize_incident(inc, blocked, len(self._blocked_chars))
        try:
            self.store.save_incident(inc)
        except Exception as e:
            self._error = f"could not save incident: {e}"
        self.last_incident = inc
        self._emit("block_finished", incident=inc)
        # Hold the alert state briefly so the menu bar is noticeable, then settle.
        while time.time() < self._alert_until:
            time.sleep(0.2)
        if self._running and self.status == STATUS_ALERT:
            self.status = STATUS_PROTECTED if self._can_block else STATUS_OBSERVING
            self._emit("status")

    # ------------------------------------------------------------- devices

    def _on_new_keyboard(self, kb: Keyboard) -> None:
        self._emit("keyboard_attached", keyboard=kb.as_dict(), trusted=self.store.is_trusted(kb.key))

    def trust_keyboard(self, key: str) -> bool:
        for kb in self.keyboards.keyboards():
            if kb.key == key:
                self.store.trust_device(key, kb.as_dict())
                self.keyboards.forget_untrusted()
                self._emit("devices")
                return True
        # allow trusting from an incident even if the keyboard is gone
        trusted = self.store.trusted_devices()
        if key not in trusted:
            self.store.trust_device(key, {"key": key, "product": key})
            self._emit("devices")
            return True
        return False

    def untrust_keyboard(self, key: str) -> None:
        self.store.untrust_device(key)
        self._emit("devices")

    # ---------------------------------------------------------------- test

    def begin_test(self, seconds: float = 8.0) -> None:
        """Treat software-synthesized keys as hardware for a short while."""
        self._test_until = time.time() + seconds
        self.detector.test_mode = True
        threading.Thread(target=self._end_test, args=(seconds,), daemon=True).start()

    def _end_test(self, seconds: float) -> None:
        time.sleep(seconds)
        if time.time() >= self._test_until:
            self.detector.test_mode = False

    def in_test(self) -> bool:
        return time.time() < self._test_until

    # ------------------------------------------------------------- reporting

    def snapshot(self) -> dict:
        from . import permissions
        cb = sorted(self.callback_ns)
        cb_med = cb[len(cb) // 2] / 1000.0 if cb else None
        cb_p99 = cb[int(len(cb) * 0.99)] / 1000.0 if cb else None
        return {
            "version": __version__,
            "status": self.status,
            "running": self._running,
            "can_block": self._can_block,
            "error": self._error,
            "permissions": permissions.status(),
            "settings": self.store.settings(),
            "started_at": self.started_at,
            "keys_seen": self.detector.total_keys,
            "software_keys": self.detector.software_keys,
            "blocks": self.detector.blocks,
            "in_quarantine": time.time() < self._quarantine_until,
            "in_test": self.in_test(),
            "last_verdict": self.last_verdict.as_dict() if self.last_verdict else None,
            "recent": list(self.detector.recent_events)[-60:],
            "keyboards": [self._kb_view(k) for k in self.keyboards.keyboards()],
            "trusted": self.store.trusted_devices(),
            "keyboard_poll_ms": round(self.keyboards.poll_ms, 1),
            "callback_us": {"median": cb_med, "p99": cb_p99, "samples": len(cb)},
            "incidents": self.store.list_incidents(limit=100),
        }

    def _kb_view(self, kb: Keyboard) -> dict:
        d = kb.as_dict()
        d["trusted"] = self.store.is_trusted(kb.key) or kb.built_in
        return d

    def _emit(self, kind: str, **payload) -> None:
        if self.on_event is None:
            return
        evt = {"event": kind, "status": self.status, "t": time.time()}
        evt.update(payload)
        try:
            self.on_event(evt)
        except Exception:
            pass
