#!/usr/bin/env python3
"""Compact READ-ONLY Jupiter market collector.

Reads balances for one Solana wallet via Solana RPC (classic SPL + Token-2022),
fetches prices from CoinGecko (BTC/SOL/JUP/USDC) and Jupiter quote API for
yield-bearing tokens (JupSOL, JL-USDC, ANSEM), then appends a timestamped
JSON record to logs/price-monitor.jsonl and detailed evidence under
evidence/jupiter-market-<ts>.json.

NEVER signs or broadcasts transactions.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WALLET = "<SOLANA_WALLET_ADDRESS>"
RPC_URL = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")

MINTS = {
    "SOL":     "So11111111111111111111111111111111111111112",
    "USDC":    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "JUP":     "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "cbBTC":   "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",
    "JupSOL":  "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
    "JL-USDC": "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D",
    "ANSEM":   "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump",
}

TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SPL_TOKEN_PROGRAM  = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SYSTEM_PROGRAM     = "11111111111111111111111111111111"

COINGECKO_IDS = {
    "BTC":  "bitcoin",
    "SOL":  "solana",
    "JUP":  "jupiter-exchange-solana",
    "USDC": "usd-coin",
}

DECIMALS = {
    "SOL": 9, "USDC": 6, "JUP": 6, "cbBTC": 8,
    "JupSOL": 9, "JL-USDC": 6, "ANSEM": 6,
}

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "price-monitor.jsonl"
EVIDENCE_DIR = ROOT / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def http_json(url, method="GET", body=None, timeout=20):
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": "duckbot-collector/1.0"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        try:
            return r.status, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return r.status, raw.decode("utf-8", errors="replace")


def rpc(method, params):
    status, payload = http_json(
        RPC_URL, method="POST",
        body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=25,
    )
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"rpc {method} failed: status={status} body={str(payload)[:200]}")
    if "error" in payload:
        raise RuntimeError(f"rpc {method} error: {payload['error']}")
    return payload.get("result")


def prog_priority(p):
    return {"system": 3, "spl-token": 2, "token-2022": 1}.get(p, 0)


def fetch_balances(wallet):
    out = {}
    for prog_id, prog_label in [(TOKEN_2022_PROGRAM, "token-2022"),
                                (SPL_TOKEN_PROGRAM, "spl-token")]:
        try:
            res = rpc("getTokenAccountsByOwner", [
                wallet, {"programId": prog_id}, {"encoding": "jsonParsed"},
            ])
        except Exception as e:
            out.setdefault("__rpc_errors", {})[prog_label] = str(e)
            continue
        for acct in (res or {}).get("value", []):
            info = acct.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            mint = info.get("mint")
            if not mint:
                continue
            token_amt = info.get("tokenAmount", {})
            amount_raw = token_amt.get("amount", "0")
            amount_ui = token_amt.get("uiAmount", 0.0) or 0.0
            label = next((k for k, v in MINTS.items() if v == mint), None)
            if not label:
                continue
            out[f"{label}|{prog_label}"] = {
                "label": label, "mint": mint, "program": prog_label,
                "amount_raw": amount_raw, "amount_ui": amount_ui,
            }

    # Native SOL via getBalance
    try:
        balance_result = rpc("getBalance", [wallet])
        lamports = (balance_result or {}).get("value", 0) if isinstance(balance_result, dict) else (balance_result or 0)
        sol_ui = lamports / 1e9
        out["SOL|system"] = {
            "label": "SOL", "mint": MINTS["SOL"], "program": "system",
            "amount_raw": str(lamports), "amount_ui": sol_ui,
        }
    except Exception as e:
        out.setdefault("__rpc_errors", {})["sol_native"] = str(e)

    collapsed = {}
    for k, v in out.items():
        if not k.startswith("__") and "|" in k:
            lbl = v["label"]
            prev = collapsed.get(lbl)
            if prev is None or prog_priority(v["program"]) > prog_priority(prev["program"]):
                collapsed[lbl] = v
    return collapsed


def fetch_coingecko_prices():
    ids = ",".join(COINGECKO_IDS.values())
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
    )
    try:
        status, data = http_json(url, timeout=15)
        if status != 200 or not isinstance(data, dict):
            return {"__error": f"status {status}"}
        return {
            sym: {
                "usd": data.get(cg_id, {}).get("usd"),
                "24h_change": data.get(cg_id, {}).get("usd_24h_change"),
                "24h_vol": data.get(cg_id, {}).get("usd_24h_vol"),
            }
            for sym, cg_id in COINGECKO_IDS.items()
        }
    except Exception as e:
        return {"__error": str(e)}


def jupiter_quote(input_mint, output_mint, amount_ui):
    if amount_ui is None or amount_ui <= 0:
        return None
    label = next((k for k, v in MINTS.items() if v == input_mint), "")
    dec = DECIMALS.get(label, 6)
    amount_raw = int(round(amount_ui * (10 ** dec)))
    params = (
        f"inputMint={input_mint}&outputMint={output_mint}"
        f"&amount={amount_raw}&slippageBps=50&swapMode=ExactIn"
    )
    try:
        status, data = http_json(f"https://quote-api.jup.ag/v6/quote?{params}", timeout=12)
        if status != 200 or not isinstance(data, dict):
            return {"__error": f"status {status}"}
        return {
            "in_amount": data.get("inAmount"),
            "out_amount": data.get("outAmount"),
            "price_impact_pct": data.get("priceImpactPct"),
            "route_count": len(data.get("routePlan", [])),
        }
    except Exception as e:
        return {"__error": str(e)}


def fmt_price(v):
    if isinstance(v, (int, float)):
        if v >= 1000:
            return f"{v:,.0f}"
        if v >= 1:
            return f"{v:.2f}"
        return f"{v:.4f}"
    return "n/a"


def main():
    ts = datetime.now(timezone.utc).isoformat()
    started = time.time()

    record = {
        "ts": ts,
        "collector": "jupiter-market-collector",
        "wallet": WALLET,
        "mode": "read-only",
        "rpc": RPC_URL,
    }

    cg = fetch_coingecko_prices()
    record["coingecko"] = cg
    price_usd = {sym: (cg.get(sym) or {}).get("usd") for sym in COINGECKO_IDS}

    try:
        balances = fetch_balances(WALLET)
    except Exception as e:
        record["rpc_error"] = str(e)
        balances = {}
    record["balances"] = balances

    jupiter_quotes = {}
    usdc_mint = MINTS["USDC"]
    for label in ("JupSOL", "JL-USDC", "ANSEM"):
        bal_entry = balances.get(label)
        if not bal_entry:
            jupiter_quotes[label] = {"__note": "no wallet balance"}
            continue
        q = jupiter_quote(MINTS[label], usdc_mint, bal_entry["amount_ui"])
        jupiter_quotes[label] = {
            "balance_ui": bal_entry["amount_ui"],
            "program": bal_entry["program"],
            "quote": q,
        }
    record["jupiter_quotes"] = jupiter_quotes

    nav = 0.0
    holdings_usd = {}
    for label, bal in balances.items():
        if label not in price_usd or price_usd[label] in (None, 0):
            continue
        usd = (bal["amount_ui"] or 0.0) * (price_usd[label] or 0.0)
        holdings_usd[label] = usd
        nav += usd
    record["nav_usd"] = round(nav, 2)
    record["holdings_usd"] = {k: round(v, 4) for k, v in holdings_usd.items()}

    alerts = []
    if price_usd.get("USDC") is not None and isinstance(price_usd["USDC"], (int, float)):
        if not (0.995 <= price_usd["USDC"] <= 1.005):
            alerts.append(f"USDC peg deviates: ${price_usd['USDC']:.4f}")
    record["alerts"] = alerts

    record["duration_s"] = round(time.time() - started, 3)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    evidence_path = EVIDENCE_DIR / f"jupiter-market-{ts.replace(':', '-')}.json"
    with open(evidence_path, "w") as f:
        json.dump(record, f, indent=2, default=str)

    b = lambda lbl, default=0.0: balances.get(lbl, {}).get("amount_ui", default)

    print(f"MARKET | BTC ${fmt_price(price_usd.get('BTC'))} | SOL ${fmt_price(price_usd.get('SOL'))} | JUP ${fmt_price(price_usd.get('JUP'))} | USDC ${fmt_price(price_usd.get('USDC'))}")
    print(f"WALLET | SOL {b('SOL'):.6f} | USDC {b('USDC'):.6f} | JUP {b('JUP'):.6f} | cbBTC {b('cbBTC'):.8f}")
    print(f"YIELD TOKENS | JL-USDC {b('JL-USDC'):.6f} | JupSOL {b('JupSOL'):.9f} | ANSEM {b('ANSEM'):.6f}")
    print(f"ALERTS | {('none' if not alerts else alerts[0])}")
    status = "ERROR" if record.get("rpc_error") or cg.get("__error") else "OK"
    print(f"STATUS | {status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
