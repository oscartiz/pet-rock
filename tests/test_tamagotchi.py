"""Tests for tamagotchi state machine: decay, moods, feeding, ETH curve."""
import time

import pytest

import tamagotchi as tama


# --- mood thresholds ------------------------------------------------------

@pytest.mark.parametrize(
    "hunger,expected",
    [
        (100.0, "thriving"),
        (80.0,  "thriving"),
        (79.9,  "content"),
        (55.0,  "content"),
        (54.9,  "hungry"),
        (35.0,  "hungry"),
        (34.9,  "starving"),
        (15.0,  "starving"),
        (14.9,  "critical"),
        (0.0,   "critical"),
    ],
)
def test_mood_thresholds(hunger, expected):
    state = tama.State(hunger=hunger, last_decay_ts=0)
    assert tama.get_mood(state) == expected


# --- decay ----------------------------------------------------------------

def test_apply_decay_reduces_hunger_over_time():
    now = int(time.time())
    state = tama.State(hunger=80.0, last_decay_ts=now - 7200)  # 2 hours ago
    decayed = tama.apply_decay(state, decay_per_hour=3.0)
    assert decayed.hunger == pytest.approx(74.0, abs=0.01)
    assert decayed.last_decay_ts >= now


def test_apply_decay_clamps_at_zero():
    state = tama.State(hunger=5.0, last_decay_ts=int(time.time()) - 100 * 3600)
    decayed = tama.apply_decay(state, decay_per_hour=3.0)
    assert decayed.hunger == 0.0


def test_apply_decay_zero_elapsed_is_noop():
    now = int(time.time())
    state = tama.State(hunger=42.0, last_decay_ts=now)
    decayed = tama.apply_decay(state, decay_per_hour=3.0)
    assert decayed.hunger == pytest.approx(42.0, abs=0.1)


# --- feed signal detection ------------------------------------------------

@pytest.mark.parametrize(
    "text",
    ["!feed me", "!FOOD please", "hey !eat", "🍕", "🍔🍟", "have a 🍩 my friend"],
)
def test_has_feed_signal_positive(text):
    assert tama.has_feed_signal(text) is True


@pytest.mark.parametrize(
    "text",
    ["hello rock", "just saying hi", "feed someone else", "", "💎"],  # gem ≠ food
)
def test_has_feed_signal_negative(text):
    assert tama.has_feed_signal(text) is False


# --- ETH hunger gain ------------------------------------------------------

def test_eth_gain_dust_is_min():
    # 1 wei → essentially zero ETH → gain == ETH_GAIN_MIN
    assert tama.eth_hunger_gain(1) == pytest.approx(tama.ETH_GAIN_MIN, abs=0.01)


def test_eth_gain_huge_is_capped():
    # 1000 ETH → log10(1 + 1e5) ≈ 5 → 15 + 35*5 = 190 → clamped to 50
    assert tama.eth_hunger_gain(10**21) == tama.ETH_GAIN_MAX


def test_eth_gain_one_eth_is_capped_at_max():
    # 1 ETH → log10(101) ≈ 2.004 → 15 + 35*2.004 ≈ 85 → clamped to 50
    assert tama.eth_hunger_gain(10**18) == tama.ETH_GAIN_MAX


def test_eth_gain_monotonic():
    values = [10**15, 10**16, 10**17, 10**18]
    gains = [tama.eth_hunger_gain(v) for v in values]
    assert gains == sorted(gains)


def test_eth_gain_within_bounds():
    for wei in [0, 1, 10**12, 10**15, 10**17, 10**18, 10**24]:
        g = tama.eth_hunger_gain(wei)
        assert tama.ETH_GAIN_MIN <= g <= tama.ETH_GAIN_MAX


# --- social feed flow (touches DB) ----------------------------------------

def test_try_social_feed_first_attempt_accepted(fresh_db):
    state = tama.State(hunger=50.0, last_decay_ts=int(time.time()))
    new_state, ok = tama.try_social_feed(state, "did:plc:alice", "!feed")
    assert ok is True
    assert new_state.hunger == pytest.approx(60.0)


def test_try_social_feed_no_signal_rejected(fresh_db):
    state = tama.State(hunger=50.0, last_decay_ts=int(time.time()))
    new_state, ok = tama.try_social_feed(state, "did:plc:alice", "just saying hi")
    assert ok is False
    assert new_state.hunger == 50.0


def test_try_social_feed_cooldown_blocks_same_user(fresh_db):
    state = tama.State(hunger=50.0, last_decay_ts=int(time.time()))
    state, ok1 = tama.try_social_feed(state, "did:plc:alice", "🍕")
    assert ok1 is True
    state, ok2 = tama.try_social_feed(state, "did:plc:alice", "🍕")
    assert ok2 is False
    assert state.hunger == pytest.approx(60.0)  # unchanged after the rejected feed


def test_try_social_feed_different_users_both_accepted(fresh_db):
    state = tama.State(hunger=50.0, last_decay_ts=int(time.time()))
    state, ok1 = tama.try_social_feed(state, "did:plc:alice", "🍕")
    state, ok2 = tama.try_social_feed(state, "did:plc:bob", "🍔")
    assert ok1 is True and ok2 is True
    assert state.hunger == pytest.approx(70.0)


def test_try_social_feed_caps_at_100(fresh_db):
    state = tama.State(hunger=95.0, last_decay_ts=int(time.time()))
    state, ok = tama.try_social_feed(state, "did:plc:alice", "🍕")
    assert ok is True
    assert state.hunger == 100.0


# --- ETH feed application -------------------------------------------------

def test_apply_eth_feed_caps_at_100(fresh_db):
    state = tama.State(hunger=80.0, last_decay_ts=int(time.time()))
    new_state = tama.apply_eth_feed(state, "0xabc", 10**18)  # 1 ETH → +50 capped
    assert new_state.hunger == 100.0


def test_apply_eth_feed_logs_to_db(fresh_db):
    state = tama.State(hunger=50.0, last_decay_ts=int(time.time()))
    tama.apply_eth_feed(state, "0xabc", 10**15)
    assert fresh_db.recent_feed_count(3600) == 1
