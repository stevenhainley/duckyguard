"""Things that keep DuckyGuard itself safe and honest: what the safe test types, timed pauses,
picking up permissions granted after launch, one event per plug-in, and a snapshot that does not hit the disk."""

import json
import time

from duckyguard import simulator
from duckyguard.devices import Keyboard
from duckyguard.engine import Engine, STATUS_NO_PERMISSION, STATUS_OBSERVING, STATUS_PAUSED, STATUS_PROTECTED
from duckyguard.store import Store


def kb(product="Mystery Keyboard", vid=0x1234, pid=0x5678, built_in=False, transport="USB"):
    return Keyboard(key=f"{vid:04x}:{pid:04x}:{transport}:{product}", product=product, manufacturer="", vendor_id=vid,
                    product_id=pid, serial="", transport=transport, built_in=built_in, location_id=1, first_seen=time.time())


BUILTIN = kb("Apple Internal Keyboard / Trackpad", 0, 0, built_in=True, transport="FIFO")


def engine(tmp_path, present=None, **settings):
    store = Store(str(tmp_path))
    for k, v in settings.items():
        store.set(k, v)
    present = present if present is not None else [BUILTIN]
    events = []
    eng = Engine(store=store, on_event=events.append, enumerate_keyboards=lambda: list(present), lock_screen=lambda: None)
    eng._can_block = True
    return eng, events, present


# ------------------------------------------------------------------- the safe test

def test_no_preset_contains_a_command_or_a_return():
    for name, text in simulator.PRESETS.items():
        assert "\n" not in text and "\r" not in text, name
        for word in ("curl", "|", "sh ", "http", "sudo", ";", "&&"):
            assert word not in text, f"{name}: {word}"


class FakeKeys:
    """Stands in for Quartz so the simulator can run in a test."""

    def __init__(self):
        self.posted = []

    def install(self, sim):
        sim._create = lambda _src, code, down: {"code": code, "down": down}
        sim._set_str = lambda ev, _n, ch: ev.update(ch=ch)
        sim._post = lambda _tap, ev: self.posted.append(ev)
        sim._tap = None
        return sim


def sim_with_fake_keys():
    fake = FakeKeys()
    return fake.install(simulator.BadUSBSimulator.__new__(simulator.BadUSBSimulator)), fake


def test_simulator_never_presses_return_even_if_asked():
    sim, fake = sim_with_fake_keys()
    assert sim.run(text="ab\ncd\r", interval_ms=0) is True
    assert [e["ch"] for e in fake.posted if e["down"]] == list("abcd")
    assert all(e["code"] != 36 for e in fake.posted)


def test_simulator_stops_when_the_window_loses_focus():
    sim, fake = sim_with_fake_keys()
    focus = iter([True, True, True, False, True, True])
    assert sim.run(text="abcdef", interval_ms=0, keep_going=lambda: next(focus)) is False
    assert [e["ch"] for e in fake.posted if e["down"]] == list("abc")


# -------------------------------------------------------------------- timed pauses

def test_timed_pause_resumes_on_its_own_and_is_not_remembered(tmp_path, monkeypatch):
    eng, events, _ = engine(tmp_path)
    eng.store.set("protection_enabled", True)
    started = []
    monkeypatch.setattr(eng, "start", lambda: started.append(1) or STATUS_PROTECTED)
    eng.pause(300, now=1000.0)
    assert eng.status == STATUS_PAUSED and eng.paused_until == 1300.0
    assert eng.store.get("protection_enabled") is True          # a relaunch comes back protected
    assert eng.snapshot()["paused_until"] == 1300.0
    assert eng.resume_if_due(now=1299.0) is False and not started
    assert eng.resume_if_due(now=1300.5) is True and started == [1]
    assert eng.paused_until is None


def test_pause_until_resumed_is_remembered(tmp_path):
    eng, _, _ = engine(tmp_path)
    eng.store.set("protection_enabled", True)
    eng.pause(None)
    assert eng.status == STATUS_PAUSED and eng.paused_until is None
    assert eng.store.get("protection_enabled") is False
    assert eng.resume_if_due(now=time.time() + 10 ** 6) is False


# ------------------------------------------------- permissions granted after launch

def test_engine_notices_accessibility_granted_after_launch(tmp_path):
    eng, _, _ = engine(tmp_path)
    eng._running, eng._can_block, eng.status = True, False, STATUS_OBSERVING
    assert eng.permissions_changed({"can_observe": True, "can_block": False}) is False
    assert eng.permissions_changed({"can_observe": True, "can_block": True}) is True


def test_engine_notices_input_monitoring_granted_after_launch(tmp_path):
    eng, _, _ = engine(tmp_path)
    eng._running, eng.status = False, STATUS_NO_PERMISSION
    assert eng.permissions_changed({"can_observe": False, "can_block": False}) is False
    assert eng.permissions_changed({"can_observe": True, "can_block": False}) is True


def test_a_paused_engine_is_not_restarted_by_a_permission_check(tmp_path):
    eng, _, _ = engine(tmp_path)
    eng._running, eng.status = False, STATUS_PAUSED
    assert eng.permissions_changed({"can_observe": True, "can_block": True}) is False


# ------------------------------------------------------------ one event per plug-in

def test_attach_event_says_whether_the_keyboard_is_being_held(tmp_path):
    eng, events, present = engine(tmp_path)
    eng.keyboards.refresh()
    present.append(kb())
    eng.keyboards.refresh()
    attached = [e for e in events if e["event"] == "keyboard_attached" and not e["keyboard"]["built_in"]]
    assert attached and attached[-1]["held"] is True

    eng2, events2, present2 = engine(tmp_path / "b", hold_new_keyboards=False)
    eng2.keyboards.refresh()
    present2.append(kb())
    eng2.keyboards.refresh()
    attached = [e for e in events2 if e["event"] == "keyboard_attached" and not e["keyboard"]["built_in"]]
    assert attached and attached[-1]["held"] is False


# ------------------------------------------------------- trusting your own keyboards

def test_setup_trusts_only_keyboards_that_are_connected(tmp_path):
    mine = kb("Keychron K2", 0x05AC, 0x024F)
    eng, _, _ = engine(tmp_path, present=[BUILTIN, mine])
    eng.keyboards.refresh()
    assert eng.trust_connected([mine.key, "dead:beef:USB:Not Here"]) == 1
    assert eng.store.is_trusted(mine.key) and not eng.store.is_trusted("dead:beef:USB:Not Here")


# ------------------------------------------------------------- snapshot and the disk

def test_listing_incidents_twice_reads_the_disk_once(tmp_path, monkeypatch):
    store = Store(str(tmp_path))
    for i in range(3):
        store.save_incident({"id": f"2026111{i}-000000", "summary": "x"})
    assert len(store.list_incidents()) == 3
    loads = []
    real = json.load
    monkeypatch.setattr(json, "load", lambda f: loads.append(1) or real(f))
    assert len(store.list_incidents()) == 3
    assert not loads

    store.save_incident({"id": "20261120-000000", "summary": "y"})
    assert len(store.list_incidents()) == 4                      # a save is seen
    assert store.delete_incident("20261120-000000") and len(store.list_incidents()) == 3
    assert store.clear_incidents() == 3 and store.list_incidents() == []


def test_incident_list_is_a_copy_callers_cannot_corrupt(tmp_path):
    store = Store(str(tmp_path))
    store.save_incident({"id": "20261110-000000", "summary": "x"})
    store.list_incidents()[0]["summary"] = "changed"
    assert store.list_incidents()[0]["summary"] == "x"
