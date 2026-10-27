"""
DuckyGuard - update notice (opt-in).

One HTTPS GET to GitHub's releases API, at most once a day, only when the user
turned "Check for updates" on or pressed "Check now". The request carries no
identifier beyond what any HTTPS client sends. The result is a notice in the
app; DuckyGuard never downloads or installs anything by itself.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Optional

from . import __version__

RELEASES_URL = "https://api.github.com/repos/stevenhainley/DuckyGuard/releases/latest"


def _parse(v: str):
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check(timeout: float = 6.0) -> dict:
    """Returns {'ok': bool, 'latest': str|None, 'newer': bool, 'url': str|None, 'message': str}."""
    try:
        req = urllib.request.Request(RELEASES_URL, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": f"DuckyGuard/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        if not tag:
            return {"ok": True, "latest": None, "newer": False, "url": None, "message": "No releases published yet."}
        newer = _parse(tag) > _parse(__version__)
        return {"ok": True, "latest": tag, "newer": newer, "url": data.get("html_url"),
                "message": (f"Version {tag} is available." if newer else f"You have the latest version ({__version__}).")}
    except Exception as e:  # offline, 404 (no releases yet), rate limit...
        msg = str(e)
        if "404" in msg:
            msg = "No releases published yet."
        elif "URLError" in type(e).__name__ or "timed out" in msg:
            msg = "Could not reach GitHub. Try again later."
        return {"ok": False, "latest": None, "newer": False, "url": None, "message": msg}


def should_check(last_check: float, enabled: bool, now: Optional[float] = None) -> bool:
    if not enabled:
        return False
    now = now or time.time()
    return (now - float(last_check or 0)) > 24 * 3600
