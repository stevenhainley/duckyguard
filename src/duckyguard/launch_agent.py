"""
DuckyGuard - launch at login.

Writes (or removes) a per-user LaunchAgent:
    ~/Library/LaunchAgents/co.shindustries.duckyguard.plist
This works for an unsigned app; no SMAppService / signing required. The plist
points at whatever is running now: the .app bundle if there is one, otherwise
``python -m duckyguard app``.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from typing import List, Optional

LABEL = "co.shindustries.duckyguard"


def plist_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", f"{LABEL}.plist")


def bundle_path() -> Optional[str]:
    try:
        from Foundation import NSBundle
        p = NSBundle.mainBundle().bundlePath()
        if p and p.endswith(".app"):
            return p
    except Exception:
        pass
    return None


def program_arguments() -> List[str]:
    b = bundle_path()
    if b:
        exe = os.path.join(b, "Contents", "MacOS", "DuckyGuard")
        if os.path.exists(exe):
            return [exe]
        return ["/usr/bin/open", "-a", b]
    return [sys.executable, "-m", "duckyguard", "app"]


def is_enabled() -> bool:
    return os.path.exists(plist_path())


def build_plist(keep_alive: bool = False) -> dict:
    """keep_alive relaunches DuckyGuard after a crash or a kill, but not after a normal Quit (exit status 0)."""
    return {
        "Label": LABEL,
        "ProgramArguments": program_arguments(),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False} if keep_alive else False,
        "ProcessType": "Interactive",
    }


def enable(keep_alive: bool = False) -> str:
    p = plist_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = build_plist(keep_alive)
    with open(p, "wb") as f:
        plistlib.dump(data, f)
    try:
        subprocess.run(["launchctl", "load", "-w", p], capture_output=True, timeout=5)
    except Exception:
        pass
    return p


def disable() -> None:
    p = plist_path()
    try:
        subprocess.run(["launchctl", "unload", "-w", p], capture_output=True, timeout=5)
    except Exception:
        pass
    try:
        os.unlink(p)
    except OSError:
        pass
