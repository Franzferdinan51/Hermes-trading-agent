#!/usr/bin/env python3
"""Cross-platform portfolio wrapper.

Coordinates normalized platform state and MoA decisions. It never signs,
broadcasts, bridges, withdraws, or changes wallet permissions.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "state" / "platforms.json"
MODEL_ROUTING = ROOT / "state" / "model_routing.json"


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text())


def snapshot() -> dict:
    reg = load_registry()
    return {
        "schema_version": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_coordination",
        "execution_enabled_platforms": [
            name for name, cfg in reg["platforms"].items()
            if cfg.get("enabled_for_execution")
        ],
        "platforms": reg["platforms"],
        "global_policy": reg["global_policy"],
        "model_routing": json.loads(MODEL_ROUTING.read_text()),
        "shared_worker_pool": ["market", "portfolio", "protocol", "execution", "transfer"],
        "handoff": {
            "moa": "tools/moa_decision.py",
            "platform_registry": "state/platforms.json",
            "jupiter_executor": "tools/privy_jupiter_executor.py",
            "coinbase_executor": "npx awal trade",
            "robinhood_executor": "robinhood_trading_mcp",
            "tronlink_wallet_adapter": "pending_tronlink_adapter",
            "sunswap_executor": "pending_sunswap_adapter",
        },
    }


def evaluate(path: str) -> dict:
    payload = json.loads(Path(path).read_text())
    cmd = [sys.executable, str(ROOT / "tools" / "moa_decision.py"), path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    decision = json.loads(result.stdout)
    reg = load_registry()
    platform = payload.get("candidate", {}).get("platform_id")
    platform_cfg = reg["platforms"].get(platform, {})
    if not platform_cfg.get("enabled_for_execution", False):
        decision["decision"] = "HOLD"
        decision["reason"] = "platform execution is disabled or not registered"
    if platform == "sunswap_tron":
        wallet = reg["platforms"].get("tronlink_tron", {})
        if not wallet.get("enabled_for_execution", False) or wallet.get("status") != "active":
            decision["decision"] = "HOLD"
            decision["reason"] = "SunSwap requires an active verified TronLink wallet adapter"
    decision["platform_id"] = platform
    decision["platform_status"] = platform_cfg.get("status", "unknown")
    decision["execution_authority"] = platform_cfg.get("executor")
    return decision


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only cross-platform trading wrapper")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    e = sub.add_parser("evaluate")
    e.add_argument("candidate_json")
    args = ap.parse_args()
    output = snapshot() if args.command == "snapshot" else evaluate(args.candidate_json)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
