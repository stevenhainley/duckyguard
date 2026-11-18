"""The engine must hand each measured key hold to the detector exactly once."""

from pynput.keyboard import KeyCode

from duckyguard.engine import Engine
from duckyguard.store import Store


def make_engine(tmp_path):
    return Engine(store=Store(str(tmp_path)), enumerate_keyboards=lambda: [])


def press(eng, ch, ts):
    """What the tap callback does for one hardware key-down."""
    eng.holds.key_down(ch, ts)
    eng._pending = {"key": KeyCode.from_char(ch), "injected": False}
    return eng._score_pending(ts, dict(injected=False, repeat=False, pid=0, in_test=False))


def release(eng, ch, ts):
    eng.holds.key_up(ch, ts)


def test_instantly_released_keys_are_blocked_through_the_engine(tmp_path):
    eng, t, blocked_at = make_engine(tmp_path), 100.0, None
    for i, ch in enumerate("abcdefghij"):
        v = press(eng, ch, t)
        if v.block:
            blocked_at = i
            break
        release(eng, ch, t + 0.0015)
        t += 0.110
    assert blocked_at is not None and blocked_at <= 6
    assert str(v.features["rule"]).startswith("K")


def test_one_quick_tap_followed_by_rollover_typing_is_not_blocked(tmp_path):
    # A stale hold time must not be counted again for every later key.
    eng, t = make_engine(tmp_path), 100.0
    v = press(eng, "a", t)
    release(eng, "a", t + 0.001)                 # one instant release
    down = []
    for ch in "bcdefghijk":                      # each key goes down before the previous one is released
        t += 0.120
        v = press(eng, ch, t)
        assert not v.block, v.features.get("rule")
        if down:
            release(eng, down.pop(), t + 0.030)
        down.append(ch)
