#!/usr/bin/env python3
"""
Jupiter Perps Executor - SOL/WBTC/ETH perpetuals via perps-api.jup.ag/v2

Compatible with our Privy/Solana wallet flow. Builds unsigned transactions
via the Jupiter API, then signs and broadcasts via the same executor path
used for spot swaps.

Endpoints used:
- POST /v2/positions/increase   — open position (returns serializedTxBase64)
- POST /v2/positions/decrease   — close/reduce position
- POST /v2/positions/close-all  — emergency close all
- POST /v2/execute              — broadcast signed tx (per CLI's postExecute)
- GET  /v2/positions            — list open positions
- GET  /v2/market-stats?mint=…  — current mark price for a market

Conservative defaults (per state/position_rules.json perps config):
- max_leverage: 3x
- max_position_pct_nav: 10%
- liquidation_buffer: 30%
- funding_threshold: 10% APR
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

JUPITER_PERPS_API = "https://perps-api.jup.ag/v2"

# The 3 markets Jupiter Perps supports as of 2026-07-13
JUPITER_PERPS_MINTS = {
    "SOL":  "So11111111111111111111111111111111111111112",
    "WBTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
    "ETH":  "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
}

# Reverse: mint → symbol
MINT_TO_SYMBOL = {v: k for k, v in JUPITER_PERPS_MINTS.items()}

WALLET = "<SOLANA_WALLET_ADDRESS>"

DEFAULT_SLIPPAGE_BPS = 200  # 2% perps slippage (Jupiter uses 200 bps for perps)


def perps_post(path: str, body: dict) -> dict:
    """POST to perps-api.jup.ag/v2/<path>."""
    url = f"{JUPITER_PERPS_API}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "HermesTradingAgent/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"Perps API error {e.code}: {err_body}")


def perps_get(path: str, params: Optional[dict] = None) -> dict:
    """GET perps-api.jup.ag/v2/<path>?<params>."""
    url = f"{JUPITER_PERPS_API}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HermesTradingAgent/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_positions(wallet: str = WALLET) -> list[dict]:
    """Get all open positions for a wallet."""
    data = perps_get("/positions", {"walletAddress": wallet})
    return data.get("dataList", [])


def get_market_price(mint: str) -> dict:
    """Get current market stats for a perp market."""
    return perps_get("/market-stats", {"mint": mint})


def request_increase_position(
    asset: str,            # "SOL", "WBTC", "ETH"
    side: str,             # "long" or "short"
    input_token: str,      # "USDC" (collateral)
    size_usd: float,
    leverage: float,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    wallet: str = WALLET,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> dict:
    """
    Build an unsigned transaction to open/increase a position.

    Returns the serialized transaction (base64) and position request pubkey
    that the user must sign. Use execute_signed_tx to broadcast.
    """
    if asset.upper() not in JUPITER_PERPS_MINTS:
        raise ValueError(f"Unsupported asset: {asset}. Must be one of {list(JUPITER_PERPS_MINTS)}")
    if side.lower() not in ("long", "short"):
        raise ValueError(f"Invalid side: {side}. Must be 'long' or 'short'.")
    if leverage <= 1.1 or leverage > 100:
        raise ValueError(f"Invalid leverage: {leverage}. Jupiter Perps requires leverage greater than 1.1x and no more than 100x.")

    # sizeUsdDelta is in micro-units (1e6)
    size_usd_delta = int(size_usd * 1_000_000)

    # inputTokenAmount is the collateral in token's smallest units
    # USDC has 6 decimals. For $5 USDC collateral: 5_000_000 (micro-USDC)
    collateral_amount = int(size_usd * 1_000_000)  # Assume USDC for now

    if size_usd < 10:
        raise ValueError(f"Minimum position size is $10 (Jupiter Perps requirement). Got ${size_usd}")

    body = {
        "asset": asset.upper(),
        "inputToken": input_token.upper(),
        "inputTokenAmount": str(collateral_amount),
        "side": side.lower(),
        "sizeUsdDelta": str(size_usd_delta),
        "leverage": str(leverage),
        "maxSlippageBps": str(slippage_bps),
        "walletAddress": wallet,
    }

    # Add TP/SL if provided (in micro-units)
    tpsl = []
    if tp_price is not None:
        tpsl.append({
            "receiveToken": input_token.upper(),
            "triggerPrice": str(int(tp_price * 1_000_000)),
            "requestType": "tp",
            "entirePosition": True,
        })
    if sl_price is not None:
        tpsl.append({
            "receiveToken": input_token.upper(),
            "triggerPrice": str(int(sl_price * 1_000_000)),
            "requestType": "sl",
            "entirePosition": True,
        })
    if tpsl:
        body["tpsl"] = tpsl

    return perps_post("/positions/increase", body)


def request_decrease_position(
    position_pubkey: str,
    receive_token: str = "USDC",
    size_usd: Optional[float] = None,
    entire_position: bool = True,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
) -> dict:
    """
    Build an unsigned transaction to close/reduce a position.

    If entire_position is True, closes the full position.
    Otherwise, size_usd specifies the amount to reduce.
    """
    body = {
        "positionPubkey": position_pubkey,
        "receiveToken": receive_token.upper(),
        "entirePosition": entire_position,
        "maxSlippageBps": str(slippage_bps),
    }
    if not entire_position and size_usd is not None:
        body["sizeUsdDelta"] = str(int(size_usd * 1_000_000))

    return perps_post("/positions/decrease", body)


def request_close_all(wallet: str = WALLET) -> dict:
    """Emergency close all positions."""
    return perps_post("/positions/close-all", {"walletAddress": wallet})


def execute_signed_tx(
    action: str,
    serialized_tx_base64: str,
    wallet: str = WALLET,
) -> dict:
    """
    Sign and broadcast a transaction via Privy + Solana RPC.

    Uses a two-step flow:
    1. Privy 'signTransaction' to sign the transaction (returns signed base64)
    2. Solana RPC 'sendTransaction' to broadcast it

    This matches the pattern in tools/privy_jupiter_executor.py for spot swaps.
    """
    import subprocess

    # Step 1: Sign via Privy (signTransaction only signs; we'll broadcast ourselves)
    sign_payload = json.dumps({
        "method": "signTransaction",
        "params": {
            "transaction": serialized_tx_base64,
            "encoding": "base64"
        }
    })

    cmd = [
        "pnpm", "--package=@privy-io/agent-wallet-cli",
        "dlx", "privy-agent-wallet", "rpc", "--json", sign_payload
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"Privy signTransaction failed: {proc.stderr.strip()}")

    parsed = json.loads(proc.stdout)

    # Extract signed transaction
    signed_tx_b64 = None
    if isinstance(parsed, dict):
        for key in ("signed_transaction", "signedTransaction", "transaction", "result", "data"):
            v = parsed.get(key)
            if isinstance(v, str):
                signed_tx_b64 = v
                break
            if isinstance(v, dict):
                for nested in ("signed_transaction", "signedTransaction", "transaction"):
                    if isinstance(v.get(nested), str):
                        signed_tx_b64 = v[nested]
                        break
                if signed_tx_b64:
                    break
            if isinstance(v, list) and len(v) > 0:
                first = v[0]
                if isinstance(first, dict) and isinstance(first.get("signedTransaction"), str):
                    signed_tx_b64 = first["signedTransaction"]
                    break

    if not signed_tx_b64:
        raise RuntimeError(f"Could not extract signed transaction. Response: {parsed}")

    # Safety validation before handing the partially signed transaction back to Jupiter.
    # Jupiter Perps transactions intentionally contain a Jupiter co-signer slot, so direct
    # Solana RPC broadcast always fails signature verification. The documented completion
    # path is POST /v2/transaction/execute, which supplies Jupiter's co-signature and sends.
    import base64
    from solders.message import to_bytes_versioned
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction

    vtx = VersionedTransaction.from_bytes(base64.b64decode(signed_tx_b64))
    required = vtx.message.header.num_required_signatures
    if required < 2:
        raise RuntimeError(f"Unexpected Jupiter Perps transaction: only {required} required signer(s)")
    payer = str(vtx.message.account_keys[0])
    if payer != wallet:
        raise RuntimeError(f"Refusing to execute: fee payer {payer} does not match wallet {wallet}")
    if not vtx.signatures[0].verify(Pubkey.from_string(wallet), to_bytes_versioned(vtx.message)):
        raise RuntimeError("Privy wallet signature verification failed")
    # A non-wallet co-signer slot is expected and must be completed by Jupiter's execute API.
    if str(vtx.signatures[1]) != "1111111111111111111111111111111111111111111111111111111111111111":
        raise RuntimeError("Unexpected co-signer state; refusing execution")

    # Step 2: Jupiter's documented executor completes the co-signature and broadcasts.
    api_action = {
        "open-position": "increase-position",
        "increase-position": "increase-position",
        "close-position": "decrease-position",
        "decrease-position": "decrease-position",
    }.get(action, action)
    if api_action not in {"increase-position", "decrease-position", "increase-position-with-fee", "decrease-position-with-fee"}:
        raise RuntimeError(f"Unsupported Jupiter execution action: {api_action}")
    execute_resp = perps_post("/transaction/execute", {
        "action": api_action,
        "serializedTxBase64": signed_tx_b64,
    })
    signature = execute_resp.get("signature") or execute_resp.get("txid") or execute_resp.get("transactionSignature")
    if not signature:
        raise RuntimeError(f"Jupiter execute returned no Solana signature: {execute_resp}")

    return {
        "action": api_action,
        "wallet": wallet,
        "signature": signature,
        "privy_response": parsed,
        "jupiter_execute_response": execute_resp,
    }


def open_position_dry_run(
    asset: str,
    side: str,
    size_usd: float,
    leverage: float,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    wallet: str = WALLET,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> dict:
    """
    Build an unsigned perp position transaction for review (no signing/broadcast).

    Returns the full API response including the serialized transaction.
    Use this for dry-run mode to inspect position details before signing.
    """
    result = request_increase_position(
        asset=asset,
        side=side,
        input_token="USDC",
        size_usd=size_usd,
        leverage=leverage,
        slippage_bps=slippage_bps,
        wallet=wallet,
        tp_price=tp_price,
        sl_price=sl_price,
    )

    # Result contains: positionPubkey, serializedTxBase64, quote, tpsl, txMetadata
    quote = result.get("quote", {})
    return {
        "mode": "dry_run",
        "asset": asset,
        "side": side,
        "size_usd": size_usd,
        "leverage": leverage,
        "slippage_bps": slippage_bps,
        "position_pubkey": result.get("positionPubkey"),
        "serialized_tx_base64": result.get("serializedTxBase64"),
        "quote": quote,
        "tx_metadata": result.get("txMetadata"),
        "tp_price": tp_price,
        "sl_price": sl_price,
        "wallet": wallet,
        "raw": result,
    }


# === CLI interface ===

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Jupiter Perps Executor (SOL/WBTC/ETH)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # open
    p_open = sub.add_parser("open", help="Open/increase a position (dry-run by default)")
    p_open.add_argument("--asset", required=True, choices=["SOL", "WBTC", "ETH"])
    p_open.add_argument("--side", required=True, choices=["long", "short"])
    p_open.add_argument("--size-usd", type=float, required=True, help="Position size in USD")
    p_open.add_argument("--leverage", type=float, required=True, help="Leverage multiplier (1-100)")
    p_open.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    p_open.add_argument("--tp", type=float, help="Take-profit price in USD")
    p_open.add_argument("--sl", type=float, help="Stop-loss price in USD")
    p_open.add_argument("--execute", action="store_true", help="Sign and broadcast via Privy (NOT just dry-run)")

    # execute-from-dry-run
    p_exec = sub.add_parser("execute", help="Sign and broadcast a previously built dry-run transaction")
    p_exec.add_argument("--serialized-tx", required=True, help="Base64 serialized transaction")
    p_exec.add_argument("--action", default="open-position", help="Action label")

    # close
    p_close = sub.add_parser("close", help="Close/reduce a position")
    p_close.add_argument("--position", required=True, help="Position pubkey")
    p_close.add_argument("--size-usd", type=float, help="USD to reduce (omit for full close)")
    p_close.add_argument("--receive", default="USDC")

    # close-all
    sub.add_parser("close-all", help="Emergency close all positions")

    # positions
    sub.add_parser("positions", help="List open positions")

    # markets
    sub.add_parser("markets", help="List market stats")

    args = parser.parse_args()

    if args.cmd == "open":
        result = open_position_dry_run(
            asset=args.asset,
            side=args.side,
            size_usd=args.size_usd,
            leverage=args.leverage,
            slippage_bps=args.slippage_bps,
            tp_price=args.tp,
            sl_price=args.sl,
        )
        # Print full result including serialized_tx_base64 for downstream execution
        print(json.dumps({
            "mode": result["mode"],
            "asset": result["asset"],
            "side": result["side"],
            "size_usd": result["size_usd"],
            "leverage": result["leverage"],
            "position_pubkey": result["position_pubkey"],
            "has_serialized_tx": bool(result["serialized_tx_base64"]),
            "serialized_tx_base64": result["serialized_tx_base64"],
            "quote": result["quote"],
            "tx_metadata": result.get("tx_metadata"),
        }, indent=2))
        if args.execute:
            # Sign and broadcast
            if not result["serialized_tx_base64"]:
                print("ERROR: no serialized tx to sign", file=sys.stderr)
                sys.exit(1)
            print("\n=== Signing and broadcasting via Privy ===", file=sys.stderr)
            exec_result = execute_signed_tx(
                action="open-position",
                serialized_tx_base64=result["serialized_tx_base64"],
                wallet=args.wallet if hasattr(args, 'wallet') else WALLET,
            )
            print(json.dumps(exec_result, indent=2))

    elif args.cmd == "execute":
        result = execute_signed_tx(
            action=args.action,
            serialized_tx_base64=args.serialized_tx,
        )
        print(json.dumps(result, indent=2))

    elif args.cmd == "close":
        result = request_decrease_position(
            position_pubkey=args.position,
            receive_token=args.receive,
            size_usd=args.size_usd,
            entire_position=args.size_usd is None,
        )
        print(json.dumps({
            "mode": "dry_run",
            "action": "close",
            "position": args.position,
            "serialized_tx_base64": result.get("serializedTxBase64"),
            "raw": result,
        }, indent=2))

    elif args.cmd == "close-all":
        result = request_close_all()
        print(json.dumps({
            "mode": "dry_run",
            "action": "close-all",
            "serialized_tx_base64": result.get("serializedTxBase64"),
            "raw": result,
        }, indent=2))

    elif args.cmd == "positions":
        positions = get_positions()
        print(f"Open positions: {len(positions)}")
        for p in positions:
            collateral = float(p.get('collateralUsd', 0)) / 1e6
            pnl = float(p.get('pnlAfterFeesUsd', 0)) / 1e6
            equity = collateral + pnl
            print(f"  {p.get('asset')}: {p.get('side')} {p.get('leverage')}x "
                  f"size=${float(p.get('sizeUsd', 0))/1e6:.2f} "
                  f"collateral=${collateral:.2f} equity=${equity:.2f} "
                  f"entry=${float(p.get('entryPriceUsd', 0))/1e6:.2f} "
                  f"mark=${float(p.get('markPriceUsd', 0))/1e6:.2f} "
                  f"liq=${float(p.get('liquidationPriceUsd', 0))/1e6:.2f} "
                  f"pnl=${pnl:.2f}")

    elif args.cmd == "markets":
        for symbol, mint in JUPITER_PERPS_MINTS.items():
            stats = get_market_price(mint)
            print(f"  {symbol} ({mint[:10]}...): "
                  f"${float(stats.get('price', 0)):.2f} "
                  f"24h: {float(stats.get('priceChange24H', 0)):.2f}% "
                  f"vol: ${float(stats.get('volume', 0))/1e6:.1f}M")


if __name__ == "__main__":
    main()