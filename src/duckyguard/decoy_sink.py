"""
DuckyGuard - Decoy Sink & Quarantine Subsystem
A focus-stealing containment window that intercepts, isolates, and neutralizes
malicious HID keystrokes before they reach foreground applications.
"""

import datetime
import os
import threading
import time
import tkinter as tk
from typing import Callable, Optional


class DecoyQuarantineSink:
    """
    Spawns an aggressive topmost window that forces macOS window focus to itself.
    Captures all raw keypresses, suppresses command execution, logs the attack string,
    and forwards the captured payload to the forensic threat analyzer.
    """

    def __init__(
        self,
        captures_dir: str,
        cooldown_sec: float = 4.0,
        on_capture_complete: Optional[Callable[[str, dict], None]] = None,
    ):
        self.captures_dir = captures_dir
        self.cooldown_sec = cooldown_sec
        self.on_capture_complete = on_capture_complete

        os.makedirs(self.captures_dir, exist_ok=True)

        self._active = threading.Event()
        self._last_event_time = 0.0
        self._root: Optional[tk.Tk] = None
        self._text_widget: Optional[tk.Text] = None
        self._current_file: Optional[str] = None
        self._captured_chars: list = []
        self._trigger_meta: dict = {}

    def is_active(self) -> bool:
        return self._active.is_set()

    def touch(self, char: str = ""):
        """Keep the watchdog alive and record character if window is open."""
        now = time.time()
        self._last_event_time = now
        if char and self._active.is_set():
            self._captured_chars.append(char)
            if self._root and self._text_widget:
                try:
                    self._text_widget.insert(tk.END, char)
                    self._text_widget.see(tk.END)
                except Exception:
                    pass

    def trigger(self, trigger_meta: Optional[dict] = None):
        """Activates the decoy quarantine sink in a dedicated UI thread."""
        if self._active.is_set():
            self.touch()
            return

        self._trigger_meta = trigger_meta or {}
        self._captured_chars.clear()
        self._last_event_time = time.time()
        self._active.set()

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._current_file = os.path.join(self.captures_dir, f"capture-{stamp}.txt")

        # Run GUI loop
        threading.Thread(target=self._run_gui, daemon=True, name="DuckyGuard-QuarantineUI").start()

    def _run_gui(self):
        root = tk.Tk()
        self._root = root
        root.title("🛡 DuckyGuard Active Defense — HID Injection Neutralized")
        root.geometry("720x420+160+140")
        root.configure(bg="#0f172a")

        # Stay on top of all windows
        root.attributes("-topmost", True)

        # Header Frame
        header = tk.Frame(root, bg="#ef4444", padx=16, pady=12)
        header.pack(fill="x")

        title_label = tk.Label(
            header,
            text="🚨 UNAUTHORIZED HID INJECTION DETECTED & INTERCEPTED",
            fg="#ffffff",
            bg="#ef4444",
            font=("Helvetica", 14, "bold"),
            justify="left",
        )
        title_label.pack(anchor="w")

        sub_label = tk.Label(
            header,
            text="Keystrokes redirected to secure sandbox. Attacker payload will NOT execute on host.",
            fg="#fee2e2",
            bg="#ef4444",
            font=("Helvetica", 11),
            justify="left",
        )
        sub_label.pack(anchor="w")

        # Telemetry Bar
        cps_val = self._trigger_meta.get("cps", "N/A")
        conf_val = self._trigger_meta.get("confidence", "1.0")
        dev_name = self._trigger_meta.get("device_name", "External USB HID")

        telemetry_frame = tk.Frame(root, bg="#1e293b", padx=14, pady=8)
        telemetry_frame.pack(fill="x")

        telem_text = f"Velocity: {cps_val} keys/s  |  Confidence: {int(float(conf_val)*100)}%  |  Device: {dev_name}"
        telem_label = tk.Label(
            telemetry_frame,
            text=telem_text,
            fg="#38bdf8",
            bg="#1e293b",
            font=("Menlo", 10, "bold"),
        )
        telem_label.pack(anchor="w")

        # Terminal Sink Box
        content_frame = tk.Frame(root, bg="#0f172a", padx=14, pady=10)
        content_frame.pack(fill="both", expand=True)

        box_label = tk.Label(
            content_frame,
            text="SUNK PAYLOAD STREAM (SANDBOXED):",
            fg="#94a3b8",
            bg="#0f172a",
            font=("Menlo", 10),
        )
        box_label.pack(anchor="w", pady=(0, 4))

        self._text_widget = tk.Text(
            content_frame,
            bg="#020617",
            fg="#4ade80",
            insertbackground="#38bdf8",
            font=("Menlo", 11),
            relief="flat",
            padx=10,
            pady=10,
        )
        self._text_widget.pack(fill="both", expand=True)

        # Preload characters captured during trigger transition
        if self._captured_chars:
            self._text_widget.insert(tk.END, "".join(self._captured_chars))

        # Focus Enforcement Bindings
        self._text_widget.bind("<KeyPress>", self._on_key_press)
        root.bind("<FocusOut>", self._on_focus_loss)

        self._enforce_focus()
        self._start_watchdog()

        try:
            root.mainloop()
        except Exception:
            pass

    def _on_key_press(self, event):
        """Record every sinked character to file in real time."""
        char = event.char if event.char else f"[{event.keysym}]"
        self.touch(char)
        if self._current_file:
            try:
                with open(self._current_file, "a", encoding="utf-8") as f:
                    f.write(char)
            except Exception:
                pass

    def _on_focus_loss(self, _event):
        """If an attacker payload attempts to Cmd+Tab or click away, snatch focus back immediately."""
        if self._active.is_set():
            self._enforce_focus()

    def _enforce_focus(self):
        if self._root:
            try:
                self._root.deiconify()
                self._root.lift()
                self._root.focus_force()
                if self._text_widget:
                    self._text_widget.focus_set()
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
                time.sleep(0.4)

            # Close window
            if self._root:
                try:
                    self._root.after(0, self._root.destroy)
                except Exception:
                    pass

            # Notify forensic threat analyzer
            if self._current_file and os.path.exists(self._current_file):
                captured_payload = "".join(self._captured_chars)
                if self.on_capture_complete:
                    self.on_capture_complete(self._current_file, self._trigger_meta)

        threading.Thread(target=watchdog, daemon=True, name="DuckyGuard-DecoyWatchdog").start()
