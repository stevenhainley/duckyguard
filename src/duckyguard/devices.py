"""
DuckyGuard - HID keyboard inventory and trust.

Enumerates keyboards through IOKit's registry (``ioreg`` plist output, no
kernel extension, no root) and notices when a keyboard that the user has not
trusted appears. The detector asks "how long ago did an untrusted keyboard
show up?" and raises its suspicion of a fast burst accordingly.

What this can and cannot do (honest version):
* It identifies keyboards by vendor id, product id, serial number (if the
  device reports one), transport (USB, Bluetooth, built-in) and product name.
* macOS does not tag individual key events with the device that produced
  them in the CGEvent API that DuckyGuard uses, so a blocked burst is
  *attributed* to the most recently attached untrusted keyboard, not proven
  to come from it. The incident says so.
* Polling runs once per second and takes ~10 ms; see docs/EVALUATION.md.
"""

from __future__ import annotations

import plistlib
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional, Set

KNOWN_INJECTOR_VIDS: Dict[int, str] = {
    0x0483: "STMicroelectronics (Flipper Zero uses this vendor id)",
    0x04D8: "Microchip (Hak5 USB Rubber Ducky uses this vendor id)",
    0x2E8A: "Raspberry Pi (Pico, pico-ducky)",
    0x16C0: "Van Ooijen / Teensy (common BadUSB boards)",
    0x1B4F: "SparkFun Pro Micro",
    0x2341: "Arduino (Leonardo / Micro, Keyboard.h sketches)",
    0x1209: "pid.codes open-source hardware",
}

BUILTIN_TRANSPORTS = {"FIFO", "SPU", "SPMI", "Audio"}


@dataclass
class Keyboard:
    key: str
    product: str
    manufacturer: str
    vendor_id: int
    product_id: int
    serial: str
    transport: str
    built_in: bool
    location_id: int
    first_seen: float
    vendor_note: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["vendor_hex"] = f"{self.vendor_id:04x}"
        d["product_hex"] = f"{self.product_id:04x}"
        return d


def _is_keyboard(node: dict) -> bool:
    pairs = node.get("DeviceUsagePairs") or []
    for p in pairs:
        if p.get("DeviceUsagePage") == 1 and p.get("DeviceUsage") in (6, 7):
            return True
    return node.get("PrimaryUsagePage") == 1 and node.get("PrimaryUsage") in (6, 7)


def parse_ioreg(plist_bytes: bytes, now: Optional[float] = None) -> List[Keyboard]:
    """Parse ``ioreg -a -r -c IOHIDDevice -l`` output into keyboards."""
    now = now or time.time()
    try:
        data = plistlib.loads(plist_bytes)
    except Exception:
        return []
    roots = data if isinstance(data, list) else [data]
    out: List[Keyboard] = []
    seen: Set[str] = set()
    for node in roots:
        if not isinstance(node, dict) or not _is_keyboard(node):
            continue
        vid = int(node.get("VendorID") or 0)
        pid = int(node.get("ProductID") or 0)
        product = str(node.get("Product") or "Unnamed keyboard")
        serial = str(node.get("SerialNumber") or "")
        transport = str(node.get("Transport") or "unknown")
        built_in = bool(node.get("Built-In")) or transport in BUILTIN_TRANSPORTS
        key = f"{vid:04x}:{pid:04x}:{transport}:{serial or product}"
        if key in seen:
            continue
        seen.add(key)
        out.append(Keyboard(
            key=key,
            product=product,
            manufacturer=str(node.get("Manufacturer") or ""),
            vendor_id=vid,
            product_id=pid,
            serial=serial,
            transport=transport,
            built_in=built_in,
            location_id=int(node.get("LocationID") or 0),
            first_seen=now,
            vendor_note=KNOWN_INJECTOR_VIDS.get(vid, ""),
        ))
    return out


def enumerate_keyboards() -> List[Keyboard]:
    try:
        proc = subprocess.run(["ioreg", "-a", "-r", "-c", "IOHIDDevice", "-l"],
                              capture_output=True, timeout=3.0)
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return parse_ioreg(proc.stdout)


class KeyboardWatcher:
    """
    Background poller. ``is_trusted(key)`` decides whether a keyboard counts as
    the user's own; everything else that appears after startup is "untrusted"
    until the user chooses to trust it.
    """

    def __init__(self, is_trusted: Callable[[str], bool], poll_interval: float = 1.0,
                 on_new_keyboard: Optional[Callable[[Keyboard], None]] = None,
                 enumerate=enumerate_keyboards):
        self.is_trusted = is_trusted
        self.poll_interval = poll_interval
        self.on_new_keyboard = on_new_keyboard
        self._enumerate = enumerate
        self._lock = threading.Lock()
        self._present: Dict[str, Keyboard] = {}
        self._last_untrusted: Optional[Keyboard] = None
        self._last_untrusted_at: Optional[float] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.poll_ms: float = 0.0
        self.refresh(initial=True)

    # ----------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="DuckyGuard-KeyboardWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while self._running:
            try:
                self.refresh()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    # ------------------------------------------------------------- queries

    def refresh(self, initial: bool = False) -> List[Keyboard]:
        t0 = time.perf_counter()
        current = {k.key: k for k in self._enumerate()}
        self.poll_ms = (time.perf_counter() - t0) * 1000.0
        new: List[Keyboard] = []
        with self._lock:
            for key, kb in current.items():
                if key not in self._present:
                    if not initial:
                        new.append(kb)
                    self._present[key] = kb
                else:
                    current[key] = self._present[key]  # keep first_seen
            for key in list(self._present):
                if key not in current:
                    del self._present[key]
            for kb in new:
                if not self.is_trusted(kb.key) and not kb.built_in:
                    self._last_untrusted = kb
                    self._last_untrusted_at = kb.first_seen
        for kb in new:
            if self.on_new_keyboard:
                try:
                    self.on_new_keyboard(kb)
                except Exception:
                    pass
        return list(current.values())

    def keyboards(self) -> List[Keyboard]:
        with self._lock:
            return list(self._present.values())

    def seconds_since_untrusted_keyboard(self) -> Optional[float]:
        with self._lock:
            if self._last_untrusted_at is None:
                return None
            if self._last_untrusted and self.is_trusted(self._last_untrusted.key):
                return None
            return time.time() - self._last_untrusted_at

    def last_untrusted(self) -> Optional[Keyboard]:
        with self._lock:
            return self._last_untrusted

    def forget_untrusted(self) -> None:
        with self._lock:
            self._last_untrusted = None
            self._last_untrusted_at = None
