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

import copy
import datetime
import hashlib
import json
import os
import stat
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

APP_NAME = "DuckyGuard"
GENESIS_HASH = "0" * 64
MAX_AUDIT_BYTES = 5 * 1024 * 1024

DEFAULT_SETTINGS: Dict[str, Any] = {
    "protection_enabled": True,
    "quiet_mode": False,            # block + log, but no sound or banner
    "launch_at_login": False,
    "check_updates": False,         # one HTTPS GET to GitHub releases, at most daily, opt-in
    "last_update_check": 0,
    "onboarded": False,
    "quarantine_seconds": 2.0,      # keep dropping keys this long after the last blocked key
    "score_software_input": False,  # expert: also score keystrokes typed by local programs
    "hold_new_keyboards": True,     # drop every hardware key from the moment an untrusted keyboard appears until it is approved
    "hold_seconds": 20.0,           # a hold nobody answers ends after this long (the keyboard stays untrusted)
    "away_mode": False,             # holds never expire: nothing new can type until you approve it
    "lockdown_mode": False,         # hold every new external keyboard, even trusted ones, with no expiry
    "monitor_only": False,          # detect and record, but never drop a key (for trying DuckyGuard out)
    "lock_on_block": False,         # lock the screen when a real attack is blocked
    "keep_alive": False,            # with launch at login: relaunch if DuckyGuard is killed
}


def _audit_entry_hash(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        self._incidents: Optional[List[dict]] = None     # newest first; re-read only when the folder changes
        self._incidents_stamp: Optional[int] = None
        self._audit_seq: Optional[int] = None
        self._audit_hash: Optional[str] = None
        self.audit_path = self.path("audit.jsonl")

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
        from .devices import device_fingerprint
        with self._lock:
            entry = dict(info)
            if not entry.get("fingerprint") and any(k in entry for k in ("vendor_id", "product_id", "transport")):
                fp = device_fingerprint(
                    int(entry.get("vendor_id") or 0),
                    int(entry.get("product_id") or 0),
                    str(entry.get("transport") or ""),
                    str(entry.get("manufacturer") or ""),
                    str(entry.get("product") or ""),
                    str(entry.get("serial") or ""),
                )
                entry["fingerprint"] = fp
                entry["fingerprint_short"] = fp[:12]
            elif entry.get("fingerprint") and not entry.get("fingerprint_short"):
                entry["fingerprint_short"] = str(entry["fingerprint"])[:12]
            entry["trusted_at"] = time.time()
            self._trusted[device_key] = entry
            self._write_json("trusted_devices.json", self._trusted)

    def untrust_device(self, device_key: str) -> None:
        with self._lock:
            if device_key in self._trusted:
                del self._trusted[device_key]
                self._write_json("trusted_devices.json", self._trusted)

    def export_trusted_devices(self, dest_path: str) -> dict:
        payload = {
            "schema": "duckyguard.trusted_devices.v1",
            "exported_at": round(time.time(), 3),
            "devices": self.trusted_devices(),
        }
        write_private(os.path.abspath(dest_path), json.dumps(payload, indent=2, sort_keys=True))
        return payload

    def import_trusted_devices(self, src_path: str, merge: bool = True) -> int:
        from .devices import device_fingerprint
        with open(src_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("trusted device file must contain a JSON object")
        devices = raw.get("devices") if "devices" in raw and isinstance(raw.get("devices"), dict) else raw
        if not isinstance(devices, dict):
            raise ValueError("invalid devices map")
        cleaned: Dict[str, dict] = {}
        now = time.time()
        for key, info in devices.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(info, dict):
                raise ValueError(f"invalid device entry for {key!r}")
            entry = dict(info)
            if not entry.get("fingerprint") and any(k in entry for k in ("vendor_id", "product_id", "transport")):
                fp = device_fingerprint(
                    int(entry.get("vendor_id") or 0),
                    int(entry.get("product_id") or 0),
                    str(entry.get("transport") or ""),
                    str(entry.get("manufacturer") or ""),
                    str(entry.get("product") or ""),
                    str(entry.get("serial") or ""),
                )
                entry["fingerprint"] = fp
                entry["fingerprint_short"] = fp[:12]
            entry.setdefault("trusted_at", now)
            cleaned[key] = entry
        with self._lock:
            if not merge:
                self._trusted = {}
            self._trusted.update(cleaned)
            self._write_json("trusted_devices.json", self._trusted)
        self.append_audit("trusted_devices_imported", {"count": len(cleaned), "merge": bool(merge)})
        return len(cleaned)

    # ---------------------------------------------------------------- incidents

    def save_incident(self, incident: dict) -> str:
        name = f"incident-{incident['id']}.json"
        p = os.path.join(self.incidents_dir, name)
        write_private(p, json.dumps(incident, indent=2))
        self._incidents = None
        return p

    def list_incidents(self, limit: int = 200) -> List[dict]:
        """Newest first. The files are read once and again only when the folder changes, so the
        dashboard's once-a-second snapshot costs one stat() instead of a hundred file reads."""
        with self._lock:
            try:
                stamp = os.stat(self.incidents_dir).st_mtime_ns
            except OSError:
                return []
            if self._incidents is None or stamp != self._incidents_stamp:
                out: List[dict] = []
                try:
                    names = sorted(os.listdir(self.incidents_dir), reverse=True)
                except OSError:
                    names = []
                for n in names:
                    if not n.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(self.incidents_dir, n), "r", encoding="utf-8") as f:
                            out.append(json.load(f))
                    except (OSError, ValueError):
                        continue
                self._incidents, self._incidents_stamp = out, stamp
            return copy.deepcopy(self._incidents[:limit])

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
            self._incidents = None
            return True
        except OSError:
            return False

    def clear_incidents(self) -> int:
        n = 0
        for inc in self.list_incidents(limit=10000):
            n += int(self.delete_incident(inc["id"]))
        return n

    # -------------------------------------------------------------- audit log

    def _ensure_audit_tail(self) -> None:
        if self._audit_seq is not None and self._audit_hash is not None:
            return
        seq = 0
        last_hash = GENESIS_HASH
        try:
            with open(self.audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    seq = int(rec.get("seq") or (seq + 1))
                    last_hash = str(rec.get("hash") or last_hash)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            try:
                os.replace(self.audit_path, self.audit_path + ".corrupt")
            except OSError:
                pass
            seq, last_hash = 0, GENESIS_HASH
        self._audit_seq = seq
        self._audit_hash = last_hash

    def append_audit(self, event: str, details: Optional[dict] = None, ts: Optional[float] = None) -> dict:
        """Append one SHA-256 hash-chained event to audit.jsonl (owner-only 0600)."""
        now = time.time() if ts is None else float(ts)
        with self._lock:
            self._ensure_audit_tail()
            rotated_from = None
            try:
                if os.path.exists(self.audit_path) and os.path.getsize(self.audit_path) >= MAX_AUDIT_BYTES:
                    rotated_from = self._audit_hash
                    os.replace(self.audit_path, self.audit_path + ".1")
                    self._audit_seq = 0
                    self._audit_hash = GENESIS_HASH
            except OSError:
                pass
            seq = (self._audit_seq or 0) + 1
            prev_hash = self._audit_hash or GENESIS_HASH
            det = dict(details or {})
            if rotated_from:
                det["rotated_from"] = rotated_from
            iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            body = {
                "seq": seq,
                "ts": round(now, 3),
                "iso": iso,
                "event": str(event),
                "details": det,
                "prev_hash": prev_hash,
            }
            digest = _audit_entry_hash(body)
            rec = dict(body, hash=digest)
            line = json.dumps(rec, sort_keys=True) + "\n"
            _secure_dir(self.root)
            fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                with os.fdopen(fd, "a", encoding="utf-8") as f:
                    f.write(line)
                os.chmod(self.audit_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                raise
            self._audit_seq = seq
            self._audit_hash = digest
            return rec

    def read_audit(self, limit: int = 100) -> List[dict]:
        with self._lock:
            try:
                with open(self.audit_path, "r", encoding="utf-8") as f:
                    rows = [json.loads(line) for line in f if line.strip()]
            except FileNotFoundError:
                return []
            except (OSError, ValueError):
                return []
            return rows[-limit:] if limit > 0 else rows

    def verify_audit(self) -> dict:
        """Verify sequential links and SHA-256 digests across audit.jsonl."""
        with self._lock:
            if not os.path.exists(self.audit_path):
                return {"ok": True, "entries": 0, "broken_at": None, "reason": None, "head_hash": GENESIS_HASH}
            expected_prev = GENESIS_HASH
            count = 0
            try:
                with open(self.audit_path, "r", encoding="utf-8") as f:
                    for idx, raw in enumerate(f, start=1):
                        s = raw.strip()
                        if not s:
                            continue
                        try:
                            rec = json.loads(s)
                        except ValueError:
                            return {"ok": False, "entries": count, "broken_at": idx,
                                    "reason": "corrupt JSON line", "head_hash": expected_prev}
                        if not isinstance(rec, dict):
                            return {"ok": False, "entries": count, "broken_at": idx,
                                    "reason": "non-object JSON record", "head_hash": expected_prev}
                        count += 1
                        if rec.get("seq") != count:
                            return {"ok": False, "entries": count, "broken_at": count,
                                    "reason": f"sequence gap: expected {count}, got {rec.get('seq')}",
                                    "head_hash": expected_prev}
                        if rec.get("prev_hash") != expected_prev:
                            return {"ok": False, "entries": count, "broken_at": count,
                                    "reason": "prev_hash chain mismatch", "head_hash": expected_prev}
                        claimed = rec.get("hash")
                        body = {k: v for k, v in rec.items() if k != "hash"}
                        actual = _audit_entry_hash(body)
                        if claimed != actual:
                            return {"ok": False, "entries": count, "broken_at": count,
                                    "reason": "entry hash mismatch", "head_hash": expected_prev}
                        expected_prev = actual
            except OSError as e:
                return {"ok": False, "entries": count, "broken_at": count + 1,
                        "reason": f"read error: {e}", "head_hash": expected_prev}
            return {"ok": True, "entries": count, "broken_at": None, "reason": None, "head_hash": expected_prev}
