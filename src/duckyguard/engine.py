"""
DuckyGuard - protection engine.

One CGEvent tap (via pynput) sees every key-down on the Mac. For each hardware
key-down the detector scores the current burst. When it says "machine", the
engine enters quarantine: that key and every following key-down/up is dropped
inside the tap callback (returned as None to macOS) until the stream has been
quiet for ``quarantine_seconds``. The dropped keys never reach any application.

What the engine honestly does and does not do:
* Keys typed *before* the decision reach the front application. With the
  hold-time rules that was 3 to 5 keys from a Flipper Zero on real hardware
  (1 when a block had just happened); see docs/EVALUATION.md and
  bench/hardware/results/2026-11-10-flipper-zero.json. The new-keyboard hold
  drops every key until the keyboard is allowed, blocked, unplugged, or the
  hold expires (hold_seconds, 20 s by default; away mode keeps it). A payload
  that waits out the hold faces the timing rules alone.
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
from .detector import HoldTracker, KeyEvent, KeystrokeAnomalyDetector, Verdict
from .devices import KeyboardWatcher, Keyboard, identity_flags
from .incidents import build_incident, finalize_incident
from .store import Store

STATUS_PROTECTED = "protected"
STATUS_OBSERVING = "observing"       # can see keys but not drop them (no Accessibility)
STATUS_PAUSED = "paused"
STATUS_ALERT = "alert"
STATUS_HOLD = "holding"             # an untrusted keyboard is plugged in and waiting for approval
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
                 enumerate_keyboards=None, lock_screen: Optional[Callable[[], object]] = None):
        self.store = store or Store()
        self.on_event = on_event
        self._lock = threading.RLock()

        kwargs = {}
        if enumerate_keyboards is not None:
            kwargs["enumerate"] = enumerate_keyboards
        self.keyboards = KeyboardWatcher(is_trusted=self.store.is_trusted, poll_interval=2.0,
                                         on_new_keyboard=self._on_new_keyboard, on_removed=self._on_keyboard_removed, **kwargs)
        self.detector = KeystrokeAnomalyDetector(
            usb_age_callback=self.keyboards.seconds_since_untrusted_keyboard,
            score_software=bool(self.store.get("score_software_input", False)),
        )

        self._lock_screen = lock_screen
        self._hold: Optional[dict] = None          # the keyboard currently waiting for approval
        self._status_before_hold = STATUS_PAUSED
        self._last_key_ts: Optional[float] = None
        self._last_key_wall: Optional[float] = None    # wall-clock time of the last hardware key, for the dashboard
        self._last_scan = time.time()
        self._listener = None
        self._tap = None
        self._running = False
        self._can_block = False
        self._error: Optional[str] = None
        self.status = STATUS_PAUSED
        self.paused_until: Optional[float] = None      # wall-clock time a timed pause ends

        # Quarantine state (touched only inside the tap callback and the watchdog)
        self._quarantine_until = 0.0
        self._incident: Optional[dict] = None
        self._blocked_chars: List[str] = []
        self._burst_chars: Deque[str] = collections.deque(maxlen=256)
        self._alert_until = 0.0

        # Hold-time bookkeeping: how long each key was held, handed to the detector once
        self.holds = HoldTracker()
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
            self.paused_until = None
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

    def pause(self, seconds: Optional[float] = None, now: Optional[float] = None) -> None:
        """Turns protection off. With ``seconds`` it comes back on its own and a relaunch starts protected;
        without, it stays off (across relaunches) until the user resumes."""
        self.stop(persist=seconds is None)
        self.paused_until = None if seconds is None else (time.time() if now is None else now) + float(seconds)
        self._emit("status")

    def resume_if_due(self, now: Optional[float] = None) -> bool:
        """Ends a timed pause once its time is up. Called from the app's one-second tick."""
        until = self.paused_until
        if until is None or (time.time() if now is None else now) < until:
            return False
        self.paused_until = None
        self.start()
        return True

    def permissions_changed(self, perms: dict) -> bool:
        """True when a permission was granted or revoked since the tap was made, so the tap must be rebuilt.
        A deliberate pause is left alone."""
        if self.status == STATUS_NO_PERMISSION:
            return bool(perms.get("can_observe"))
        if not self._running:
            return False
        return bool(perms.get("can_block")) != bool(self._can_block) or not perms.get("can_observe")

    def refresh_permissions(self) -> bool:
        """Rebuilds the tap if the permissions changed. Returns True when it did."""
        from . import permissions
        if not self.permissions_changed(permissions.status()):
            return False
        self.stop(persist=False)
        self.start()
        return True

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
            # Listen-only mode: no intercept callback, so time holds and score here.
            self.holds.key_down(key, time.time())
            self._score_pending(None, None)

    def _on_release(self, key, injected=False):
        if not self._can_block:
            self.holds.key_up(key, time.time())

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

            if not injected and event_type in (kCGEventKeyDown, kCGEventKeyUp):
                if event_type == kCGEventKeyDown:
                    self.before_hardware_key(ts, now)
                if self.should_drop_hardware(False, now):
                    if event_type == kCGEventKeyDown:
                        self.note_held_key()
                    return None

            if event_type == kCGEventKeyUp:
                self.holds.key_up(keycode, ts)
                if in_quarantine and (not injected or in_test):
                    return None
                return event

            if event_type != kCGEventKeyDown:
                return event

            repeat = CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat) != 0
            if not repeat:
                self.holds.key_down(keycode, ts)

            if in_quarantine and (not injected or in_test):
                self._absorb(_key_to_char(self._pending["key"]) if self._pending else "?", now)
                return None

            verdict = self._score_pending(ts, dict(injected=injected, repeat=repeat, pid=pid, in_test=in_test))
            if verdict is not None and verdict.block and self.dropping():
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
        modifier = name in _MODIFIER_NAMES
        repeat = bool(meta.get("repeat", False))
        ev = KeyEvent(
            timestamp=ts if ts is not None else time.time(),
            char=ch,
            injected=bool(injected) and not meta.get("in_test", False),
            repeat=repeat,
            modifier=modifier,
            hold_time=None if (modifier or repeat) else self.holds.take(),
            source_pid=int(meta.get("pid", 0)),
        )
        if not ev.modifier and not ev.repeat:
            if ev.injected:
                pass
            else:
                self._burst_chars.append(ch)
        verdict = self.detector.observe(ev)
        self.last_verdict = verdict
        if not ev.injected or meta.get("in_test"):
            self._last_key_wall = time.time()
        if verdict.kind == "buffering" and verdict.features.get("burst_len", 0) == 1:
            # new burst started: forget the old prefix text
            self._burst_chars.clear()
            self._burst_chars.append(ch)
        if verdict.block and not self.dropping():
            # Listen-only or monitor-only: we can warn but not drop.
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
        if can_drop and not simulated and self.store.get("lock_on_block", False):
            try:
                from . import permissions
                (self._lock_screen or permissions.lock_screen)()
                self._emit("screen_locked")
            except Exception as e:
                self._error = f"could not lock the screen: {e}"
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
        flags = identity_flags(kb, self.keyboards.keyboards(), self.store.trusted_devices())
        suspicious = "duplicate" in flags or "serial changed" in flags
        trusted = (self.store.is_trusted(kb.key) or kb.built_in) and not suspicious
        if suspicious:
            self.keyboards.mark_untrusted(kb)
        held = not trusted and bool(self.store.get("hold_new_keyboards", True)) and self.dropping()
        self._emit("keyboard_attached", keyboard=kb.as_dict(), trusted=trusted, flags=flags, held=held)
        if held:
            self._start_hold(kb, flags)

    def _on_keyboard_removed(self, key: str) -> None:
        self._emit("keyboard_removed", key=key)
        if self._hold is not None and self._hold["key"] == key:
            self._end_hold("unplugged")

    # ---------------------------------------------------------------- hold
    # macOS does not say which keyboard a key came from, so a hold drops every hardware key
    # (the built-in keyboard included) until the new keyboard is allowed, blocked or unplugged.
    # Approval comes from the mouse, Touch ID or the notification, never from the keyboard.

    def dropping(self) -> bool:
        """True when DuckyGuard is allowed to drop keys (Accessibility granted and not monitor-only)."""
        return bool(self._can_block) and not self.store.get("monitor_only", False)

    def hold_active(self) -> bool:
        return self._hold is not None

    def _start_hold(self, kb: Keyboard, flags: List[str]) -> None:
        now, secs = time.time(), float(self.store.get("hold_seconds", 20.0))
        if self._hold is None:
            self._status_before_hold = self.status
        self._hold = {"key": kb.key, "keyboard": kb.as_dict(), "flags": list(flags), "since": now,
                      "until": now + secs, "blocked": False, "dropped": 0}
        self.status = STATUS_HOLD
        self._emit("hold_started", keyboard=kb.as_dict(), flags=list(flags), expires_in=secs,
                   away=bool(self.store.get("away_mode", False)))

    def before_hardware_key(self, ts: float, now: float) -> None:
        """Called for every hardware key-down. On the first key after a pause, look for a keyboard that
        appeared since the last background scan, so its very first key is already held."""
        idle = self._last_key_ts is None or ts - self._last_key_ts > 0.35 or ts < self._last_key_ts
        self._last_key_ts = ts
        if idle and now - self._last_scan > 1.0:
            self._last_scan = now
            try:
                self.keyboards.refresh()
            except Exception:
                pass

    def should_drop_hardware(self, injected: bool, now: Optional[float] = None) -> bool:
        h = self._hold
        if h is None or injected:
            return False
        now = time.time() if now is None else now
        if not h["blocked"] and not self.store.get("away_mode", False) and now > h["until"]:
            self._end_hold("expired")
            return False
        return True

    def note_held_key(self) -> None:
        h = self._hold
        if h is not None:
            h["dropped"] += 1

    def allow_keyboard(self, key: str, trust: bool = True) -> bool:
        h = self._hold
        if h is None or h["key"] != key:
            return False
        if trust:
            self.store.trust_device(key, h["keyboard"])
            self.keyboards.forget_untrusted()
            self._emit("devices")
        self._end_hold("allowed")
        return True

    def block_keyboard(self, key: str) -> bool:
        h = self._hold
        if h is None or h["key"] != key:
            return False
        h["blocked"] = True
        self._emit("hold_blocked", keyboard=h["keyboard"])
        return True

    def _end_hold(self, result: str) -> None:
        h, self._hold = self._hold, None
        if h is None:
            return
        if self.status == STATUS_HOLD:
            self.status = (STATUS_PROTECTED if self._can_block else STATUS_OBSERVING) if self._running else self._status_before_hold
        if h["dropped"] > 0:
            name = h["keyboard"].get("product") or "A keyboard"
            how = {"allowed": "you allowed it", "expired": "the hold ran out", "unplugged": "it was unplugged"}.get(result, result)
            text = (f"{name} was held as soon as it was plugged in. {h['dropped']} keys were blocked before {how}. "
                    "None got through.")
            verdict = {"block": True, "score": 1.0, "kind": "hold", "explanation": text,
                       "reasons": ["an untrusted keyboard was plugged in and held for approval"] + h["flags"],
                       "features": {"rule": "Q: new keyboard held until you choose", "burst_len": 0, "flags": h["flags"]}}
            inc = build_incident(verdict, h["keyboard"], "", simulated=False, started_at=h["since"])
            inc.update({"keys_before_block": 0, "blocked_count": h["dropped"], "ended_at": time.time(),
                        "can_drop": True, "summary": text, "hold_result": result})
            try:
                self.store.save_incident(inc)
                self.last_incident = inc
            except Exception as e:
                self._error = f"could not save incident: {e}"
        self._emit("hold_ended", result=result, dropped=h["dropped"], keyboard=h["keyboard"])

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

    def trust_connected(self, keys) -> int:
        """Trusts the listed keyboards that are connected right now (first-run setup). Returns how many."""
        wanted, n = set(keys or []), 0
        for kb in self.keyboards.keyboards():
            if kb.key in wanted and not kb.built_in:
                self.store.trust_device(kb.key, kb.as_dict())
                n += 1
        if n:
            self.keyboards.forget_untrusted()
            self._emit("devices")
        return n

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
            "paused_until": self.paused_until,
            "keys_seen": self.detector.total_keys,
            "software_keys": self.detector.software_keys,
            "blocks": self.detector.blocks,
            "in_quarantine": time.time() < self._quarantine_until,
            "in_test": self.in_test(),
            "now": time.time(),
            "idle_s": (time.time() - self._last_key_wall) if self._last_key_wall else None,
            "hold": dict(self._hold) if self._hold else None,
            "secure_input": permissions.secure_input_active(),
            "shields": self.shields(),
            "last_verdict": self.last_verdict.as_dict() if self.last_verdict else None,
            "recent": list(self.detector.recent_events)[-64:],
            "keyboards": [self._kb_view(k) for k in self.keyboards.keyboards()],
            "trusted": self.store.trusted_devices(),
            "keyboard_poll_ms": round(self.keyboards.poll_ms, 1),
            "callback_us": {"median": cb_med, "p99": cb_p99, "samples": len(cb)},
            "incidents": self.store.list_incidents(limit=100),
        }

    def shields(self) -> List[dict]:
        """Every protection DuckyGuard has, whether it is on, and one honest line about it."""
        g, drop = self.store.get, self.dropping()
        return [
            {"id": "timing", "label": "Timing rules", "on": True, "note": "Speed and evenness of each burst."},
            {"id": "hold_time", "label": "Hold-time rules", "on": True, "note": "Keys released faster than a finger can."},
            {"id": "keyboard_hold", "label": "Hold new keyboards", "on": bool(g("hold_new_keyboards", True)) and drop,
             "note": "Blocks every key until you choose what to do with a new keyboard. Your own keyboard is off too."},
            {"id": "impostor", "label": "Lookalike check", "on": True, "note": "Duplicates, changed serials and lookalikes of keyboards you trust."},
            {"id": "away_mode", "label": "Away mode", "on": bool(g("away_mode", False)), "note": "Holds never expire while you are gone."},
            {"id": "lock_on_block", "label": "Lock the screen on a block", "on": bool(g("lock_on_block", False)), "note": "Locks the screen when an attack is blocked."},
            {"id": "keep_alive", "label": "Restart if it stops", "on": bool(g("keep_alive", False)), "note": "Starts DuckyGuard again if it is killed."},
            {"id": "monitor_only", "label": "Record only", "on": bool(g("monitor_only", False)), "note": "Notes what it would block and blocks nothing."},
            {"id": "dropping", "label": "Can block keys", "on": drop, "note": "Needs the Accessibility permission."},
        ]

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
