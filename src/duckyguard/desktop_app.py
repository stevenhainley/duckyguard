"""
DuckyGuard - Native macOS Desktop Application
A standalone GUI dashboard for real-time HID injection monitoring,
hardware bus forensics, attack simulation, and incident triage.
Designed to sh. industries standards: dark matte obsidian & cyber amber.
"""

import glob
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from PIL import Image, ImageTk

from .engine import DuckyGuardEngine
from .simulator import BadUSBSimulator


class DuckyGuardDesktopApp:
    """
    Main Desktop Application GUI for DuckyGuard.
    """

    # sh. industries Cyber Amber palette
    BG_DARK = "#0E0E0D"
    PANEL_BG = "#1A1A17"
    PANEL_BORDER = "#2B2A26"
    ACCENT_AMBER = "#FF7A00"
    ACCENT_AMBER_HOT = "#FFA31A"
    ACCENT_GREEN = "#10B981"
    ACCENT_RED = "#EF4444"
    TEXT_PAPER = "#F7F6F1"
    TEXT_MUTED = "#85827A"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DuckyGuard — Physical HID Injection Defense")
        self.root.geometry("980x640+140+100")
        self.root.configure(bg=self.BG_DARK)
        self.root.minsize(860, 560)

        # Base directories
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.reports_dir = os.path.join(self.base_dir, "reports")
        self.captures_dir = os.path.join(self.base_dir, "captures")

        # Initialize engines
        self.engine = DuckyGuardEngine(base_dir=self.base_dir)
        self.simulator = BadUSBSimulator()

        # Engine starts in background
        threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()

        # Keep mascot photo reference
        self.mascot_photo: Optional[ImageTk.PhotoImage] = None

        # State tracking
        self.current_tab = "monitor"
        self._running = True

        # Build UI
        self._build_header()
        self._build_body()

        # Telemetry Polling Thread
        self.poll_thread = threading.Thread(target=self._telemetry_worker, daemon=True)
        self.poll_thread.start()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self):
        """Top Header Bar with Brand, Pixel Mascot, and Engine Arming Toggle."""
        header = tk.Frame(self.root, bg=self.PANEL_BG, height=72, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        header.pack(fill="x", side="top")

        left_box = tk.Frame(header, bg=self.PANEL_BG, padx=16, pady=10)
        left_box.pack(side="left")

        # Pixel Mascot
        sprite_path = os.path.join(self.assets_dir, "ducky_pixel_sprite.png")
        if os.path.exists(sprite_path):
            try:
                raw_img = Image.open(sprite_path).convert("RGBA")
                raw_img = raw_img.resize((48, 48), Image.NEAREST)
                self.mascot_photo = ImageTk.PhotoImage(raw_img)
                mascot_lbl = tk.Label(left_box, image=self.mascot_photo, bg=self.PANEL_BG)
                mascot_lbl.pack(side="left", padx=(0, 14))
            except Exception:
                pass

        title_box = tk.Frame(left_box, bg=self.PANEL_BG)
        title_box.pack(side="left")

        kicker = tk.Label(
            title_box,
            text="SH. INDUSTRIES // PHYSICAL ENDPOINT DEFENSE",
            fg=self.ACCENT_AMBER,
            bg=self.PANEL_BG,
            font=("Menlo", 9, "bold"),
        )
        kicker.pack(anchor="w")

        title = tk.Label(
            title_box,
            text="DUCKYGUARD",
            fg=self.TEXT_PAPER,
            bg=self.PANEL_BG,
            font=("Helvetica", 18, "bold"),
        )
        title.pack(anchor="w")

        # Right Header: Status + Toggle
        right_box = tk.Frame(header, bg=self.PANEL_BG, padx=20, pady=12)
        right_box.pack(side="right")

        self.status_pill = tk.Label(
            right_box,
            text="● ARMED & MONITORING",
            fg=self.ACCENT_GREEN,
            bg="#064e3b",
            font=("Menlo", 10, "bold"),
            padx=12,
            pady=6,
        )
        self.status_pill.pack(side="left", padx=(0, 12))

        self.toggle_btn = tk.Button(
            right_box,
            text="Disarm",
            command=self._toggle_engine,
            fg=self.TEXT_PAPER,
            bg=self.PANEL_BORDER,
            activebackground=self.PANEL_BG,
            font=("Helvetica", 11, "bold"),
            relief="flat",
            padx=14,
            pady=4,
            cursor="pointinghand",
        )
        self.toggle_btn.pack(side="left")

    def _build_body(self):
        """Build Main Content with Navigation Sidebar and Tab Views."""
        container = tk.Frame(self.root, bg=self.BG_DARK)
        container.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(container, bg=self.PANEL_BG, width=180, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        sidebar.pack(fill="y", side="left")
        sidebar.pack_propagate(False)

        nav_title = tk.Label(
            sidebar,
            text="CONSOLE",
            fg=self.TEXT_MUTED,
            bg=self.PANEL_BG,
            font=("Menlo", 9, "bold"),
            padx=16,
            pady=16,
        )
        nav_title.pack(anchor="w")

        self.nav_btns = {}
        tabs = [
            ("monitor", "🛡 Live Monitor"),
            ("vault", "📂 Incident Vault"),
            ("hardware", "🔌 USB Bus"),
            ("simulator", "⚡ Attack Lab"),
        ]

        for tab_id, tab_label in tabs:
            btn = tk.Button(
                sidebar,
                text=tab_label,
                command=lambda t=tab_id: self._switch_tab(t),
                fg=self.TEXT_PAPER,
                bg=self.PANEL_BG,
                activebackground=self.PANEL_BORDER,
                font=("Helvetica", 12),
                relief="flat",
                anchor="w",
                padx=16,
                pady=10,
                cursor="pointinghand",
            )
            btn.pack(fill="x")
            self.nav_btns[tab_id] = btn

        # Main Dynamic View
        self.view_container = tk.Frame(container, bg=self.BG_DARK, padx=24, pady=20)
        self.view_container.pack(fill="both", expand=True, side="right")

        # Initialize tab frames
        self.views = {
            "monitor": self._build_monitor_view(),
            "vault": self._build_vault_view(),
            "hardware": self._build_hardware_view(),
            "simulator": self._build_simulator_view(),
        }

        self._switch_tab("monitor")

    def _build_monitor_view(self) -> tk.Frame:
        """Dashboard view: live telemetry cards and real-time stats."""
        frame = tk.Frame(self.view_container, bg=self.BG_DARK)

        lbl = tk.Label(frame, text="Live Endpoint Telemetry", fg=self.TEXT_PAPER, bg=self.BG_DARK, font=("Helvetica", 16, "bold"))
        lbl.pack(anchor="w", pady=(0, 16))

        # 3 Metrics Cards Grid
        cards_frame = tk.Frame(frame, bg=self.BG_DARK)
        cards_frame.pack(fill="x", pady=(0, 20))

        # Card 1: Keys Analyzed
        c1 = tk.Frame(cards_frame, bg=self.PANEL_BG, padx=16, pady=16, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(c1, text="KEYSTROKES INSPECTED", fg=self.TEXT_MUTED, bg=self.PANEL_BG, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_keys_count = tk.Label(c1, text="0", fg=self.TEXT_PAPER, bg=self.PANEL_BG, font=("Helvetica", 28, "bold"))
        self.lbl_keys_count.pack(anchor="w", pady=(6, 0))

        # Card 2: Attacks Blocked
        c2 = tk.Frame(cards_frame, bg=self.PANEL_BG, padx=16, pady=16, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c2.pack(side="left", fill="both", expand=True, padx=5)
        tk.Label(c2, text="ATTACKS NEUTRALIZED", fg=self.TEXT_MUTED, bg=self.PANEL_BG, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_attacks_count = tk.Label(c2, text="0", fg=self.ACCENT_AMBER_HOT, bg=self.PANEL_BG, font=("Helvetica", 28, "bold"))
        self.lbl_attacks_count.pack(anchor="w", pady=(6, 0))

        # Card 3: Connected Keyboards
        c3 = tk.Frame(cards_frame, bg=self.PANEL_BG, padx=16, pady=16, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c3.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(c3, text="ACTIVE USB HID DEVICES", fg=self.TEXT_MUTED, bg=self.PANEL_BG, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_hid_count = tk.Label(c3, text="1", fg=self.ACCENT_GREEN, bg=self.PANEL_BG, font=("Helvetica", 28, "bold"))
        self.lbl_hid_count.pack(anchor="w", pady=(6, 0))

        # Live Dynamics Box
        dynamics_panel = tk.Frame(frame, bg=self.PANEL_BG, padx=20, pady=18, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        dynamics_panel.pack(fill="both", expand=True)

        tk.Label(dynamics_panel, text="ACTIVE DEFENSE STATUS & HEURISTICS", fg=self.ACCENT_AMBER, bg=self.PANEL_BG, font=("Menlo", 10, "bold")).pack(anchor="w", pady=(0, 10))

        self.telemetry_log = tk.Text(
            dynamics_panel,
            bg="#0A0A09",
            fg="#4ADE80",
            font=("Menlo", 11),
            relief="flat",
            padx=12,
            pady=12,
            height=10,
        )
        self.telemetry_log.pack(fill="both", expand=True)
        self.telemetry_log.insert(tk.END, "[*] DuckyGuard Real-Time Protection Daemon active.\n")
        self.telemetry_log.insert(tk.END, "[*] Monitoring IOKit USB bus for HID enumeration events...\n")
        self.telemetry_log.insert(tk.END, "[*] Keystroke dynamics engine running (Sliding window = 12 keys).\n")
        self.telemetry_log.insert(tk.END, "[*] Threshold: 20 chars/sec velocity, < 12ms jitter standard deviation.\n")
        self.telemetry_log.config(state="disabled")

        return frame

    def _build_vault_view(self) -> tk.Frame:
        """Incident Vault: view intercepted attacks, forensic reports, and YARA rules."""
        frame = tk.Frame(self.view_container, bg=self.BG_DARK)

        top_box = tk.Frame(frame, bg=self.BG_DARK)
        top_box.pack(fill="x", pady=(0, 12))

        tk.Label(top_box, text="Incident Response Vault", fg=self.TEXT_PAPER, bg=self.BG_DARK, font=("Helvetica", 16, "bold")).pack(side="left")

        open_folder_btn = tk.Button(
            top_box,
            text="📂 Open Reports Folder",
            command=lambda: subprocess.run(["open", self.reports_dir]),
            fg=self.TEXT_PAPER,
            bg=self.PANEL_BG,
            font=("Helvetica", 10),
            relief="flat",
            padx=10,
            pady=4,
            cursor="pointinghand",
        )
        open_folder_btn.pack(side="right")

        # Split pane: Reports List on left, Report Viewer on right
        panes = tk.Frame(frame, bg=self.BG_DARK)
        panes.pack(fill="both", expand=True)

        # Left Reports Listbox
        list_box = tk.Frame(panes, bg=self.PANEL_BG, width=260, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        list_box.pack(side="left", fill="y", padx=(0, 12))
        list_box.pack_propagate(False)

        tk.Label(list_box, text="INTERCEPTED INCIDENTS", fg=self.TEXT_MUTED, bg=self.PANEL_BG, font=("Menlo", 9, "bold"), padx=10, pady=10).pack(anchor="w")

        self.reports_listbox = tk.Listbox(
            list_box,
            bg=self.PANEL_BG,
            fg=self.TEXT_PAPER,
            selectbackground=self.ACCENT_AMBER,
            selectforeground=self.BG_DARK,
            font=("Menlo", 10),
            relief="flat",
            highlightthickness=0,
        )
        self.reports_listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.reports_listbox.bind("<<ListboxSelect>>", self._on_select_report)

        # Right Content Area
        preview_box = tk.Frame(panes, bg=self.PANEL_BG, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        preview_box.pack(side="right", fill="both", expand=True)

        self.report_preview_text = tk.Text(
            preview_box,
            bg="#0A0A09",
            fg=self.TEXT_PAPER,
            font=("Menlo", 11),
            relief="flat",
            padx=14,
            pady=14,
        )
        self.report_preview_text.pack(fill="both", expand=True)

        self._refresh_vault_list()
        return frame

    def _build_hardware_view(self) -> tk.Frame:
        """Hardware Bus view: table of connected USB and HID devices."""
        frame = tk.Frame(self.view_container, bg=self.BG_DARK)

        tk.Label(frame, text="Connected USB & HID Devices", fg=self.TEXT_PAPER, bg=self.BG_DARK, font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 12))

        table_box = tk.Frame(frame, bg=self.PANEL_BG, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        table_box.pack(fill="both", expand=True)

        self.hw_text = tk.Text(
            table_box,
            bg="#0A0A09",
            fg="#38BDF8",
            font=("Menlo", 11),
            relief="flat",
            padx=14,
            pady=14,
        )
        self.hw_text.pack(fill="both", expand=True)

        self._refresh_hardware_list()
        return frame

    def _build_simulator_view(self) -> tk.Frame:
        """Attack Simulation Lab: test defense mechanisms without physical hardware."""
        frame = tk.Frame(self.view_container, bg=self.BG_DARK)

        tk.Label(frame, text="Synthetic BadUSB Attack Lab", fg=self.TEXT_PAPER, bg=self.BG_DARK, font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(
            frame,
            text="Simulate micro-controller keystroke injection to verify DuckyGuard's focus-stealing Decoy Sink in real time.",
            fg=self.TEXT_MUTED,
            bg=self.BG_DARK,
            font=("Helvetica", 12),
        ).pack(anchor="w", pady=(0, 20))

        lab_box = tk.Frame(frame, bg=self.PANEL_BG, padx=20, pady=20, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        lab_box.pack(fill="both", expand=True)

        # Preset 1: Resume Dropper
        self._create_sim_row(
            lab_box,
            title="1. Flipper Zero BadUSB (Resume Dropper Payload)",
            subtitle="Types at ~80 chars/sec with 12ms uniform microcontroller jitter.",
            command_func=lambda: self._trigger_sim("resume_dropper", is_badusb=True),
            btn_text="Launch Attack Test",
            btn_color=self.ACCENT_AMBER,
        )

        # Preset 2: Reverse Shell
        self._create_sim_row(
            lab_box,
            title="2. Reverse Shell Injector (Linux / macOS Dropper)",
            subtitle="Injects bash network socket commands directly into the terminal stream.",
            command_func=lambda: self._trigger_sim("reverse_shell", is_badusb=True),
            btn_text="Launch Attack Test",
            btn_color=self.ACCENT_RED,
        )

        # Preset 3: Benign Human
        self._create_sim_row(
            lab_box,
            title="3. Benign Human Baseline (Zero False-Positive Verification)",
            subtitle="Simulates a human typing at natural speeds (150-240ms intervals with high jitter).",
            command_func=lambda: self._trigger_sim("benign_human", is_badusb=False),
            btn_text="Test Human Typing",
            btn_color=self.ACCENT_GREEN,
        )

        return frame

    def _create_sim_row(self, parent, title: str, subtitle: str, command_func, btn_text: str, btn_color: str):
        row = tk.Frame(parent, bg=self.PANEL_BG, pady=12)
        row.pack(fill="x", pady=6)

        info = tk.Frame(row, bg=self.PANEL_BG)
        info.pack(side="left")

        tk.Label(info, text=title, fg=self.TEXT_PAPER, bg=self.PANEL_BG, font=("Helvetica", 13, "bold")).pack(anchor="w")
        tk.Label(info, text=subtitle, fg=self.TEXT_MUTED, bg=self.PANEL_BG, font=("Helvetica", 11)).pack(anchor="w")

        btn = tk.Button(
            row,
            text=btn_text,
            command=command_func,
            fg="#0E0E0D",
            bg=btn_color,
            activebackground=btn_color,
            font=("Helvetica", 11, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="pointinghand",
        )
        btn.pack(side="right")

    def _trigger_sim(self, preset_name: str, is_badusb: bool):
        messagebox.showinfo(
            "Simulation Armed",
            f"Simulation '{preset_name}' will fire in 3 seconds.\n\n"
            "DuckyGuard's Decoy Sink will intercept and redirect the stream!"
        )
        threading.Thread(
            target=self.simulator.run_simulation,
            kwargs={"preset_name": preset_name, "is_badusb": is_badusb, "initial_countdown_sec": 3},
            daemon=True,
        ).start()

    def _switch_tab(self, tab_id: str):
        self.current_tab = tab_id
        for tid, frame in self.views.items():
            frame.pack_forget()

        for tid, btn in self.nav_btns.items():
            if tid == tab_id:
                btn.configure(bg=self.PANEL_BORDER, fg=self.ACCENT_AMBER)
            else:
                btn.configure(bg=self.PANEL_BG, fg=self.TEXT_PAPER)

        self.views[tab_id].pack(fill="both", expand=True)

        if tab_id == "vault":
            self._refresh_vault_list()
        elif tab_id == "hardware":
            self._refresh_hardware_list()

    def _toggle_engine(self):
        if self.engine._running:
            self.engine.stop()
            self.status_pill.config(text="● DISARMED", fg=self.ACCENT_RED, bg="#450a0a")
            self.toggle_btn.config(text="Arm Engine")
        else:
            threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()
            self.status_pill.config(text="● ARMED & MONITORING", fg=self.ACCENT_GREEN, bg="#064e3b")
            self.toggle_btn.config(text="Disarm")

    def _refresh_vault_list(self):
        self.reports_listbox.delete(0, tk.END)
        reports = sorted(glob.glob(os.path.join(self.reports_dir, "incident-*.md")), reverse=True)
        for r in reports:
            self.reports_listbox.insert(tk.END, os.path.basename(r))

        if reports:
            self.reports_listbox.select_set(0)
            self._display_report_file(reports[0])

    def _on_select_report(self, _event):
        sel = self.reports_listbox.curselection()
        if sel:
            fname = self.reports_listbox.get(sel[0])
            fpath = os.path.join(self.reports_dir, fname)
            self._display_report_file(fpath)

    def _display_report_file(self, fpath: str):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            self.report_preview_text.config(state="normal")
            self.report_preview_text.delete("1.0", tk.END)
            self.report_preview_text.insert(tk.END, content)
            self.report_preview_text.config(state="disabled")
        except Exception:
            pass

    def _refresh_hardware_list(self):
        devices = self.engine.usb_watcher._get_current_hid_devices()
        self.hw_text.config(state="normal")
        self.hw_text.delete("1.0", tk.END)
        self.hw_text.insert(tk.END, f"{'VENDOR ID':<12} {'PRODUCT ID':<12} {'DEVICE NAME':<35}\n")
        self.hw_text.insert(tk.END, "="*65 + "\n")

        for dev_sig in sorted(devices):
            parts = dev_sig.split(":", 2)
            vid = parts[0] if len(parts) > 0 else "N/A"
            pid = parts[1] if len(parts) > 1 else "N/A"
            name = parts[2] if len(parts) > 2 else "Unknown HID"
            self.hw_text.insert(tk.END, f"{vid:<12} {pid:<12} {name:<35}\n")

        self.hw_text.config(state="disabled")

    def _telemetry_worker(self):
        """Polls engine statistics and updates UI counters."""
        while self._running:
            keys = self.engine.detector.total_keys_inspected
            blocked = self.engine.detector.anomalies_detected
            try:
                self.lbl_keys_count.config(text=f"{keys:,}")
                self.lbl_attacks_count.config(text=str(blocked))
            except Exception:
                pass
            time.sleep(1.0)

    def _on_close(self):
        self._running = False
        self.engine.stop()
        self.root.destroy()


def launch_desktop():
    root = tk.Tk()
    app = DuckyGuardDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_desktop()
