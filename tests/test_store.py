"""Store: private folder, owner-only permissions, trusted devices, incidents."""

import json
import os
import stat

from duckyguard.store import Store


def test_store_creates_private_folder_and_files(tmp_path):
    root = tmp_path / "DuckyGuard"
    s = Store(str(root))
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    s.set("quiet_mode", True)
    p = root / "settings.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert json.loads(p.read_text())["quiet_mode"] is True
    assert Store(str(root)).get("quiet_mode") is True


def test_trust_flow_persists(tmp_path):
    s = Store(str(tmp_path))
    key = "0483:5740:USB:Flipper"
    assert not s.is_trusted(key)
    s.trust_device(key, {"product": "Flipper Zero"})
    assert s.is_trusted(key)
    s2 = Store(str(tmp_path))
    assert s2.is_trusted(key)
    assert stat.S_IMODE(os.stat(tmp_path / "trusted_devices.json").st_mode) == 0o600
    s2.untrust_device(key)
    assert not Store(str(tmp_path)).is_trusted(key)


def test_incidents_round_trip_and_permissions(tmp_path):
    s = Store(str(tmp_path))
    p = s.save_incident({"id": "20260101-000000-000", "x": 1})
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert s.list_incidents()[0]["x"] == 1
    assert s.get_incident("20260101-000000-000")["x"] == 1
    assert s.delete_incident("20260101-000000-000")
    assert s.list_incidents() == []


def test_corrupt_settings_do_not_crash(tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    s = Store(str(tmp_path))
    assert s.get("protection_enabled") is True
    assert (tmp_path / "settings.json.corrupt").exists()


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKYGUARD_HOME", str(tmp_path / "x"))
    s = Store()
    assert s.root == str(tmp_path / "x")
