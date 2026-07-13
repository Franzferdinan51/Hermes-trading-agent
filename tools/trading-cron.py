#!/usr/bin/env python3
"""
DuckBot Trading Cron - Solana/Jupiter edition
Runs every 2 hours via Hermes cron
Evaluates current positions, runs research pass, logs recommendation
READ-ONLY by default; never auto-executes
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = SETUP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

WALLET = "<SOLANA_WALLET_ADDRESS>"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / "trading-cron.log", "a") as f:
        f.write(line + "\n")

def rpc_call(method, params):
    req = urllib.request.Request(
        "https://api.mainnet-beta.solana.com",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if "error" in resp:
        return None
    return resp.get("result", {}).get("value")

# Solana token program IDs
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Tracked mints
TRACKED_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",  # lowercase j
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
}


def get_balances():
    """Get SOL + token balances via RPC. Query by program ID for reliability."""
    balances = {"SOL": 0.0, "USDC": 0, "JUP": 0, "JupSOL": 0, "cbBTC": 0, "JL-USDC": 0}

    # SOL
    sol_lamports = rpc_call("getBalance", [WALLET])
    if sol_lamports is not None:
        balances["SOL"] = sol_lamports / 1e9

    # Query token accounts by program (more reliable than per-mint)
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
        # 1 SOL → USDC
        if coin_id == "solana":
            url = f"https://api.jup.ag/swap/v1/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6
        # 100 JUP → USDC
        elif coin_id == "jupiter-2":
            url = f"https://api.jup.ag/swap/v1/quote?inputMint=JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6 / 100
        # 0.01 cbBTC → USDC
        elif coin_id == "coinbase-wrapped-btc":
            url = f"https://api.jup.ag/swap/v1/quote?inputMint=cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000&slippageBps=50"
            resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
            if "outAmount" in resp:
                return float(resp["outAmount"]) / 1e6 / 0.01
    except Exception:
        pass
    return 0.0

def get_jupiter_quote(input_mint, output_mint, amount):
    """Get a Jupiter quote for a potential swap"""
    try:
        url = f"https://api.jup.ag/swap/v1/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps=50"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        return resp
    except Exception as e:
        return {"error": str(e)}

def main():
    log("=" * 50)
    log("DUCKBOT TRADING CRON STARTED")
    log("=" * 50)
    log(f"Wallet: {WALLET}")
    log(f"Workdir: {SETUP_DIR}")

    # Get balances
    log("Fetching on-chain balances...")
    balances = get_balances()

    # Get prices
    log("Fetching prices...")
    sol_price = get_price("solana")
    prices = {
        "SOL": sol_price,
        "JUP": get_price("jupiter-2"),
        "cbBTC": get_price("coinbase-wrapped-btc"),
        # JupSOL ≈ SOL * 1.1955 ratio (per DefiLlama pool)
        "JupSOL": sol_price * 1.1955 if sol_price else 0,
    }

    # Calculate NAV
    nav = sum(balances.get(asset, 0) * prices.get(asset, 0)
              for asset in ["SOL", "USDC", "JUP", "cbBTC", "JupSOL"])
    # JL-USDC valued at $1
    nav += balances.get("JL-USDC", 0)

    log("")
    log("💰 PORTFOLIO (live on-chain):")
    for asset in ["SOL", "USDC", "JUP", "JupSOL", "cbBTC", "JL-USDC"]:
        bal = balances.get(asset, 0)
        val = bal * prices.get(asset, 1)
        log(f"   {asset}: {bal:.6f} = ${val:.2f}")
    log(f"   TOTAL NAV: ${nav:.2f}")
    log("")

    # Check key thresholds
    sol_balance = balances.get("SOL", 0)
    fee_reserve_ok = sol_balance >= 0.02
    log(f"Fee reserve: {sol_balance:.6f} SOL {'✅ OK' if fee_reserve_ok else '❌ LOW'} (need >= 0.02)")

    usdc_balance = balances.get("USDC", 0)
    log(f"USDC dry powder: ${usdc_balance:.2f}")

    # Sample Jupiter quotes for context (not auto-executing)
    log("")
    log("📊 Sample Jupiter quotes (1 unit each):")
    sol_usdc = get_jupiter_quote(SOL_MINT, USDC_MINT, 1_000_000_000)
    if "outAmount" in sol_usdc:
        log(f"   1 SOL → USDC: ~${float(sol_usdc['outAmount']) / 1e6:.2f}")
    jup_usdc = get_jupiter_quote("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC_MINT, 100_000_000)
    if "outAmount" in jup_usdc:
        log(f"   100 JUP → USDC: ~${float(jup_usdc['outAmount']) / 1e6:.2f}")

    log("")
    log("🎯 RECOMMENDATION:")
    log("   This cron is READ-ONLY.")
    log("   For execution: see Autonomous Portfolio Execution Supervisor.")
    log("   Evidence: state/evidence/ + logs/")

    log("")
    log("Trading cron completed")
    log("-" * 50)

if __name__ == "__main__":
    main()