"""
DuckyGuard - Native macOS Desktop Application
Theme: Modern Light Creme-Orange (Award-Winning Aesthetic)
Built to sh. industries standards: warm luxury paper, cyber orange accents,
crisp typography, and tactile security controls.
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
    Modern Light-Theme Desktop Dashboard for DuckyGuard.
    """

    # Light Creme Orange Design Palette (Linear / Apple Design Award vibe)
    BG_CREME = "#FAF5EE"          # Warm luxurious creme canvas
    PANEL_WHITE = "#FFFFFF"       # Raised card surfaces
    PANEL_BORDER = "#EFE5D8"      # Subtle warm divider line
    PANEL_HOVER = "#F5ECE1"       # Subtle hover state
    TEXT_INK = "#1C1917"          # Rich stone ink for ultra-crisp typography
    TEXT_MUTED = "#78716C"        # Warm stone secondary label
    TEXT_FAINT = "#A8A29E"        # Light neutral captions

    # Accent Colors
    ACCENT_ORANGE = "#FF6B00"     # Cyberpunk signature orange
    ACCENT_ORANGE_HOT = "#FF8533" # Hover / glowing orange
    ACCENT_ORANGE_TINT = "#FFF0E5"# Soft peach/creme badge background
    ACCENT_MINT = "#059669"       # Fresh emerald green for armed status
    ACCENT_MINT_TINT = "#ECFDF5"  # Soft mint background
    ACCENT_RED = "#DC2626"        # Alert red
    ACCENT_RED_TINT = "#FEF2F2"   # Soft red background

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DuckyGuard — Physical HID Injection Defense")
        self.root.geometry("1020x680+120+80")
        self.root.configure(bg=self.BG_CREME)
        self.root.minsize(900, 600)

        # Base directories
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.reports_dir = os.path.join(self.base_dir, "reports")
        self.captures_dir = os.path.join(self.base_dir, "captures")

        # Initialize core engines
        self.engine = DuckyGuardEngine(base_dir=self.base_dir)
        self.simulator = BadUSBSimulator()

        # Engine runs in background
        threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()

        # Keep mascot image reference
        self.mascot_photo: Optional[ImageTk.PhotoImage] = None

        # State tracking
        self.current_tab = "monitor"
        self._running = True

        # Build UI layout
        self._build_top_nav()
        self._build_main_container()

        # Telemetry worker thread
        self.poll_thread = threading.Thread(target=self._telemetry_worker, daemon=True)
        self.poll_thread.start()

        # Clean exit
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_top_nav(self):
        """Top Brand Header with Cute Pixel Mascot and System Controls."""
        header_wrap = tk.Frame(self.root, bg=self.PANEL_WHITE, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        header_wrap.pack(fill="x", side="top")

        header = tk.Frame(header_wrap, bg=self.PANEL_WHITE, padx=24, pady=14)
        header.pack(fill="x")

        # Left: Mascot + Brand
        left_box = tk.Frame(header, bg=self.PANEL_WHITE)
        left_box.pack(side="left")

        # Cute Cyber Mascot Icon in Squircle Pill
        sprite_path = os.path.join(self.assets_dir, "ducky_pixel_cute.png")
        if not os.path.exists(sprite_path):
            sprite_path = os.path.join(self.assets_dir, "ducky_pixel_sprite.png")

        if os.path.exists(sprite_path):
            try:
                raw_img = Image.open(sprite_path).convert("RGBA")
                raw_img = raw_img.resize((44, 44), Image.NEAREST)
                self.mascot_photo = ImageTk.PhotoImage(raw_img)
                mascot_badge = tk.Label(
                    left_box,
                    image=self.mascot_photo,
                    bg=self.ACCENT_ORANGE_TINT,
                    padx=6,
                    pady=6,
                    highlightthickness=1,
                    highlightbackground="#FED7AA",
                )
                mascot_badge.pack(side="left", padx=(0, 14))
            except Exception:
                pass

        title_box = tk.Frame(left_box, bg=self.PANEL_WHITE)
        title_box.pack(side="left")

        eyebrow = tk.Label(
            title_box,
            text="SH. INDUSTRIES // ENDPOINT SECURITY",
            fg=self.ACCENT_ORANGE,
            bg=self.PANEL_WHITE,
            font=("Menlo", 9, "bold"),
        )
        eyebrow.pack(anchor="w")

        title_row = tk.Frame(title_box, bg=self.PANEL_WHITE)
        title_row.pack(anchor="w")

        app_name = tk.Label(
            title_row,
            text="DuckyGuard",
            fg=self.TEXT_INK,
            bg=self.PANEL_WHITE,
            font=("Helvetica", 19, "bold"),
        )
        app_name.pack(side="left")

        version_chip = tk.Label(
            title_row,
            text="v1.0",
            fg=self.TEXT_MUTED,
            bg=self.PANEL_HOVER,
            font=("Helvetica", 9, "bold"),
            padx=6,
            pady=2,
        )
        version_chip.pack(side="left", padx=(8, 0))

        # Right: Arm/Disarm Controls & Status Pill
        right_box = tk.Frame(header, bg=self.PANEL_WHITE)
        right_box.pack(side="right")

        self.status_pill = tk.Label(
            right_box,
            text="● SHIELD ARMED",
            fg=self.ACCENT_MINT,
            bg=self.ACCENT_MINT_TINT,
            font=("Menlo", 10, "bold"),
            padx=14,
            pady=7,
            highlightthickness=1,
            highlightbackground="#A7F3D0",
        )
        self.status_pill.pack(side="left", padx=(0, 14))

        self.toggle_btn = tk.Button(
            right_box,
            text="Disarm",
            command=self._toggle_engine,
            fg=self.TEXT_INK,
            bg=self.BG_CREME,
            activebackground=self.PANEL_BORDER,
            font=("Helvetica", 11, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="pointinghand",
            highlightthickness=1,
            highlightbackground=self.PANEL_BORDER,
        )
        self.toggle_btn.pack(side="left")

    def _build_main_container(self):
        """Build Navigation Tabs and Card Content Area."""
        body = tk.Frame(self.root, bg=self.BG_CREME, padx=32, pady=24)
        body.pack(fill="both", expand=True)

        # Tab Navigation Pill Bar
        nav_bar = tk.Frame(body, bg=self.BG_CREME)
        nav_bar.pack(fill="x", pady=(0, 20))

        self.nav_btns = {}
        tab_defs = [
            ("monitor", "🛡  Live Monitor"),
            ("vault", "📂  Incident Vault"),
            ("hardware", "🔌  USB Bus Forensics"),
            ("simulator", "⚡  Attack Simulator Lab"),
        ]

        for tab_id, tab_label in tab_defs:
            btn = tk.Button(
                nav_bar,
                text=tab_label,
                command=lambda t=tab_id: self._switch_tab(t),
                fg=self.TEXT_MUTED,
                bg=self.PANEL_WHITE,
                activebackground=self.ACCENT_ORANGE_TINT,
                font=("Helvetica", 11, "bold"),
                relief="flat",
                padx=16,
                pady=8,
                cursor="pointinghand",
                highlightthickness=1,
                highlightbackground=self.PANEL_BORDER,
            )
            btn.pack(side="left", padx=(0, 10))
            self.nav_btns[tab_id] = btn

        # Tab Content Container
        self.view_container = tk.Frame(body, bg=self.BG_CREME)
        self.view_container.pack(fill="both", expand=True)

        self.views = {
            "monitor": self._build_monitor_view(),
            "vault": self._build_vault_view(),
            "hardware": self._build_hardware_view(),
            "simulator": self._build_simulator_view(),
        }

        self._switch_tab("monitor")

    def _build_monitor_view(self) -> tk.Frame:
        """Dashboard view with 3 clean metrics cards and live telemetry."""
        frame = tk.Frame(self.view_container, bg=self.BG_CREME)

        # 3 Top Metric Cards
        cards_row = tk.Frame(frame, bg=self.BG_CREME)
        cards_row.pack(fill="x", pady=(0, 20))

        # Card 1: Keystrokes
        c1 = tk.Frame(cards_row, bg=self.PANEL_WHITE, padx=20, pady=18, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 14))
        tk.Label(c1, text="KEYSTROKES INSPECTED", fg=self.TEXT_MUTED, bg=self.PANEL_WHITE, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_keys_count = tk.Label(c1, text="0", fg=self.TEXT_INK, bg=self.PANEL_WHITE, font=("Helvetica", 32, "bold"))
        self.lbl_keys_count.pack(anchor="w", pady=(8, 2))
        tk.Label(c1, text="Real-time event stream", fg=self.TEXT_FAINT, bg=self.PANEL_WHITE, font=("Helvetica", 10)).pack(anchor="w")

        # Card 2: Attacks Neutralized
        c2 = tk.Frame(cards_row, bg=self.PANEL_WHITE, padx=20, pady=18, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c2.pack(side="left", fill="both", expand=True, padx=(0, 14))
        tk.Label(c2, text="ATTACKS NEUTRALIZED", fg=self.ACCENT_ORANGE, bg=self.PANEL_WHITE, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_attacks_count = tk.Label(c2, text="0", fg=self.ACCENT_ORANGE, bg=self.PANEL_WHITE, font=("Helvetica", 32, "bold"))
        self.lbl_attacks_count.pack(anchor="w", pady=(8, 2))
        tk.Label(c2, text="Trapped in Decoy Sink", fg=self.TEXT_FAINT, bg=self.PANEL_WHITE, font=("Helvetica", 10)).pack(anchor="w")

        # Card 3: USB HID Hardware
        c3 = tk.Frame(cards_row, bg=self.PANEL_WHITE, padx=20, pady=18, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        c3.pack(side="left", fill="both", expand=True)
        tk.Label(c3, text="ACTIVE HID DEVICES", fg=self.ACCENT_MINT, bg=self.PANEL_WHITE, font=("Menlo", 9, "bold")).pack(anchor="w")
        self.lbl_hid_count = tk.Label(c3, text="1", fg=self.ACCENT_MINT, bg=self.PANEL_WHITE, font=("Helvetica", 32, "bold"))
        self.lbl_hid_count.pack(anchor="w", pady=(8, 2))
        tk.Label(c3, text="IOKit bus enumeration", fg=self.TEXT_FAINT, bg=self.PANEL_WHITE, font=("Helvetica", 10)).pack(anchor="w")

        # Telemetry & Status Container
        console_card = tk.Frame(frame, bg=self.PANEL_WHITE, padx=22, pady=20, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        console_card.pack(fill="both", expand=True)

        top_info = tk.Frame(console_card, bg=self.PANEL_WHITE)
        top_info.pack(fill="x", pady=(0, 12))

        tk.Label(top_info, text="REAL-TIME DEFENSE ENGINE HEURISTICS", fg=self.TEXT_INK, bg=self.PANEL_WHITE, font=("Helvetica", 13, "bold")).pack(side="left")
        tk.Label(top_info, text="Sampling at 1,000 Hz", fg=self.TEXT_MUTED, bg=self.PANEL_WHITE, font=("Menlo", 9)).pack(side="right")

        # Dark Slate Terminal inside clean white card
        self.telemetry_log = tk.Text(
            console_card,
            bg="#18181B",
            fg="#4ADE80",
            insertbackground="#38BDF8",
            font=("Menlo", 11),
            relief="flat",
            padx=14,
            pady=14,
            height=12,
        )
        self.telemetry_log.pack(fill="both", expand=True)
        self.telemetry_log.insert(tk.END, "[*] DuckyGuard Real-Time Protection Daemon active.\n")
        self.telemetry_log.insert(tk.END, "[*] Monitoring macOS IOKit USB bus for HID keyboard connections...\n")
        self.telemetry_log.insert(tk.END, "[*] Keystroke dynamics sliding buffer initialized (12-event window).\n")
        self.telemetry_log.insert(tk.END, "[*] Heuristics: Velocity > 20 cps  |  Jitter std-dev < 12ms  |  USB correlation <= 5s.\n")
        self.telemetry_log.insert(tk.END, "[*] Status: ZERO UNTRUSTED KEYSTROKES DETECTED.\n")
        self.telemetry_log.config(state="disabled")

        return frame

    def _build_vault_view(self) -> tk.Frame:
        """Incident Response Vault: review captured payloads, IOCs, and YARA rules."""
        frame = tk.Frame(self.view_container, bg=self.BG_CREME)

        # Header with Finder action
        head = tk.Frame(frame, bg=self.BG_CREME)
        head.pack(fill="x", pady=(0, 14))

        tk.Label(head, text="Forensic Incident Vault", fg=self.TEXT_INK, bg=self.BG_CREME, font=("Helvetica", 15, "bold")).pack(side="left")

        open_btn = tk.Button(
            head,
            text="📂 Open Reports in Finder",
            command=lambda: subprocess.run(["open", self.reports_dir]),
            fg=self.TEXT_INK,
            bg=self.PANEL_WHITE,
            font=("Helvetica", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            cursor="pointinghand",
            highlightthickness=1,
            highlightbackground=self.PANEL_BORDER,
        )
        open_btn.pack(side="right")

        # Split Card: Left List, Right Viewer
        vault_card = tk.Frame(frame, bg=self.PANEL_WHITE, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        vault_card.pack(fill="both", expand=True)

        left_list_frame = tk.Frame(vault_card, bg="#FBF8F4", width=280, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        left_list_frame.pack(side="left", fill="y")
        left_list_frame.pack_propagate(False)

        tk.Label(left_list_frame, text="CAPTURED ATTACKS", fg=self.TEXT_MUTED, bg="#FBF8F4", font=("Menlo", 9, "bold"), padx=14, pady=12).pack(anchor="w")

        self.reports_listbox = tk.Listbox(
            left_list_frame,
            bg="#FBF8F4",
            fg=self.TEXT_INK,
            selectbackground=self.ACCENT_ORANGE,
            selectforeground="#FFFFFF",
            font=("Menlo", 10),
            relief="flat",
            highlightthickness=0,
        )
        self.reports_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.reports_listbox.bind("<<ListboxSelect>>", self._on_select_report)

        # Right Preview Area
        preview_frame = tk.Frame(vault_card, bg=self.PANEL_WHITE)
        preview_frame.pack(side="right", fill="both", expand=True)

        self.report_preview_text = tk.Text(
            preview_frame,
            bg=self.PANEL_WHITE,
            fg=self.TEXT_INK,
            font=("Menlo", 11),
            relief="flat",
            padx=18,
            pady=18,
        )
        self.report_preview_text.pack(fill="both", expand=True)

        self._refresh_vault_list()
        return frame

    def _build_hardware_view(self) -> tk.Frame:
        """Hardware Bus view: live table of connected USB and HID devices."""
        frame = tk.Frame(self.view_container, bg=self.BG_CREME)

        tk.Label(frame, text="Active USB & HID Hardware Bus", fg=self.TEXT_INK, bg=self.BG_CREME, font=("Helvetica", 15, "bold")).pack(anchor="w", pady=(0, 14))

        card = tk.Frame(frame, bg=self.PANEL_WHITE, padx=20, pady=20, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        card.pack(fill="both", expand=True)

        self.hw_text = tk.Text(
            card,
            bg=self.PANEL_WHITE,
            fg=self.TEXT_INK,
            font=("Menlo", 11),
            relief="flat",
            padx=10,
            pady=10,
        )
        self.hw_text.pack(fill="both", expand=True)

        self._refresh_hardware_list()
        return frame

    def _build_simulator_view(self) -> tk.Frame:
        """Attack Simulation Lab."""
        frame = tk.Frame(self.view_container, bg=self.BG_CREME)

        tk.Label(frame, text="Synthetic Attack Simulation Lab", fg=self.TEXT_INK, bg=self.BG_CREME, font=("Helvetica", 15, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            frame,
            text="Inject synthetic BadUSB keystroke streams to verify DuckyGuard's focus-stealing Decoy Sink in real time.",
            fg=self.TEXT_MUTED,
            bg=self.BG_CREME,
            font=("Helvetica", 11),
        ).pack(anchor="w", pady=(0, 18))

        card = tk.Frame(frame, bg=self.PANEL_WHITE, padx=24, pady=20, highlightthickness=1, highlightbackground=self.PANEL_BORDER)
        card.pack(fill="both", expand=True)

        # Simulation Row 1
        self._create_sim_row(
            card,
            title="1. Flipper Zero BadUSB (Resume Dropper Script)",
            subtitle="Fires ~80 chars/second with 12ms uniform microcontroller timing intervals.",
            command_func=lambda: self._trigger_sim("resume_dropper", is_badusb=True),
            btn_text="Launch Attack Test",
            btn_bg=self.ACCENT_ORANGE,
            btn_fg="#FFFFFF",
        )

        # Simulation Row 2
        self._create_sim_row(
            card,
            title="2. Reverse Shell Dropper (macOS / Linux)",
            subtitle="Simulates automated bash command socket payloads targeting port 4444.",
            command_func=lambda: self._trigger_sim("reverse_shell", is_badusb=True),
            btn_text="Launch Attack Test",
            btn_bg="#EA580C",
            btn_fg="#FFFFFF",
        )

        # Simulation Row 3
        self._create_sim_row(
            card,
            title="3. Benign Human Baseline (Zero False-Positive Check)",
            subtitle="Simulates natural human typing speeds (120-220ms per key) with high timing jitter.",
            command_func=lambda: self._trigger_sim("benign_human", is_badusb=False),
            btn_text="Verify Human Typing",
            btn_bg=self.ACCENT_MINT_TINT,
            btn_fg=self.ACCENT_MINT,
        )

        return frame

    def _create_sim_row(self, parent, title: str, subtitle: str, command_func, btn_text: str, btn_bg: str, btn_fg: str):
        row = tk.Frame(parent, bg=self.PANEL_WHITE, pady=14)
        row.pack(fill="x", pady=6)

        info = tk.Frame(row, bg=self.PANEL_WHITE)
        info.pack(side="left")

        tk.Label(info, text=title, fg=self.TEXT_INK, bg=self.PANEL_WHITE, font=("Helvetica", 13, "bold")).pack(anchor="w")
        tk.Label(info, text=subtitle, fg=self.TEXT_MUTED, bg=self.PANEL_WHITE, font=("Helvetica", 11)).pack(anchor="w")

        btn = tk.Button(
            row,
            text=btn_text,
            command=command_func,
            fg=btn_fg,
            bg=btn_bg,
            activebackground=self.ACCENT_ORANGE_HOT,
            font=("Helvetica", 11, "bold"),
            relief="flat",
            padx=18,
            pady=8,
            cursor="pointinghand",
        )
        btn.pack(side="right")

    def _trigger_sim(self, preset_name: str, is_badusb: bool):
        messagebox.showinfo(
            "Attack Simulation Armed",
            f"Simulation '{preset_name}' will fire in 3 seconds.\n\n"
            "DuckyGuard's focus-stealing Decoy Sink will intercept and quarantine the stream!"
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
                btn.configure(bg=self.ACCENT_ORANGE_TINT, fg=self.ACCENT_ORANGE, highlightbackground="#FED7AA")
            else:
                btn.configure(bg=self.PANEL_WHITE, fg=self.TEXT_MUTED, highlightbackground=self.PANEL_BORDER)

        self.views[tab_id].pack(fill="both", expand=True)

        if tab_id == "vault":
            self._refresh_vault_list()
        elif tab_id == "hardware":
            self._refresh_hardware_list()

    def _toggle_engine(self):
        if self.engine._running:
            self.engine.stop()
            self.status_pill.config(
                text="● SHIELD DISARMED",
                fg=self.ACCENT_RED,
                bg=self.ACCENT_RED_TINT,
                highlightbackground="#FECACA",
            )
            self.toggle_btn.config(text="Arm Shield")
        else:
            threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()
            self.status_pill.config(
                text="● SHIELD ARMED",
                fg=self.ACCENT_MINT,
                bg=self.ACCENT_MINT_TINT,
                highlightbackground="#A7F3D0",
            )
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
        self.hw_text.insert(tk.END, f"{'VENDOR ID':<14} {'PRODUCT ID':<14} {'DEVICE NAME':<35}\n")
        self.hw_text.insert(tk.END, "─"*65 + "\n")

        for dev_sig in sorted(devices):
            parts = dev_sig.split(":", 2)
            vid = parts[0] if len(parts) > 0 else "N/A"
            pid = parts[1] if len(parts) > 1 else "N/A"
            name = parts[2] if len(parts) > 2 else "Unknown HID"
            self.hw_text.insert(tk.END, f"{vid:<14} {pid:<14} {name:<35}\n")

        self.hw_text.config(state="disabled")

    def _telemetry_worker(self):
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
