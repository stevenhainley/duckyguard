"""
DuckyGuard - macOS permission checks.

DuckyGuard needs two things from Privacy & Security:

* Input Monitoring: to see keystrokes system-wide (CGEvent tap, listen).
* Accessibility: to *drop* keystrokes (an active CGEvent tap). Without it
  DuckyGuard can only warn.

Both checks are read-only system calls; nothing is prompted unless the user
clicks "Open System Settings".
"""

from __future__ import annotations

import ctypes
import ctypes.util
import functools
import subprocess
from typing import Dict


@functools.lru_cache(maxsize=None)
def _lib(path: str):
    return ctypes.cdll.LoadLibrary(path)

INPUT_MONITORING_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
LOGIN_ITEMS_URL = "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"

_kIOHIDRequestTypeListenEvent = 1
_kIOHIDAccessTypeGranted = 0


def input_monitoring_granted() -> bool:
    """IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) == granted (macOS 10.15+)."""
    try:
        iokit = _lib("/System/Library/Frameworks/IOKit.framework/IOKit")
        fn = iokit.IOHIDCheckAccess
        fn.restype = ctypes.c_uint32
        fn.argtypes = [ctypes.c_uint32]
        return fn(_kIOHIDRequestTypeListenEvent) == _kIOHIDAccessTypeGranted
    except Exception:
        return False


def accessibility_granted() -> bool:
    """AXIsProcessTrusted()."""
    try:
        appsvc = _lib("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        fn = appsvc.AXIsProcessTrusted
        fn.restype = ctypes.c_bool
        return bool(fn())
    except Exception:
        return False


def request_input_monitoring() -> None:
    """Asks macOS to show the Input Monitoring prompt for this process (once)."""
    try:
        iokit = _lib("/System/Library/Frameworks/IOKit.framework/IOKit")
        fn = iokit.IOHIDRequestAccess
        fn.restype = ctypes.c_bool
        fn.argtypes = [ctypes.c_uint32]
        fn(_kIOHIDRequestTypeListenEvent)
    except Exception:
        pass


def request_accessibility() -> None:
    """Asks macOS to show its Accessibility prompt, which also adds this app to the list in System Settings
    so the user only has to flip the switch."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass


def secure_input_active() -> bool:
    """True while macOS Secure Input is on (a password field has focus). Event taps receive no keys then,
    so DuckyGuard cannot see or drop typing until it ends. IsSecureEventInputEnabled() is public Carbon API."""
    try:
        carbon = _lib("/System/Library/Frameworks/Carbon.framework/Carbon")
        fn = carbon.IsSecureEventInputEnabled
        fn.restype = ctypes.c_bool
        return bool(fn())
    except Exception:
        return False


def lock_screen() -> bool:
    """Locks the screen now. Uses SACLockScreenImmediate from the private login framework: there is no
    public call for this, so it may stop working in a future macOS. Returns False if it could not be called."""
    try:
        login = _lib("/System/Library/PrivateFrameworks/login.framework/Versions/Current/login")
        login.SACLockScreenImmediate()
        return True
    except Exception:
        return False


def open_settings(url: str) -> None:
    try:
        subprocess.Popen(["open", url])
    except Exception:
        pass


def status() -> Dict[str, bool]:
    im = input_monitoring_granted()
    ax = accessibility_granted()
    return {
        "input_monitoring": im,
        "accessibility": ax,
        "can_observe": im or ax,
        "can_block": ax,
    }
