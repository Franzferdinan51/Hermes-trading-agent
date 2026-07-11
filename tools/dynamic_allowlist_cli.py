#!/usr/bin/env python3
"""CLI for the dynamic allowlist kill switch and inspection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_allowlist as dyn  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("halt").add_argument("reason")
    sub.add_parser("resume")
    sub.add_parser("status")
    sub.add_parser("list")
    sub.add_parser("purge-expired")
    p = sub.add_parser("show")
    p.add_argument("mint")

    args = ap.parse_args()
    if args.cmd == "halt":
        dyn.halt(args.reason)
        print(json.dumps({"halted": True, "reason": args.reason}))
    elif args.cmd == "resume":
        dyn.resume()
        print(json.dumps({"halted": False}))
    elif args.cmd == "status":
        print(json.dumps({"halted": dyn.is_halted(), "active_entries": len(dyn.read_entries())}, indent=2))
    elif args.cmd == "list":
        print(json.dumps(dyn.read_entries(), indent=2))
    elif args.cmd == "purge-expired":
        purged = dyn.purge_expired()
        print(json.dumps({"purged": purged}))
    elif args.cmd == "show":
        entry = dyn.entry_for(args.mint)
        print(json.dumps(entry if entry else {"mint": args.mint, "status": "missing_or_expired"}, indent=2))


if __name__ == "__main__":
    main()