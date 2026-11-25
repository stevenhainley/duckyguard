"""Tests for DuckyGuard 2.2 features:
- Spotlight chord + launcher interception (Rule P1) and jittered dropper commands (Rule P2)
- Expanded macOS/Unix payload patterns and MITRE ATT&CK mappings
- SHA-256 hardware descriptor fingerprint pinning and trust policy import/export
- Lockdown mode (holding even trusted external keyboards without expiry)
- Tamper-evident SHA-256 hash-chained audit.jsonl log and CLI commands
"""

import json
import os
import random
import stat
import time

import pytest

from duckyguard.cli import main
from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector
from duckyguard.devices import Keyboard, device_fingerprint, identify_injector, identity_flags
from duckyguard.engine import Engine
from duckyguard.incidents import analyze_text, build_incident, finalize_incident, render_markdown
from duckyguard import store as store_mod
from duckyguard.store import GENESIS_HASH, Store


def make_kb(vid=0x05AC, pid=0x024F, product="Keychron K2", manufacturer="Keychron",
            serial="", transport="USB", built_in=False, location=1):
    key = f"{vid:04x}:{pid:04x}:{transport}:{serial or product}"
    return Keyboard(
        key=key, product=product, manufacturer=manufacturer,
        vendor_id=vid, product_id=pid, serial=serial, transport=transport,
        built_in=built_in, location_id=location, first_seen=time.time(),
    )


BUILTIN = make_kb(0, 0, "Apple Internal Keyboard / Trackpad", "Apple", transport="FIFO", built_in=True)


# ------------------------------------------------ Spotlight chord & Rule P

def test_spotlight_chord_blocks_terminal_opener_before_enter():
    """Cmd+Space -> 350ms Spotlight wait -> 'terminal\\n' at 28ms/key is stopped at 'termin' (key 6),
    before 'a', 'l', or Return can launch Terminal.app."""
    det = KeystrokeAnomalyDetector()
    assert not det.observe(KeyEvent(timestamp=1.000, char="[cmd]", modifier=True)).block
    assert not det.observe(KeyEvent(timestamp=1.012, char=" ", hold_time=0.040)).block
    t = 1.400  # > 350ms burst gap while Spotlight opens
    blocked_at = None
    verdict = None
    for idx, ch in enumerate("terminal\n"):
        t += 0.028
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.045))
        if v.block:
            blocked_at = idx + 1
            verdict = v
            break
    assert blocked_at == 6  # 't','e','r','m','i','n' -> blocked before 'a','l','\n'
    assert verdict.features["spotlight_chord"] is True
    assert verdict.features["pattern"] == "Spotlight to Terminal opener"
    assert str(verdict.features["rule"]).startswith(("P1", "B"))


def test_spotlight_chord_catches_jittered_opener_that_timing_alone_missed():
    """Jittered 42-62ms gaps (CV ~ 0.16, holds 65ms) evade Rules B/C/E on plain text,
    but after Cmd+Space typing 'terminal' triggers Rule P1 at 6 keys."""
    det = KeystrokeAnomalyDetector()
    det.observe(KeyEvent(timestamp=10.000, char="[cmd_l]", modifier=True))
    det.observe(KeyEvent(timestamp=10.020, char=" ", hold_time=0.065))
    t = 10.500
    gaps = [0.042, 0.061, 0.044, 0.059, 0.045, 0.060, 0.043, 0.058]
    blocked_at = None
    verdict = None
    for idx, ch in enumerate("terminal\n"):
        t += gaps[idx % len(gaps)]
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.070))
        if v.block:
            blocked_at = idx + 1
            verdict = v
            break
    assert blocked_at == 6
    assert str(verdict.features["rule"]).startswith("P1")


def test_human_opening_spotlight_and_typing_terminal_is_never_blocked():
    rng = random.Random(42)
    for _ in range(200):
        det = KeystrokeAnomalyDetector()
        det.observe(KeyEvent(timestamp=0.0, char="[cmd]", modifier=True))
        det.observe(KeyEvent(timestamp=rng.uniform(0.04, 0.14), char=" ", hold_time=0.085))
        t = rng.uniform(0.35, 0.90)
        for ch in "terminal\n":
            t += rng.lognormvariate(-2.35, 0.36)  # ~100-130 WPM human with natural variance
            v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=rng.uniform(0.065, 0.135)))
            assert not v.block, (v.features, v.reasons)


def test_spotlight_chord_window_expires_after_five_seconds():
    det = KeystrokeAnomalyDetector()
    det.observe(KeyEvent(timestamp=1.0, char="[cmd]", modifier=True))
    det.observe(KeyEvent(timestamp=1.02, char=" "))
    t = 8.0  # 7s later: chord expired
    for ch in "termin":
        t += 0.050
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.080))
    assert v.features.get("spotlight_chord") is False


def test_software_cmd_space_does_not_arm_hardware_spotlight_chord():
    det = KeystrokeAnomalyDetector()
    det.observe(KeyEvent(timestamp=1.0, char="[cmd]", modifier=True, injected=True, source_pid=555))
    det.observe(KeyEvent(timestamp=1.01, char=" ", injected=True, source_pid=555))
    t = 1.4
    for ch in "termin":
        t += 0.050
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.080))
    assert v.features.get("spotlight_chord") is False


@pytest.mark.parametrize("payload, expected_pattern", [
    ("python3 -c 'import os; os.system(\"id\")'\n", "Python one-liner"),
    ("security find-generic-password -wa CorpWiFi\n", "Keychain password lookup"),
    ("xattr -dr com.apple.quarantine /tmp/agent\n", "quarantine attribute strip"),
    ("launchctl bootstrap gui/501 ~/Library/LaunchAgents/a.plist\n", "launchctl persistence"),
    ("nohup /tmp/dropper >/dev/null 2>&1 & exit\n", "backgrounded shell exit"),
])
def test_jittered_macos_dropper_commands_caught_by_rule_p2(payload, expected_pattern):
    """Jittered ~21 keys/s (CV ~ 0.18, holds 75ms) evades v2.1's CV<0.15 Rule E,
    but Rule P2 catches known dropper commands at machine speed."""
    det = KeystrokeAnomalyDetector()
    gaps = [0.038, 0.056, 0.041, 0.058, 0.039, 0.055]
    t = 0.0
    seen_pattern = None
    blocked = False
    last_rule = None
    for idx, ch in enumerate(payload):
        t += gaps[idx % len(gaps)]
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.075))
        if v.features.get("pattern"):
            seen_pattern = v.features["pattern"]
        if v.block:
            blocked = True
            last_rule = str(v.features.get("rule") or "")
    assert seen_pattern == expected_pattern
    assert blocked is True
    assert last_rule.startswith(("P2", "E", "S"))


def test_fast_human_developer_typing_curl_pipe_sh_not_blocked():
    rng = random.Random(99)
    cmd = "curl -fsSL https://example.com/install.sh | sh\n"
    for _ in range(200):
        det = KeystrokeAnomalyDetector()
        t = 0.0
        for ch in cmd:
            t += rng.lognormvariate(-2.30, 0.38)
            v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=rng.uniform(0.060, 0.140)))
            assert not v.block, (v.features, v.reasons)


def test_new_macos_mitre_mappings_only_appear_when_matched():
    plain = analyze_text("echo just a harmless note")
    plain_ids = [m["id"] for m in plain["mitre"]]
    assert "T1555.001" not in plain_ids and "T1553.001" not in plain_ids and "T1059.006" not in plain_ids

    rich = analyze_text(
        "python3 -c 'print(1)' && security find-generic-password -wa WiFi && "
        "xattr -dr com.apple.quarantine /tmp/p && launchctl bootstrap gui/501 /tmp/p.plist"
    )
    rich_ids = {m["id"] for m in rich["mitre"]}
    assert {"T1674", "T1200", "T1059.006", "T1555.001", "T1553.001", "T1547.011"} <= rich_ids


# ------------------------------------ SHA-256 fingerprint pinning & devices

def test_device_fingerprint_is_deterministic_and_sensitive_to_maker():
    fp1 = device_fingerprint(0x05AC, 0x024F, "USB", "Keychron", "Keychron K2", "")
    fp2 = device_fingerprint(0x05AC, 0x024F, "usb", "  keychron ", "keychron k2", "")
    fp_spoof = device_fingerprint(0x05AC, 0x024F, "USB", "Generic HID", "Keychron K2", "")
    assert len(fp1) == 64
    assert fp1 == fp2
    assert fp1 != fp_spoof


def test_spoofed_manufacturer_with_same_device_key_triggers_fingerprint_mismatch_hold(tmp_path):
    store = Store(str(tmp_path))
    real = make_kb(0x05AC, 0x024F, product="Keychron K2", manufacturer="Keychron", serial="")
    store.trust_device(real.key, real.as_dict())
    saved = store.trusted_devices()[real.key]
    assert saved["fingerprint"] == real.fingerprint

    present = [BUILTIN]
    events = []
    eng = Engine(store=store, on_event=events.append, enumerate_keyboards=lambda: list(present), lock_screen=lambda: None)
    eng._can_block = True

    # Spoofed board shares exact VID, PID, transport, and product (so key matches!), but different manufacturer
    spoof = make_kb(0x05AC, 0x024F, product="Keychron K2", manufacturer="Arduino LLC", serial="")
    assert spoof.key == real.key
    present.append(spoof)
    eng.keyboards.refresh()

    assert eng.hold_active()
    attached = [e for e in events if e["event"] == "keyboard_attached"][-1]
    assert "fingerprint mismatch" in attached["flags"]
    assert attached["trusted"] is False and attached["held"] is True


def test_legacy_trusted_entry_without_fingerprint_stays_compatible():
    real = make_kb(0x3434, 0x0001, product="Keychron K2", manufacturer="Keychron", serial="")
    legacy_trusted = {real.key: {"product": "Keychron K2", "vendor_id": 0x3434, "product_id": 0x0001}}
    assert identity_flags(real, [BUILTIN], legacy_trusted) == []


def test_trusted_devices_export_and_import_cli(tmp_path, monkeypatch, capsys):
    home_a = tmp_path / "home_a"
    home_b = tmp_path / "home_b"
    export_file = tmp_path / "policy.json"

    s_a = Store(str(home_a))
    kb1 = make_kb(0x05AC, 0x024F, product="Keychron K2", manufacturer="Keychron", serial="SN01")
    s_a.trust_device(kb1.key, kb1.as_dict())

    monkeypatch.setenv("DUCKYGUARD_HOME", str(home_a))
    assert main(["devices", "--export", str(export_file)]) == 0
    capsys.readouterr()
    assert stat.S_IMODE(os.stat(export_file).st_mode) == 0o600

    monkeypatch.setenv("DUCKYGUARD_HOME", str(home_b))
    s_b = Store(str(home_b))
    other = make_kb(0x046D, 0xC31C, product="Logi K120", manufacturer="Logitech", serial="LG99")
    s_b.trust_device(other.key, other.as_dict())

    # Merge import keeps both
    assert main(["devices", "--import", str(export_file)]) == 0
    capsys.readouterr()
    s_b2 = Store(str(home_b))
    assert s_b2.is_trusted(kb1.key) and s_b2.is_trusted(other.key)
    assert s_b2.trusted_devices()[kb1.key]["fingerprint"] == kb1.fingerprint

    # Replace import keeps only exported policy
    assert main(["devices", "--import", str(export_file), "--replace"]) == 0
    capsys.readouterr()
    s_b3 = Store(str(home_b))
    assert s_b3.is_trusted(kb1.key) and not s_b3.is_trusted(other.key)

    # CLI --trust / --untrust / --json
    assert main(["devices", "--untrust", kb1.key]) == 0
    capsys.readouterr()
    assert not Store(str(home_b)).is_trusted(kb1.key)
    assert main(["devices", "--trust", kb1.key]) == 0
    capsys.readouterr()
    assert Store(str(home_b)).is_trusted(kb1.key)
    assert main(["devices", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert kb1.key in out["trusted"]


def test_sparkfun_and_seeed_hobby_boards_identified_with_sources():
    for vid in (0x1B4F, 0x2886):
        hit = identify_injector(make_kb(vid, 0x0001, product="HID Board", manufacturer="DIY"))
        assert hit and hit["confidence"] == "hobby board" and hit["source"].startswith("https://")


def test_markdown_report_shows_descriptor_fingerprint():
    kb = make_kb(0x046D, 0xC529, product="Flipper Zero", manufacturer="Flipper Devices")
    verdict = {"block": True, "score": 0.9, "reasons": ["fast"], "kind": "machine",
               "features": {"burst_len": 6, "rule": "K: 6 keys"}, "explanation": "Blocked."}
    inc = finalize_incident(build_incident(verdict, kb.as_dict(), "ab"), "cdef", 4)
    md = render_markdown(inc, "2.2.0")
    assert kb.fingerprint in md


# ------------------------------------------------------------ Lockdown mode

def test_lockdown_holds_even_trusted_external_keyboards_and_never_expires(tmp_path):
    store = Store(str(tmp_path))
    trusted_kb = make_kb(0x05AC, 0x024F, product="Keychron K2", manufacturer="Keychron", serial="HOME1")
    store.trust_device(trusted_kb.key, trusted_kb.as_dict())

    present = [BUILTIN]
    events = []
    eng = Engine(store=store, on_event=events.append, enumerate_keyboards=lambda: list(present), lock_screen=lambda: None)
    eng._can_block = True
    eng.set_lockdown(True)

    # Even though Keychron K2 is on the trust list (or a clone spoofing its exact VID:PID:serial),
    # Lockdown mode holds it on plug-in and never lets the countdown expire.
    present.append(trusted_kb)
    eng.keyboards.refresh()
    assert eng.hold_active()
    assert eng.should_drop_hardware(injected=False, now=time.time() + 7200)
    attached = [e for e in events if e["event"] == "keyboard_attached"][-1]
    assert "lockdown active" in attached["flags"]

    # Approving once releases the current hold
    assert eng.allow_keyboard(trusted_kb.key, trust=False)
    assert not eng.hold_active()


def test_enabling_lockdown_immediately_holds_connected_untrusted_keyboard(tmp_path):
    untrusted = make_kb(0x1234, 0x5678, product="Coffee Shop Dongle")
    store = Store(str(tmp_path))
    store.set("hold_new_keyboards", False)
    eng = Engine(store=store, enumerate_keyboards=lambda: [BUILTIN, untrusted], lock_screen=lambda: None)
    eng._can_block = True
    assert not eng.hold_active()

    eng.set_lockdown(True)
    assert eng.hold_active()
    assert eng._hold["key"] == untrusted.key


def test_lockdown_cli_round_trip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DUCKYGUARD_HOME", str(tmp_path))
    assert main(["lockdown", "on"]) == 0
    assert json.loads(capsys.readouterr().out)["lockdown_mode"] is True
    assert main(["lockdown"]) == 0
    assert json.loads(capsys.readouterr().out)["lockdown_mode"] is True
    assert main(["lockdown", "off"]) == 0
    assert json.loads(capsys.readouterr().out)["lockdown_mode"] is False


# ------------------------------------ Tamper-evident SHA-256 audit.jsonl log

def test_audit_log_hash_chain_persistence_and_verification(tmp_path):
    s = Store(str(tmp_path))
    r1 = s.append_audit("engine_started", {"can_block": True}, ts=1795000000.0)
    r2 = s.append_audit("keyboard_attached", {"key": "046d:c529:USB:Flipper"}, ts=1795000005.0)
    assert r1["seq"] == 1 and r1["prev_hash"] == GENESIS_HASH
    assert r2["seq"] == 2 and r2["prev_hash"] == r1["hash"]
    assert stat.S_IMODE(os.stat(s.audit_path).st_mode) == 0o600

    # Reopening Store continues the chain cleanly
    s2 = Store(str(tmp_path))
    r3 = s2.append_audit("hold_ended", {"result": "unplugged", "dropped": 42}, ts=1795000012.0)
    assert r3["seq"] == 3 and r3["prev_hash"] == r2["hash"]

    ver = s2.verify_audit()
    assert ver == {"ok": True, "entries": 3, "broken_at": None, "reason": None, "head_hash": r3["hash"]}
    assert len(s2.read_audit(limit=2)) == 2


def test_audit_verify_detects_edited_or_deleted_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DUCKYGUARD_HOME", str(tmp_path))
    s = Store(str(tmp_path))
    for i in range(4):
        s.append_audit("evt", {"n": i})

    assert main(["audit", "--verify"]) == 0
    capsys.readouterr()

    # Tamper with detail value on line 2 without updating hashes
    lines = open(s.audit_path, encoding="utf-8").read().splitlines()
    rec2 = json.loads(lines[1])
    rec2["details"]["n"] = 999
    lines[1] = json.dumps(rec2, sort_keys=True)
    with open(s.audit_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    res = Store(str(tmp_path)).verify_audit()
    assert res["ok"] is False and res["broken_at"] == 2 and "hash" in res["reason"]
    assert main(["audit", "--verify"]) == 1
    capsys.readouterr()

    # Delete line 2 -> sequence gap / prev_hash break
    del lines[1]
    with open(s.audit_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    res2 = Store(str(tmp_path)).verify_audit()
    assert res2["ok"] is False and res2["broken_at"] == 2


def test_audit_log_rotates_cleanly_at_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "MAX_AUDIT_BYTES", 600)
    s = Store(str(tmp_path))
    for i in range(10):
        s.append_audit("bulk_event", {"index": i, "pad": "x" * 80})
    assert os.path.exists(s.audit_path + ".1")
    ver = s.verify_audit()
    assert ver["ok"] is True and ver["entries"] >= 1
    rows = s.read_audit(limit=0)
    assert "rotated_from" in rows[0]["details"]


def test_engine_writes_forensic_audit_trail_and_cli_prints_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DUCKYGUARD_HOME", str(tmp_path))
    store = Store(str(tmp_path))
    present = [BUILTIN]
    eng = Engine(store=store, enumerate_keyboards=lambda: list(present), lock_screen=lambda: None)
    eng._can_block = True

    flip = make_kb(0x046D, 0xC529, product="Flipper Zero", manufacturer="Flipper Devices")
    present.append(flip)
    eng.keyboards.refresh()
    eng.note_held_key()
    eng.note_held_key()
    eng.block_keyboard(flip.key)
    present.remove(flip)
    eng.keyboards.refresh()

    assert store.verify_audit()["ok"] is True
    events = [r["event"] for r in store.read_audit(limit=20)]
    assert "keyboard_attached" in events and "hold_ended" in events and "keyboard_removed" in events

    assert main(["audit", "--json"]) == 0
    json_lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert any(r["event"] == "hold_ended" and r["details"]["dropped"] == 2 for r in json_lines)

    assert main(["audit"]) == 0
    human_out = capsys.readouterr().out
    assert "hold_ended" in human_out and "dropped=2" in human_out
