#!/usr/bin/env python3
"""Isolated smoke test for the bounded policy guard; never touches production state."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import policy_engine as policy  # noqa: E402

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


def check(condition: bool, label: str) -> None:
    print(("PASS" if condition else "FAIL"), label)
    if not condition:
        raise SystemExit(1)


def rejected(changes: dict, label: str) -> None:
    try:
        policy.preflight(**dict(BASE, **changes))
    except Exception:
        check(True, label)
    else:
        check(False, label)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="policy-guard-test-") as tmp:
        state = Path(tmp)
        policy.STATE = state
        policy.HALT = state / "EMERGENCY_STOP"
        policy.LOCK = state / "trade.lock"

        check(policy.preflight(**BASE), "preflight accepts a within-bounds trade")
        rejected({"quote_age_s": 120}, "stale quote rejected")
        rejected({"notional_usd": 1000}, "over-cap notional rejected")
        rejected({"before_fingerprint": "xyz"}, "fingerprint mismatch rejected")
        rejected({"notional_usd": float("nan")}, "NaN notional rejected")
        rejected({"slippage_bps": -1}, "negative slippage rejected")

        with policy.trade_lock():
            try:
                with policy.trade_lock():
                    check(False, "second trade_lock must be rejected")
            except Exception:
                check(True, "concurrent trade_lock rejected")

        policy.halt("smoke test")
        try:
            with policy.trade_lock():
                check(False, "HALT must block trade_lock")
        except Exception:
            check(True, "HALT blocks trade_lock")
        rejected({}, "HALT blocks preflight")
        policy.resume()
        check(policy.preflight(**BASE), "after resume, preflight accepts again")

    print("\nALL ISOLATED POLICY-GUARD SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
