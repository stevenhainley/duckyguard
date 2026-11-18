"""Protection features around the detector: holding new keyboards, impostor checks,
monitor-only mode, lock on block, secure-input reporting and keep-alive."""

import time

from duckyguard import launch_agent, permissions
from duckyguard.detector import Verdict
from duckyguard.devices import Keyboard, identity_flags
from duckyguard.engine import Engine
from duckyguard.store import Store


def kb(vid=0x1234, pid=0x5678, product="Mystery Keyboard", serial="", transport="USB", built_in=False, location=1):
    return Keyboard(key=f"{vid:04x}:{pid:04x}:{transport}:{product}", product=product, manufacturer="",
                    vendor_id=vid, product_id=pid, serial=serial, transport=transport, built_in=built_in,
                    location_id=location, first_seen=time.time())


BUILTIN = kb(0, 0, "Apple Internal Keyboard / Trackpad", transport="FIFO", built_in=True)


class Bench:
    """An engine wired to a keyboard list the test controls."""

    def __init__(self, tmp_path, present=None, trusted=(), **settings):
        self.present = list(present or [BUILTIN])
        self.events, self.locks, self.scans = [], 0, 0
        self.store = Store(str(tmp_path))
        for k, v in settings.items():
            self.store.set(k, v)
        for k in trusted:
            self.store.trust_device(k.key, k.as_dict())
        self.eng = Engine(store=self.store, on_event=self.events.append,
                          enumerate_keyboards=self._enumerate, lock_screen=self._lock)
        self.eng._can_block = True

    def _enumerate(self):
        self.scans += 1
        return list(self.present)

    def _lock(self):
        self.locks += 1

    def plug(self, k):
        self.present.append(k)
        self.eng.keyboards.refresh()

    def unplug(self, k):
        self.present.remove(k)
        self.eng.keyboards.refresh()

    def last(self, name):
        hits = [e for e in self.events if e["event"] == name]
        return hits[-1] if hits else None


# ------------------------------------------------------------- holding new keyboards

def test_new_untrusted_keyboard_is_held_and_its_keys_dropped(tmp_path):
    b = Bench(tmp_path)
    b.plug(kb())
    assert b.eng.hold_active()
    assert b.eng.should_drop_hardware(injected=False)
    started = b.last("hold_started")
    assert started and started["keyboard"]["product"] == "Mystery Keyboard"


def test_software_typed_keys_pass_during_a_hold(tmp_path):
    b = Bench(tmp_path)
    b.plug(kb())
    assert not b.eng.should_drop_hardware(injected=True)


def test_trusted_keyboard_is_not_held(tmp_path):
    k = kb(product="My Keychron")
    b = Bench(tmp_path, trusted=[k])
    b.plug(k)
    assert not b.eng.hold_active()


def test_hold_can_be_switched_off(tmp_path):
    b = Bench(tmp_path, hold_new_keyboards=False)
    b.plug(kb())
    assert not b.eng.hold_active()


def test_allow_ends_the_hold_and_trusts_the_keyboard(tmp_path):
    b, k = Bench(tmp_path), kb()
    b.plug(k)
    b.eng.allow_keyboard(k.key)
    assert not b.eng.hold_active() and not b.eng.should_drop_hardware(injected=False)
    assert b.store.is_trusted(k.key)
    assert b.last("hold_ended")["result"] == "allowed"


def test_allow_once_does_not_trust(tmp_path):
    b, k = Bench(tmp_path), kb()
    b.plug(k)
    b.eng.allow_keyboard(k.key, trust=False)
    assert not b.eng.hold_active() and not b.store.is_trusted(k.key)


def test_hold_expires_and_releases_the_keyboard(tmp_path):
    b = Bench(tmp_path, hold_seconds=20)
    b.plug(kb())
    assert b.eng.should_drop_hardware(injected=False, now=time.time() + 19)
    assert not b.eng.should_drop_hardware(injected=False, now=time.time() + 21)
    assert b.last("hold_ended")["result"] == "expired"


def test_away_mode_never_expires(tmp_path):
    b = Bench(tmp_path, hold_seconds=20, away_mode=True)
    b.plug(kb())
    assert b.eng.should_drop_hardware(injected=False, now=time.time() + 3600)


def test_blocked_keyboard_stays_held_until_it_is_unplugged(tmp_path):
    b, k = Bench(tmp_path, hold_seconds=20), kb()
    b.plug(k)
    b.eng.block_keyboard(k.key)
    assert b.eng.should_drop_hardware(injected=False, now=time.time() + 3600)
    b.unplug(k)
    assert not b.eng.hold_active()
    assert b.last("hold_ended")["result"] == "unplugged"


def test_hold_records_how_many_keys_it_dropped_but_not_which(tmp_path):
    b, k = Bench(tmp_path), kb()
    b.plug(k)
    for _ in range(7):
        b.eng.note_held_key()
    b.eng.block_keyboard(k.key)
    b.unplug(k)
    assert b.last("hold_ended")["dropped"] == 7
    inc = b.store.list_incidents()[0]
    assert inc["blocked_count"] == 7 and inc["blocked_text"] == "" and inc["prefix_text"] == ""
    assert "held" in inc["explanation"].lower()


def test_first_key_after_a_pause_rescans_keyboards_so_nothing_slips_through(tmp_path):
    b = Bench(tmp_path)
    b.present.append(kb())                        # plugged in, but the background poll has not run yet
    b.eng._last_scan = time.time() - 5
    b.eng.before_hardware_key(ts=1000.0, now=time.time())
    assert b.eng.hold_active()


def test_rescan_is_rate_limited(tmp_path):
    b = Bench(tmp_path)
    b.eng._last_scan = time.time() - 5
    before = b.scans
    now = time.time()
    b.eng.before_hardware_key(ts=1000.0, now=now)
    b.eng.before_hardware_key(ts=1001.0, now=now + .5)      # a new burst, but within a second of the last scan
    b.eng.before_hardware_key(ts=1001.05, now=now + .55)    # mid-burst
    assert b.scans == before + 1


# -------------------------------------------------------------------- impostor checks

def test_second_copy_of_a_trusted_keyboard_is_held_as_a_duplicate(tmp_path):
    mine = kb(0x05ac, 0x024f, "Keychron K2", serial="")
    b = Bench(tmp_path, present=[BUILTIN, mine], trusted=[mine])
    b.plug(kb(0x05ac, 0x024f, "Keychron K2", serial="", location=9))
    assert b.eng.hold_active()
    assert "duplicate" in b.last("keyboard_attached")["flags"]


def test_trusted_keyboard_with_a_different_serial_is_held(tmp_path):
    mine = kb(0x05ac, 0x024f, "Keychron K2", serial="A1B2")
    b = Bench(tmp_path, trusted=[mine])
    b.plug(kb(0x05ac, 0x024f, "Keychron K2", serial="ZZ99"))
    assert b.eng.hold_active()
    assert "serial changed" in b.last("keyboard_attached")["flags"]


def test_lookalike_of_a_trusted_model_is_flagged():
    mine = kb(0x05ac, 0x024f, "Keychron K2")
    fake = kb(0x05ac, 0x024f, "Keychron K2 ", transport="USB")
    assert "lookalike" in identity_flags(fake, [BUILTIN, mine], {mine.key: mine.as_dict()})
    assert identity_flags(kb(product="Something Else"), [BUILTIN, mine], {mine.key: mine.as_dict()}) == []


# ------------------------------------------------------- monitor-only and lock on block

def fake_block():
    return Verdict(True, 0.9, ["test"], {"burst_len": 7, "rule": "K: test"}, "machine", "blocked in a test")


def test_monitor_only_never_drops_or_holds(tmp_path):
    b = Bench(tmp_path, monitor_only=True)
    assert not b.eng.dropping()
    b.plug(kb())
    assert not b.eng.hold_active()
    assert not b.eng.should_drop_hardware(injected=False)


def test_lock_on_block_locks_the_screen_once(tmp_path):
    b = Bench(tmp_path, lock_on_block=True)
    b.eng._begin_quarantine(fake_block(), time.time(), simulated=False)
    assert b.locks == 1


def test_lock_on_block_ignores_the_safe_test_and_is_off_by_default(tmp_path):
    b = Bench(tmp_path, lock_on_block=True)
    b.eng._begin_quarantine(fake_block(), time.time(), simulated=True)
    assert b.locks == 0
    b2 = Bench(tmp_path / "second")
    b2.eng._begin_quarantine(fake_block(), time.time(), simulated=False)
    assert b2.locks == 0


# ------------------------------------------------------------ secure input, keep-alive

def test_secure_input_state_is_reported(tmp_path):
    assert permissions.secure_input_active() in (True, False)
    assert Bench(tmp_path).eng.snapshot()["secure_input"] in (True, False)


def test_keep_alive_relaunches_only_after_an_abnormal_exit():
    assert launch_agent.build_plist(keep_alive=True)["KeepAlive"] == {"SuccessfulExit": False}
    assert launch_agent.build_plist(keep_alive=False)["KeepAlive"] is False


def test_snapshot_lists_the_shields(tmp_path):
    shields = Bench(tmp_path).eng.snapshot()["shields"]
    assert {s["id"] for s in shields} >= {"timing", "hold_time", "keyboard_hold", "impostor", "monitor_only", "lock_on_block", "away_mode"}
    assert all(isinstance(s["on"], bool) and s["label"] for s in shields)
