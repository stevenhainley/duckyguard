"""Property tests for timing edge cases (hypothesis)."""

from hypothesis import given, settings, strategies as st

from duckyguard.detector import KeyEvent, KeystrokeAnomalyDetector


@settings(max_examples=300, deadline=None)
@given(st.lists(st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False), min_size=1, max_size=80))
def test_never_raises_and_features_are_finite(gaps):
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for g in gaps:
        t += g
        v = det.observe(KeyEvent(timestamp=t, char="a"))
        for k, val in v.features.items():
            if isinstance(val, float):
                assert val == val and abs(val) != float("inf")
        assert 0.0 <= v.score <= 1.0


@settings(max_examples=200, deadline=None)
@given(st.floats(min_value=0.004, max_value=0.060), st.integers(min_value=12, max_value=60))
def test_any_even_fast_spacing_is_blocked(gap, n):
    det = KeystrokeAnomalyDetector()
    t = 0.0
    blocked = False
    for _ in range(n):
        if det.observe(KeyEvent(timestamp=t, char="a")).block:
            blocked = True
            break
        t += gap
    assert blocked


@settings(max_examples=200, deadline=None)
@given(st.lists(st.floats(min_value=0.15, max_value=0.6), min_size=1, max_size=60))
def test_normal_human_gaps_never_blocked(gaps):
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for g in gaps:
        t += g
        assert not det.observe(KeyEvent(timestamp=t, char="a", hold_time=0.09)).block


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=7), st.floats(min_value=0.005, max_value=0.03))
def test_short_fast_bursts_separated_by_pauses_never_blocked(burst_len, gap):
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for _ in range(10):
        for _ in range(burst_len):
            assert not det.observe(KeyEvent(timestamp=t, char="a")).block
            t += gap
        t += 1.0


@settings(max_examples=100, deadline=None)
@given(st.lists(st.floats(min_value=0.0, max_value=0.1), min_size=5, max_size=60))
def test_block_always_has_reasons_and_explanation(gaps):
    det = KeystrokeAnomalyDetector()
    t = 0.0
    for g in gaps:
        t += g
        v = det.observe(KeyEvent(timestamp=t, char="a"))
        if v.block:
            assert v.reasons
            assert "blocked" in v.explanation
            assert v.features.get("rule")
