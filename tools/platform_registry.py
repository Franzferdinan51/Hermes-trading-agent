#!/usr/bin/env python3
"""Cross-platform registry and read-only portfolio coordination checks.

This module never signs, broadcasts, bridges, withdraws, or changes platform
permissions. Platform-specific executors remain responsible for transactions.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "state" / "platforms.json"


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text())


def enabled_execution_platforms(registry: dict | None = None) -> list[str]:
    data = registry or load_registry()
    return [name for name, cfg in data["platforms"].items() if cfg.get("enabled_for_execution")]


def cross_management_snapshot(registry: dict | None = None) -> dict:
    data = registry or load_registry()
    return {
        "schema_version": data["schema_version"],
        "enabled_execution_platforms": enabled_execution_platforms(data),
        "platforms": {
            name: {
                "status": cfg.get("status"),
                "chain": cfg.get("chain"),
                "wallet": cfg.get("wallet"),
                "mode": cfg.get("mode"),
                "enabled_for_execution": cfg.get("enabled_for_execution", False),
                "native_fee_asset": cfg.get("native_fee_asset"),
            }
            for name, cfg in data["platforms"].items()
        },
        "global_policy": data["global_policy"],
    }


def main() -> int:
    print(json.dumps(cross_management_snapshot(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
