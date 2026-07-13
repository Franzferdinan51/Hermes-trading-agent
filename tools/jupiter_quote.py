#!/usr/bin/env python3
"""Jupiter quote helper. Usage: python3 jupiter_quote.py SOL USDC 1000000000"""
from __future__ import annotations
import json, os, subprocess, urllib.parse, urllib.request

SERVICE = "jupiter-api-key"
BASE = "https://api.jup.ag"

def api_key() -> str:
    env = os.environ.get("JUPITER_API_KEY")
    if env:
        return env
    p = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", SERVICE, "-w"],
        capture_output=True, text=True, check=True,
    )
    return p.stdout.strip()

def get(path: str, params: dict | None = None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "x-api-key": api_key(),
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, json.loads(r.read().decode())

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Jupiter quote tool")
    ap.add_argument("input_mint", help="Input token mint (e.g. SOL, USDC or full mint address)")
    ap.add_argument("output_mint", help="Output token mint")
    ap.add_argument("amount", type=int, help="Amount in smallest unit (lamports for SOL, micro-USDC for USDC)")
    ap.add_argument("--slippage-bps", type=int, default=50, help="Slippage in bps (default 50)")
    ap.add_argument("--only-direct-routes", action="store_true", help="Only direct routes")
    args = ap.parse_args()

    # Resolve token symbols to mints
    MINT_MAP = {
        "SOL": "So11111111111111111111111111111111111111112",
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "WETH": "7vfCXTUXx5WJV5JADk17DU5MGAAD7t7hkU9HpiDss1e",
        "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "CBBTC": "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",
        "JL-USDC": "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D",
        "JUPSOL": "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
    }
    inp = MINT_MAP.get(args.input_mint.upper(), args.input_mint)
    out = MINT_MAP.get(args.output_mint.upper(), args.output_mint)

    params = {
        "inputMint": inp,
        "outputMint": out,
        "amount": args.amount,
        "slippageBps": args.slippage_bps,
        "onlyDirectRoutes": str(args.only_direct_routes).lower(),
        "automaticSlippage": "true",
    }
    status, data = get("/swap/v1/quote", params)
    out_summary = {
        "status": status,
        "inputMint": inp,
        "outputMint": out,
        "amount": args.amount,
        "inAmount": data.get("inAmount", "?"),
        "outAmount": data.get("outAmount", "?"),
        "otherAmountThreshold": data.get("otherAmountThreshold", "?"),
        "priceImpactPct": data.get("priceImpactPct", "?"),
        "swapMode": data.get("swapMode", "?"),
        "routePlan": [
            {"label": r.get("swapInfo", {}).get("label"),
             "inputMint": r.get("swapInfo", {}).get("inputMint"),
             "outputMint": r.get("swapInfo", {}).get("outputMint"),
             "inAmount": r.get("swapInfo", {}).get("inAmount"),
             "outAmount": r.get("swapInfo", {}).get("outAmount"),
             "percent": r.get("percent")}
            for r in data.get("routePlan", []) if r.get("swapInfo")
        ],
        "error": data.get("error", None) or (None if status == 200 else f"HTTP {status}"),
    }
    print(json.dumps(out_summary, indent=2))
