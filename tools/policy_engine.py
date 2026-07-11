#!/usr/bin/env python3
"""Bounded execution guard for Privy/Jupiter jobs.

This module never signs or broadcasts. It provides the preflight gate and a
filesystem lock that an executor must call before and after a transaction.
"""
from __future__ import annotations
import argparse, json, math, os, time
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
LOCK = STATE / "trade.lock"
HALT = STATE / "EMERGENCY_STOP"
# Hard-coded safety floors (defense in depth). Per-trade notional cap and risk
# ratios are sourced from state/position_rules.json where the supervisor and
# risk manager can adjust them without redeploying code.
CAP_USD = 50.0                  # absolute USD ceiling per single trade (hard floor)
MAX_NOTIONAL_PCT = 0.25        # 25% of wallet NAV per trade (raised from 10% on owner request)
MAX_RISK_PCT = 0.01             # 1% of wallet NAV max loss per trade
MAX_DAILY_LOSS_PCT = 0.02       # 2% of wallet NAV daily realized loss cap
MAX_PRICE_IMPACT_PCT = 0.5      # 0.5% max price impact
MAX_SLIPPAGE_BPS = 100          # 100 bps max slippage
MAX_QUOTE_AGE_SECONDS = 20      # quote must be <20s old
ACTIVE_CAP_STATE_FILE = STATE / "position_rules.json"


def _state_override(name: str, default):
    """Pull a tunable from state/position_rules.json with safe fallback."""
    try:
        rules = json.loads(ACTIVE_CAP_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default
    value = rules.get("global", {}).get(name, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return value


def _active_cap_usd() -> float:
    """Pull the adaptive active cap from state/position_rules.json.

    Falls back to the hard-coded CAP_USD if the file is missing or the
    active cap is not a finite positive number.
    """
    return _state_override("active_cap_usd", CAP_USD)


def _max_notional_pct() -> float:
    return _state_override("max_notional_per_trade_pct", MAX_NOTIONAL_PCT)

class PolicyError(RuntimeError): pass

@contextmanager
def trade_lock(timeout=0):
    STATE.mkdir(parents=True, exist_ok=True)
    if HALT.exists(): raise PolicyError("emergency stop is active")
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, json.dumps({"pid":os.getpid(),"created":time.time()}).encode())
        os.close(fd)
    except FileExistsError:
        raise PolicyError("another wallet operation is active")
    try: yield
    finally:
        try: LOCK.unlink()
        except FileNotFoundError: pass

def preflight(*, wallet_value_usd, notional_usd, max_loss_usd, quote_age_s,
              price_impact_pct, slippage_bps, expected_out, min_out,
              current_fingerprint, before_fingerprint, daily_loss_usd=0):
    if HALT.exists(): raise PolicyError("emergency stop is active")
    numeric = {
        "wallet value": wallet_value_usd,
        "notional": notional_usd,
        "maximum loss": max_loss_usd,
        "daily loss": daily_loss_usd,
        "quote age": quote_age_s,
        "price impact": price_impact_pct,
        "slippage": slippage_bps,
    }
    for label, value in numeric.items():
        if not math.isfinite(float(value)): raise PolicyError(f"{label} must be finite")
    if wallet_value_usd <= 0: raise PolicyError("wallet value must be positive")
    if notional_usd <= 0: raise PolicyError("notional must be positive")
    if max_loss_usd < 0: raise PolicyError("maximum loss cannot be negative")
    if daily_loss_usd < 0: raise PolicyError("daily loss cannot be negative")
    if quote_age_s < 0: raise PolicyError("quote age cannot be negative")
    if price_impact_pct < 0: raise PolicyError("price impact cannot be negative")
    if slippage_bps < 0: raise PolicyError("slippage cannot be negative")
    if expected_out <= 0 or min_out <= 0: raise PolicyError("quote outputs must be positive")
    if notional_usd > _active_cap_usd(): raise PolicyError("notional exceeds active cap")
    if notional_usd > max(wallet_value_usd * _max_notional_pct(), 1.0):
        raise PolicyError("notional exceeds per-trade wallet limit")
    if max_loss_usd > wallet_value_usd * MAX_RISK_PCT:
        raise PolicyError("risk exceeds 1% wallet limit")
    if daily_loss_usd > wallet_value_usd * MAX_DAILY_LOSS_PCT:
        raise PolicyError("daily loss limit exceeded")
    if quote_age_s > MAX_QUOTE_AGE_SECONDS: raise PolicyError("quote is stale")
    if price_impact_pct > MAX_PRICE_IMPACT_PCT: raise PolicyError("price impact too high")
    if slippage_bps > MAX_SLIPPAGE_BPS: raise PolicyError("slippage too high")
    if expected_out < min_out: raise PolicyError("minimum output invalid")
    if before_fingerprint is not None and current_fingerprint != before_fingerprint:
        raise PolicyError("wallet state changed during preflight")
    return True

def halt(reason):
    STATE.mkdir(parents=True, exist_ok=True)
    HALT.write_text(json.dumps({"reason":reason,"time":time.time()}))

def resume():
    try: HALT.unlink()
    except FileNotFoundError: pass

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("halt").add_argument("reason")
    sub.add_parser("resume")
    s=sub.add_parser("status")
    a=sub.add_parser("preflight"); a.add_argument("--json",required=True)
    x=ap.parse_args()
    if x.cmd=="halt": halt(x.reason); print("halted")
    elif x.cmd=="resume": resume(); print("resumed")
    elif x.cmd=="status": print(json.dumps({"halt":HALT.exists(),"lock":LOCK.exists()}))
    else: print(json.dumps({"ok":preflight(**json.loads(x.json))}))
if __name__ == "__main__": main()
