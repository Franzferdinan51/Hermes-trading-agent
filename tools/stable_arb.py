#!/usr/bin/env python3
"""Stablecoin arbitrage scanner for Jupiter.

Scans all liquid stablecoin pairs for synchronized two-way quotes
with positive net edge after all costs (slippage, priority fee, price impact).

Usage:
    python3 tools/stable_arb.py           # dry-run report
    python3 tools/stable_arb.py --execute # execute qualifying arbs
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

STABLES = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "USDS": "USDSwr9ApdHk5bvJKMjzff41FfuX8bSxdKcR81vYc",
    "PYUSD": "2b1kV6DkPAnYd7X1iM9iCHRZL5Zf1bSd5qK8xLkP",
    "EURC": "Eu2Wc9g6a7t4hY8k9X1iM9iCHRZL5Zf1bSd5qK8xLkP",
    "JL-USDC": "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D",
}

# Only pairs with real liquidity and quoted on Jupiter
PAIRS = [
    ("USDC", "USDT"),
    ("USDC", "USDS"),
    ("USDC", "PYUSD"),
    ("USDC", "EURC"),
    ("USDT", "USDS"),
    ("USDT", "PYUSD"),
    ("USDC", "JL-USDC"),  # earn receipt vs underlying
]

SOL_MINT = "So11111111111111111111111111111111111111112"
RPC = "https://api.mainnet-beta.solana.com"
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
DEFAULT_SLIPPAGE_BPS = 10
PRIORITY_FEE_SOL = 0.0001
MIN_EDGE_BPS = 5  # minimum net edge in basis points to consider
MAX_NOTIONAL_USD = 50.0
MAX_PRICE_IMPACT_PCT = 0.1  # stable-stable should be tiny


def _http_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _jupiter_quote(in_mint: str, out_mint: str, amount: int, slippage_bps: int) -> dict | None:
    q = urllib.parse.urlencode({
        "inputMint": in_mint,
        "outputMint": out_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "restrictIntermediateTokens": "true",
        "maxAccounts": "32",
    })
    try:
        return _http_json(f"{JUP_QUOTE}?{q}")
    except Exception:
        return None


def _rpc(method: str, params: list) -> dict | list:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("result", {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    return {}


def _wallet_balance(wallet: str, mint: str) -> int:
    if mint == SOL_MINT:
        bal = _rpc("getBalance", [wallet])
        return bal.get("value", 0) if isinstance(bal, dict) else 0
    raw = 0
    for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                 "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
        rows = _rpc("getTokenAccountsByOwner", [
            wallet, {"programId": prog}, {"encoding": "jsonParsed"}
        ])
        rows = rows.get("value", []) if isinstance(rows, dict) else rows
        for row in rows:
            if not isinstance(row, dict): continue
            acct = row.get("account", {})
            if not isinstance(acct, dict): continue
            data = acct.get("data", {})
            if not isinstance(data, dict): continue
            parsed = data.get("parsed")
            if not isinstance(parsed, dict): continue
            info = parsed.get("info", {})
            if info.get("mint") == mint:
                ta = info.get("tokenAmount", {})
                try:
                    raw += int(ta.get("amount", "0"))
                except (TypeError, ValueError):
                    pass
    return raw


def _simulate_arb(wallet: str, a: str, b: str, amount_a: int, slippage_bps: int) -> dict:
    """Simulate A->B->A round trip. Returns net edge in basis points."""
    m_a, m_b = STABLES[a], STABLES[b]

    # Leg 1: A -> B
    q1 = _jupiter_quote(m_a, m_b, amount_a, slippage_bps)
    if not q1: return {"ok": False, "reason": "no quote A->B"}
    out_b = int(q1["outAmount"])
    impact1 = float(q1.get("priceImpactPct", 0)) * 100

    # Leg 2: B -> A (use the exact output from leg 1)
    q2 = _jupiter_quote(m_b, m_a, out_b, slippage_bps)
    if not q2: return {"ok": False, "reason": "no quote B->A"}
    out_a = int(q2["outAmount"])
    impact2 = float(q2.get("priceImpactPct", 0)) * 100

    # Net result
    net_raw = out_a - amount_a
    if net_raw <= 0:
        return {"ok": False, "reason": f"negative round-trip: {net_raw}"}

    # Convert to bps
    dec_a = 6 if a != "JL-USDC" else 6  # JL-USDC is also 6 decimals
    net_bps = (net_raw / amount_a) * 10000

    # Estimate costs
    priority_fee_bps = (PRIORITY_FEE_SOL * 1e9 / amount_a) * 10000  # rough
    slippage_cost_bps = slippage_bps * 2  # both legs

    net_edge_bps = net_bps - slippage_cost_bps - priority_fee_bps

    return {
        "ok": net_edge_bps >= MIN_EDGE_BPS,
        "net_edge_bps": round(net_edge_bps, 2),
        "gross_edge_bps": round(net_bps, 2),
        "impact_pct": round(impact1 + impact2, 4),
        "amount_a": amount_a,
        "out_b": out_b,
        "out_a": out_a,
        "net_raw": net_raw,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--wallet", default="<YOUR_PRIVY_SOLANA_WALLET>")
    ap.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    ap.add_argument("--notional-usd", type=float, default=10000.0)
    args = ap.parse_args()

    print(f"STABLE ARB | mode={'EXEC' if args.execute else 'DRY'} | notional=${args.notional_usd:,.0f} | min_edge={MIN_EDGE_BPS}bps")

    # Fetch balances
    balances = {name: _wallet_balance(args.wallet, mint) for name, mint in STABLES.items()}
    print(f"Balances: " + ", ".join(f"{k}={v/1e6:.2f}" for k,v in balances.items() if v > 0))

    opportunities = []
    for a, b in PAIRS:
        bal_a = balances.get(a, 0)
        bal_b = balances.get(b, 0)
        if bal_a == 0 and bal_b == 0:
            continue

        # Use smaller of notional or available balance
        # For stable-stable, 1 unit ≈ $1, so notional ≈ amount in 6-dec units
        max_amount = min(args.notional_usd * 1e6, bal_a if bal_a > 0 else bal_b)
        if max_amount < 1000:  # less than $0.001
            continue

        result = _simulate_arb(args.wallet, a, b, int(max_amount), args.slippage_bps)
        if result.get("ok"):
            opportunities.append({
                "pair": f"{a}/{b}",
                "direction": f"{a}->{b}->{a}",
                "net_edge_bps": result["net_edge_bps"],
                "impact_pct": result["impact_pct"],
                "notional_usd": max_amount / 1e6,
            })
            print(f"  OPPORTUNITY: {a}/{b} | edge={result['net_edge_bps']:.1f}bps | impact={result['impact_pct']:.4f}% | notional=${max_amount/1e6:.0f}")
        else:
            print(f"  no edge: {a}/{b} ({result.get('reason', 'unknown')})")

    if not opportunities:
        print("No qualifying arbitrage opportunities.")
        return 0

    # Sort by edge descending
    opportunities.sort(key=lambda x: -x["net_edge_bps"])

    if args.execute:
        print("Execution not yet implemented for stable arb (requires dynamic allowlist for both mints).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())