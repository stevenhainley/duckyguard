"""
DuckyGuard - USB Device and HID Connection Watcher
Monitors the arrival of new Human Interface Devices (keyboards/composite USBs)
via macOS IOKit / ioreg and tracks temporal correlation with input bursts.
"""

import json
import platform
import re
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set


class USBDeviceWatcher:
    """
    Tracks connected USB and HID keyboard devices.
    Flags newly connected devices and calculates the delta in seconds
    between device insertion and keystroke arrival.
    """

    KNOWN_BADUSB_VIDS = {
        "0483": "Flipper Zero (STMicroelectronics)",
        "04d8": "Hak5 Rubber Ducky (Microchip)",
        "2e8a": "Raspberry Pi Pico (BadUSB)",
        "16c0": "Teensy / ATmega32u4 USB",
        "1b4f": "SparkFun Pro Micro",
    }

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval
        self.is_macos = platform.system() == "Darwin"
        self._known_devices: Set[str] = set()
        self._last_connected_time: Optional[float] = None
        self._last_connected_device_info: Optional[Dict] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Initialize baseline known devices
        self._known_devices = self._get_current_hid_devices()

    def start(self):
        """Start background USB polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="DuckyGuard-USBWatcher")
        self._thread.start()

    def stop(self):
        """Stop background USB polling."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def get_seconds_since_last_connection(self) -> Optional[float]:
        """Returns elapsed seconds since the most recent new USB HID device was attached."""
        with self._lock:
            if self._last_connected_time is None:
                return None
            return time.time() - self._last_connected_time

    def get_last_device_info(self) -> Optional[Dict]:
        """Returns metadata for the most recently attached device."""
        with self._lock:
            return dict(self._last_connected_device_info) if self._last_connected_device_info else None

    def _get_current_hid_devices(self) -> Set[str]:
        """Snapshot current HID device signatures from the OS."""
        if not self.is_macos:
            return set()

        devices = set()
        try:
            cmd = ["ioreg", "-r", "-c", "IOHIDDevice", "-l"]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0)
            if proc.returncode != 0:
                return devices

            # Parse lines for Product, VendorID, ProductID
            current_product = "Unknown"
            current_vid = None
            current_pid = None

            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith('"Product"'):
                    m = re.search(r'"Product"\s*=\s*"([^"]+)"', line)
                    if m:
                        current_product = m.group(1)
                elif line.startswith('"VendorID"'):
                    m = re.search(r'"VendorID"\s*=\s*(\d+)', line)
                    if m:
                        current_vid = m.group(1)
                elif line.startswith('"ProductID"'):
                    m = re.search(r'"ProductID"\s*=\s*(\d+)', line)
                    if m:
                        current_pid = m.group(1)

                if current_vid and current_pid:
                    sig = f"{current_vid}:{current_pid}:{current_product}"
                    devices.add(sig)
                    current_vid = None
                    current_pid = None
        except Exception:
            pass

        return devices

    def _poll_loop(self):
        """Continuous polling for new device attachments."""
        while self._running:
            try:
                current = self._get_current_hid_devices()
                new_devices = current - self._known_devices
                if new_devices:
                    now = time.time()
                    for dev_sig in new_devices:
                        parts = dev_sig.split(":", 2)
                        vid_dec = parts[0] if len(parts) > 0 else "0"
                        pid_dec = parts[1] if len(parts) > 1 else "0"
                        prod_name = parts[2] if len(parts) > 2 else "Unknown HID Device"

                        # Format hex VID for matching known BadUSB hardware
                        try:
                            vid_hex = f"{int(vid_dec):04x}"
                        except ValueError:
                            vid_hex = "0000"

                        hardware_match = self.KNOWN_BADUSB_VIDS.get(vid_hex, "Generic HID Device")

                        with self._lock:
                            self._last_connected_time = now
                            self._last_connected_device_info = {
                                "timestamp": now,
                                "name": prod_name,
                                "vendor_id": vid_hex,
                                "product_id": pid_dec,
                                "hardware_profile": hardware_match,
                                "is_apple_internal": int(vid_dec) == 1452,
                            }

                    self._known_devices = current
                elif len(current) < len(self._known_devices):
                    # Device removed
                    self._known_devices = current
            except Exception:
                pass

            time.sleep(self.poll_interval)
