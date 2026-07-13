#!/usr/bin/env python3
"""
Profit Sweep - Solana/Jupiter edition
Daily at 6 PM ET via Hermes cron
READ-ONLY: calculates profit-take allocation, logs recommendation
Never auto-executes — execution requires supervisor authorization
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = SETUP_DIR / "logs"
STATE_DIR = SETUP_DIR / "state"
LOG_DIR.mkdir(exist_ok=True)

WALLET = "<SOLANA_WALLET_ADDRESS>"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / "profit-sweep.log", "a") as f:
        f.write(line + "\n")

def get_price(coin_id):
    """Get USD price — try CoinGecko first, fall back to Jupiter quote"""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        if coin_id in resp and "usd" in resp[coin_id]:
            return float(resp[coin_id]["usd"])
    except Exception:
        pass

    # Fallback: derive from Jupiter quote
    try:
        if coin_id == "solana":
            url = "https://api.jup.ag/swap/v1/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6
        elif coin_id == "jupiter-2":
            url = "https://api.jup.ag/swap/v1/quote?inputMint=JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6 / 100
        elif coin_id == "coinbase-wrapped-btc":
            url = "https://api.jup.ag/swap/v1/quote?inputMint=cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6 / 0.01
    except Exception:
        pass
    return 0.0

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

TRACKED_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",  # lowercase j
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
}


def get_balances():
    """Fetch SOL + tokens via RPC. Query by program ID for reliability."""
    balances = {"SOL": 0, "USDC": 0, "JUP": 0, "JupSOL": 0, "cbBTC": 0, "JL-USDC": 0}

    # SOL
    try:
        req = urllib.request.Request(
            "https://api.mainnet-beta.solana.com",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [WALLET]}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        sol = json.loads(urllib.request.urlopen(req, timeout=15).read())["result"]["value"] / 1e9
        balances["SOL"] = sol
    except Exception:
        balances["SOL"] = 0

    # Query token accounts by program
    for program_id in [TOKEN_PROGRAM, TOKEN_2022_PROGRAM]:
        try:
            req = urllib.request.Request(
                "https://api.mainnet-beta.solana.com",
                data=json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [WALLET, {"programId": program_id}, {"encoding": "jsonParsed"}]
                }).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
            accounts = resp.get("result", {}).get("value", [])

            for account in accounts:
                info = account["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                if mint in TRACKED_MINTS:
                    label = TRACKED_MINTS[mint]
                    balances[label] = info["tokenAmount"].get("uiAmount", 0) or 0
        except Exception as e:
            log(f"WARN: program {program_id[:8]} query failed: {e}")

    return balances

def load_thesis():
    """Load position theses to compare against current"""
    try:
        return json.load(open(STATE_DIR / "position_theses.json"))
    except Exception:
        return {}

def main():
    log("=" * 50)
    log("PROFIT SWEEP CRON STARTED")
    log("=" * 50)
    log(f"Wallet: {WALLET}")

    # Current balances
    log("Fetching balances...")
    balances = get_balances()
    prices = {
        "SOL": get_price("solana"),
        "JUP": get_price("jupiter-2"),
        "cbBTC": get_price("coinbase-wrapped-btc"),
        "JupSOL": get_price("solana"),
    }

    # Calculate NAV
    nav = sum(balances.get(a, 0) * prices.get(a, 0) for a in ["SOL", "USDC", "JUP", "cbBTC", "JupSOL"])
    nav += balances.get("JL-USDC", 0)

    log(f"\n💰 PORTFOLIO NAV: ${nav:.2f}")
    for asset in ["SOL", "USDC", "JUP", "cbBTC", "JupSOL", "JL-USDC"]:
        bal = balances.get(asset, 0)
        val = bal * prices.get(asset, 1)
        log(f"   {asset}: {bal:.6f} = ${val:.2f}")

    # Thesis comparison
    log("\n📋 THESIS REVIEW:")
    thesis = load_thesis()
    holdings = thesis.get("holdings", {})

    actions = []
    for asset in ["JUP", "cbBTC", "SOL", "JupSOL"]:
        state = holdings.get(asset, {})
        target = state.get("target_usd")  # if defined
        invalidation = state.get("invalidation_usd")
        live_val = balances.get(asset, 0) * prices.get(asset, 0)

        if target and live_val >= target:
            actions.append(f"   🎯 {asset}: ${live_val:.2f} ≥ target ${target:.2f} → PROFIT-TAKE eligible")
        if invalidation and live_val <= invalidation:
            actions.append(f"   ⚠️ {asset}: ${live_val:.2f} ≤ invalidation ${invalidation:.2f} → EXIT")

    if not actions:
        actions.append("   No positions hit target or invalidation — HOLD")

    for a in actions:
        log(a)

    log("\n🎯 SWEEP RECOMMENDATION:")
    log("   This cron is READ-ONLY.")
    log("   Profit sweep candidates → WATCH until supervisor authorizes.")
    log("   Bucket policy: 50% USDC stable / 25% BTC / 25% reinvest")
    log("   Reserve: keep >= 0.02 SOL for fees")

    log("\nProfit sweep completed")
    log("-" * 50)

if __name__ == "__main__":
    main()