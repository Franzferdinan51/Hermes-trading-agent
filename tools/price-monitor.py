#!/usr/bin/env python3
"""
DuckBot price monitor — Osmosis-aware.

Monitors:
- OSMO (CoinGecko + on-chain pool 678 spot vs USDC)
- ATOM (CoinGecko)
- USDC peg (CoinGecko)
- BTC (CoinGecko)

Read-only. No broadcasting.

Cron mode: --cron or -c
Continuous mode: no flag
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

COINGECKO = "https://api.coingecko.com/api/v3"
OSMOSIS_LCD = "https://lcd.osmosis.zone"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "price-monitor.jsonl"

ALERT_THRESHOLDS = {
    "osmo": {"high": 0.06, "low": 0.025},
    "atom": {"high": 10.0, "low": 1.0},
    "usdc": {"high": 1.005, "low": 0.995},
    "btc": {"high": 100000.0, "low": 50000.0},
}

COINS = {"osmo": "osmosis", "atom": "cosmos", "usdc": "usd-coin", "btc": "bitcoin"}


def fetch_coingecko_prices() -> dict:
    ids = ",".join(COINS.values())
    r = requests.get(
        f"{COINGECKO}/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true",
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return {
        sym: {
            "usd": data.get(cg).get("usd"),
            "24h_change": data.get(cg).get("usd_24h_change"),
            "24h_vol": data.get(cg).get("usd_24h_vol"),
        }
        for sym, cg in COINS.items()
    }


def fetch_osmo_pool_spot() -> dict | None:
    r = requests.get(f"{OSMOSIS_LCD}/osmosis/gamm/v1beta1/pools/678", timeout=10)
    r.raise_for_status()
    p = r.json()["pool"]
    a0 = int(p["pool_assets"][0]["token"]["amount"])
    a1 = int(p["pool_assets"][1]["token"]["amount"])
    return {"pool_id": 678, "asset0": a0 / 1_000_000, "asset1": a1 / 1_000_000}


def log_line(line: dict) -> None:
    line["ts"] = datetime.now(timezone.utc).isoformat()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(line) + "\n")


def check():
    out = {"prices": {}, "alerts": [], "pool_spot": None}
    prices = fetch_coingecko_prices()
    for sym, p in prices.items():
        out["prices"][sym] = p
        if sym in ALERT_THRESHOLDS:
            t = ALERT_THRESHOLDS[sym]
            if p["usd"] is None:
                continue
            if p["usd"] >= t["high"]:
                out["alerts"].append(f"🚨 {sym.upper()} HIGH: ${p['usd']:.4f} (≥ ${t['high']})")
            elif p["usd"] <= t["low"]:
                out["alerts"].append(f"📉 {sym.upper()} LOW: ${p['usd']:.4f} (≤ ${t['low']})")
    try:
        pool = fetch_osmo_pool_spot()
        out["pool_spot"] = pool
    except Exception as e:
        out["pool_spot_error"] = str(e)
    log_line(out)
    return out


def print_report(out):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Price check")
    for sym, p in out["prices"].items():
        if p["usd"] is not None:
            chg = f"{p['24h_change']:+.1f}%" if p["24h_change"] is not None else "?"
            print(f"  {sym.upper():5} ${p['usd']:<10.4f}  24h={chg}")
    if out.get("pool_spot"):
        ps = out["pool_spot"]
        print(f"  pool 678 spot: {ps['asset0']:.2f} USDC <-> {ps['asset1']:.2f} OSMO")
    for a in out["alerts"]:
        print(f"  {a}")


def main():
    cron = "--cron" in sys.argv or "-c" in sys.argv
    if cron:
        out = check()
        print_report(out)
        sys.exit(1 if out["alerts"] else 0)
    print("📊 DuckBot price monitor (Osmosis-aware). Press Ctrl+C to stop.")
    while True:
        try:
            out = check()
            print_report(out)
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()