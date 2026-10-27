"""Keyboard inventory parsing and the untrusted-keyboard timer."""

import plistlib
import time

from duckyguard.devices import KeyboardWatcher, parse_ioreg


def node(product, vid, pid, transport="USB", serial="", built_in=False, usage=6):
    d = {
        "Product": product, "Manufacturer": "ACME", "VendorID": vid, "ProductID": pid,
        "Transport": transport, "SerialNumber": serial, "LocationID": 1,
        "DeviceUsagePairs": [{"DeviceUsagePage": 1, "DeviceUsage": usage}],
        "IOObjectClass": "IOHIDDevice",
    }
    if built_in:
        d["Built-In"] = True
    return d


def test_parse_only_keyboards():
    data = [node("Flipper Zero", 0x0483, 0x5740), node("Mouse", 0x046D, 0xC077, usage=2),
            node("Apple Internal Keyboard / Trackpad", 0, 0, transport="FIFO", built_in=True)]
    kbs = parse_ioreg(plistlib.dumps(data))
    names = sorted(k.product for k in kbs)
    assert names == ["Apple Internal Keyboard / Trackpad", "Flipper Zero"]
    flip = [k for k in kbs if k.product == "Flipper Zero"][0]
    assert "Flipper" in flip.vendor_note
    assert not flip.built_in
    assert [k for k in kbs if k.built_in]


def test_parse_garbage_is_empty():
    assert parse_ioreg(b"not a plist") == []


def test_watcher_flags_new_untrusted_keyboard_and_trust_clears_it():
    present = [node("Apple Internal Keyboard / Trackpad", 0, 0, transport="FIFO", built_in=True)]
    trusted = set()
    attached = []
    w = KeyboardWatcher(is_trusted=lambda k: k in trusted, enumerate=lambda: parse_ioreg(plistlib.dumps(present)),
                        on_new_keyboard=attached.append)
    assert w.seconds_since_untrusted_keyboard() is None
    present.append(node("Flipper Zero", 0x0483, 0x5740, serial="ABC"))
    w.refresh()
    assert attached and attached[0].product == "Flipper Zero"
    age = w.seconds_since_untrusted_keyboard()
    assert age is not None and age < 1.0
    trusted.add(attached[0].key)
    assert w.seconds_since_untrusted_keyboard() is None


def test_watcher_ignores_builtin_and_trusted():
    present = [node("Apple Internal Keyboard / Trackpad", 0, 0, transport="FIFO", built_in=True)]
    w = KeyboardWatcher(is_trusted=lambda k: True, enumerate=lambda: parse_ioreg(plistlib.dumps(present)))
    present.append(node("Keychron", 0x3434, 0x0001))
    w.refresh()
    assert w.seconds_since_untrusted_keyboard() is None


def test_real_enumeration_runs():
    from duckyguard.devices import enumerate_keyboards
    t0 = time.perf_counter()
    kbs = enumerate_keyboards()
    assert (time.perf_counter() - t0) < 3.0
    assert isinstance(kbs, list)
