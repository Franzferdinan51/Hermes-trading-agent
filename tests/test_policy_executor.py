#!/usr/bin/env python3
"""Regression tests for the bounded Jupiter policy and executor helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from policy_engine import PolicyError, preflight  # noqa: E402
from privy_jupiter_executor import (  # noqa: E402
    ALLOWLIST,
    ALLOWLIST_INTENT,
    ANSEM,
    CBBTC,
    FEE_RESERVE_LAMPORTS,
    JUP,
    JUPSOL,
    SOL,
    SPECULATIVE_ALLOWLIST,
    USDC,
    asset_raw_balance,
    speculative_buy_allowed,
    speculative_exit_only,
    verify_post_trade,
)

BASE = dict(
    wallet_value_usd=64.80,
    notional_usd=3.90,
    max_loss_usd=0.50,
    quote_age_s=2,
    price_impact_pct=0.05,
    slippage_bps=75,
    expected_out=100,
    min_out=99,
    current_fingerprint="abc",
    before_fingerprint="abc",
)


def test_allowlist_pins_core_assets() -> None:
    expected = {SOL, USDC, JUP, CBBTC, JUPSOL, ANSEM}
    assert expected.issubset(ALLOWLIST), f"missing mints in allowlist: {expected - ALLOWLIST}"
    assert ALLOWLIST_INTENT[SOL] == "core"
    assert ALLOWLIST_INTENT[USDC] == "core"
    assert ALLOWLIST_INTENT[JUP] == "core"
    assert ALLOWLIST_INTENT[CBBTC] == "core"
    assert ALLOWLIST_INTENT[JUPSOL] == "core"


def test_speculative_intent_is_exit_only_by_default() -> None:
    assert ANSEM in SPECULATIVE_ALLOWLIST
    assert ALLOWLIST_INTENT[ANSEM] == "speculation_exit"
    assert speculative_exit_only(ANSEM) is True
    assert speculative_buy_allowed(ANSEM) is False


def test_preflight_rejects_invalid_wallet_value() -> None:
    with pytest.raises(PolicyError, match="wallet value"):
        preflight(**dict(BASE, wallet_value_usd=0))


def test_preflight_rejects_negative_amounts_and_loss() -> None:
    with pytest.raises(PolicyError, match="notional"):
        preflight(**dict(BASE, notional_usd=-1))
    with pytest.raises(PolicyError, match="maximum loss"):
        preflight(**dict(BASE, max_loss_usd=-1))


def test_raw_balance_supports_native_and_spl() -> None:
    snapshot = {
        "sol_lamports": 123,
        "token_raw_amounts": {USDC: 456},
        "tokens": {USDC: "0.000456"},
    }
    assert asset_raw_balance(snapshot, SOL) == 123
    assert asset_raw_balance(snapshot, USDC) == 456


def test_post_trade_requires_minimum_output_and_sol_reserve() -> None:
    before = {"sol_lamports": 100_000_000, "token_raw_amounts": {USDC: 0}, "tokens": {}}
    after = {
        "sol_lamports": FEE_RESERVE_LAMPORTS + 1,
        "token_raw_amounts": {USDC: 99},
        "tokens": {USDC: "0.000099"},
    }
    verify_post_trade(before, after, SOL, USDC, input_amount=10_000_000, minimum_out=99)

    with pytest.raises(PolicyError, match="minimum output"):
        verify_post_trade(before, dict(after, token_raw_amounts={USDC: 98}), SOL, USDC, 10_000_000, 99)

    with pytest.raises(PolicyError, match="fee reserve"):
        verify_post_trade(before, dict(after, sol_lamports=FEE_RESERVE_LAMPORTS - 1), SOL, USDC, 10_000_000, 99)