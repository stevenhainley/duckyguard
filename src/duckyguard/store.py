"""
DuckyGuard - on-disk state.

Everything DuckyGuard remembers lives in one folder that only the current user
can read:

    ~/Library/Application Support/DuckyGuard/
        settings.json           user preferences
        trusted_devices.json    keyboards the user chose to trust
        incidents/              one JSON file per blocked burst (+ raw captured text)
        exports/                Markdown reports the user exported

The folder is created with mode 0700 and every file with mode 0600. Nothing is
ever written anywhere else and nothing is sent anywhere.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from typing import Any, Dict, List, Optional

APP_NAME = "DuckyGuard"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "protection_enabled": True,
    "quiet_mode": False,            # block + log, but no sound or banner
    "launch_at_login": False,
    "check_updates": False,         # one HTTPS GET to GitHub releases, at most daily, opt-in
    "last_update_check": 0,
    "onboarded": False,
    "quarantine_seconds": 2.0,      # keep dropping keys this long after the last blocked key
    "score_software_input": False,  # expert: also score keystrokes typed by local programs
}


def support_dir(base: Optional[str] = None) -> str:
    if base:
        return base
    env = os.environ.get("DUCKYGUARD_HOME")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)


def _secure_dir(path: str) -> None:
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def write_private(path: str, data: str) -> None:
    """Atomic write with 0600 permissions."""
    d = os.path.dirname(path)
    _secure_dir(d)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Store:
    """Settings, trusted devices and incidents, all under one private folder."""

    def __init__(self, base: Optional[str] = None):
        self.root = support_dir(base)
        self.incidents_dir = os.path.join(self.root, "incidents")
        self.exports_dir = os.path.join(self.root, "exports")
        for d in (self.root, self.incidents_dir, self.exports_dir):
            _secure_dir(d)
        self._lock = threading.RLock()
        self._settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._settings.update(self._read_json("settings.json", {}))
        self._trusted: Dict[str, dict] = self._read_json("trusted_devices.json", {})

    # ---------------------------------------------------------------- helpers

    def path(self, name: str) -> str:
        return os.path.join(self.root, name)

    def _read_json(self, name: str, default):
        p = self.path(name)
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            # Corrupt file: keep a copy for the user, start fresh.
            try:
                os.replace(p, p + ".corrupt")
            except OSError:
                pass
            return default

    def _write_json(self, name: str, obj) -> None:
        write_private(self.path(name), json.dumps(obj, indent=2, sort_keys=True))

    # --------------------------------------------------------------- settings

    def get(self, key: str, default=None):
        with self._lock:
            return self._settings.get(key, DEFAULT_SETTINGS.get(key, default))

    def set(self, key: str, value) -> None:
        with self._lock:
            self._settings[key] = value
            self._write_json("settings.json", self._settings)

    def settings(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._settings)

    # ---------------------------------------------------------- trusted devices

    def trusted_devices(self) -> Dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._trusted.items()}

    def is_trusted(self, device_key: str) -> bool:
        with self._lock:
            return device_key in self._trusted

    def trust_device(self, device_key: str, info: dict) -> None:
        import time
        with self._lock:
            entry = dict(info)
            entry["trusted_at"] = time.time()
            self._trusted[device_key] = entry
            self._write_json("trusted_devices.json", self._trusted)

    def untrust_device(self, device_key: str) -> None:
        with self._lock:
            if device_key in self._trusted:
                del self._trusted[device_key]
                self._write_json("trusted_devices.json", self._trusted)

    # ---------------------------------------------------------------- incidents

    def save_incident(self, incident: dict) -> str:
        name = f"incident-{incident['id']}.json"
        p = os.path.join(self.incidents_dir, name)
        write_private(p, json.dumps(incident, indent=2))
        return p

    def list_incidents(self, limit: int = 200) -> List[dict]:
        out: List[dict] = []
        try:
            names = sorted(os.listdir(self.incidents_dir), reverse=True)
        except OSError:
            return out
        for n in names:
            if not n.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.incidents_dir, n), "r", encoding="utf-8") as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                continue
            if len(out) >= limit:
                break
        return out

    def get_incident(self, incident_id: str) -> Optional[dict]:
        p = os.path.join(self.incidents_dir, f"incident-{os.path.basename(incident_id)}.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def delete_incident(self, incident_id: str) -> bool:
        p = os.path.join(self.incidents_dir, f"incident-{os.path.basename(incident_id)}.json")
        try:
            os.unlink(p)
            return True
        except OSError:
            return False

    def clear_incidents(self) -> int:
        n = 0
        for inc in self.list_incidents(limit=10000):
            n += int(self.delete_incident(inc["id"]))
        return n
