#!/usr/bin/env python3
"""
Wallet Poller - Solana/Jupiter edition
Every 30 min via Hermes cron
Reads Privy/Jupiter Solana wallet balances
Logs to wallet-poller.jsonl
Alerts on >5% balance change
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "logs" / "wallet-poller.jsonl"
LOG.parent.mkdir(exist_ok=True)

WALLET = "<SOLANA_WALLET_ADDRESS>"

# Solana token program IDs
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Tokens we care about
TRACKED_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",  # lowercase j
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
}


def rpc(method, params):
    req = urllib.request.Request(
        "https://api.mainnet-beta.solana.com",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return resp.get("result", {}).get("value")


def get_sol_balance():
    lamports = rpc("getBalance", [WALLET])
    return lamports / 1e9 if lamports is not None else 0


def get_all_token_balances():
    """Query by program ID, filter to tracked mints. More reliable than per-mint queries."""
    balances = {}

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
                    ui = info["tokenAmount"].get("uiAmount", 0) or 0
                    balances[label] = ui
        except Exception as e:
            print(f"WARN: program {program_id[:8]} query failed: {e}", file=sys.stderr)

    return balances


def poll_solana(quiet=False):
    """Poll Solana wallet"""
    timestamp = datetime.now(timezone.utc).isoformat()

    balances = get_all_token_balances()

    result = {
        "timestamp": timestamp,
        "chain": "solana",
        "wallet": WALLET,
        "balances": {
            "SOL": get_sol_balance(),
            "USDC": balances.get("USDC", 0),
            "JUP": balances.get("JUP", 0),
            "JupSOL": balances.get("JupSOL", 0),
            "cbBTC": balances.get("cbBTC", 0),
            "JL-USDC": balances.get("JL-USDC", 0),
        },
    }

    if not quiet:
        print(json.dumps(result, indent=2))

    return result


def check_delta(new_balances):
    """Compare against last log entry, alert on >5% delta"""
    if not LOG.exists():
        return None

    try:
        last_line = None
        with open(LOG, "r") as f:
            for line in f:
                last_line = line
        if not last_line:
            return None

        last = json.loads(last_line)
        deltas = {}

        for asset, new_val in new_balances["balances"].items():
            old_val = last.get("balances", {}).get(asset, 0)
            if old_val == 0:
                if new_val > 0:
                    deltas[asset] = "NEW"
                continue
            pct = ((new_val - old_val) / old_val) * 100
            if abs(pct) > 5:
                deltas[asset] = f"{pct:+.2f}%"

        return deltas if deltas else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", default="solana", choices=["solana"])
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    result = poll_solana(quiet=args.quiet)
    deltas = check_delta(result)

    record = {
        **result,
        "delta_alerts": deltas,
    }

    with open(LOG, "a") as f:
        f.write(json.dumps(record) + "\n")

    if deltas:
        print(f"\n⚠️  BALANCE DELTAS > 5%: {deltas}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"\nLogged to {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())