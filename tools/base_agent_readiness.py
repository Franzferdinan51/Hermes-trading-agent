#!/usr/bin/env python3
"""Read-only Coinbase CDP/Base readiness check.

This tool never creates wallets, signs, broadcasts, bridges, or spends funds.
It verifies configuration and Base RPC reachability only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

BASE_CHAIN_ID = 8453
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
CDP_API_KEY_FILE = Path(os.getenv(
    "CDP_API_KEY_FILE",
    "<LOCAL_USER_HOME>/Documents/cdp_api_key (1).json",
))


def cdp_file_ready() -> bool:
    """Validate CDP key-file shape without printing secret material."""
    try:
        data = json.loads(CDP_API_KEY_FILE.read_text())
        return isinstance(data, dict) and bool(data.get("id")) and bool(data.get("privateKey"))
    except (OSError, ValueError, TypeError):
        return False


def rpc(method: str, params: list) -> dict:
    request = urllib.request.Request(
        BASE_RPC_URL,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Hermes-Base-Readiness/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def configured_base_address() -> str:
    """Return the explicit env address or the registered public Base wallet address."""
    explicit = os.getenv("BASE_AGENT_ADDRESS", "").strip()
    if explicit:
        return explicit
    for candidate in (
        Path(__file__).resolve().parents[1] / "state" / "platforms.json",
        Path("state/platforms.json"),
    ):
        try:
            data = json.loads(candidate.read_text())
            address = data.get("platforms", {}).get("coinbase_base", {}).get("wallet", "")
            if isinstance(address, str) and address.startswith("0x") and len(address) == 42:
                return address
        except (OSError, ValueError, TypeError):
            continue
    return ""


def main() -> int:
    present = {
        "CDP_API_KEY_FILE": cdp_file_ready(),
        "CDP_API_KEY_ID": bool(os.getenv("CDP_API_KEY_ID")),
        "CDP_API_KEY_SECRET": bool(os.getenv("CDP_API_KEY_SECRET")),
        "CDP_WALLET_SECRET": bool(os.getenv("CDP_WALLET_SECRET")),
        "BASE_AGENT_ADDRESS": bool(configured_base_address()),
    }
    print("Coinbase CDP/Base readiness")
    print("credentials_present:", present)
    print("transaction_capability: disabled by this checker")
    try:
        chain = rpc("eth_chainId", [])
        block = rpc("eth_blockNumber", [])
        chain_id = int(chain["result"], 16)
        print("rpc:", BASE_RPC_URL)
        print("chain_id:", chain_id)
        print("chain_ok:", chain_id == BASE_CHAIN_ID)
        print("latest_block:", int(block["result"], 16))
    except Exception as exc:
        print("rpc_error:", type(exc).__name__, str(exc))
        return 1
    print("next_step:", "configure CDP credentials and wallet policy" if not all(present.values()) else "review policy before enabling transactions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
