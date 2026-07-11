#!/usr/bin/env python3
"""Append-only trade ledger.

Usage:
    python3 trade_ledger.py append --entry '{"ts":"...","thesis_id":"...","tx_hash":"...","balance_before":...,"balance_after":...,"verifiers_passed":3}'
    python3 trade_ledger.py list
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone

LEDGER_PATH = Path(__file__).resolve().parent.parent / "logs" / "trade_ledger.jsonl"


def append_entry(entry: dict) -> None:
    if not isinstance(entry, dict):
        raise ValueError("ledger entry must be an object")
    entry.setdefault("ts", datetime.now(timezone.utc).isoformat())
    entry.setdefault("status", "unknown")
    if entry.get("status") == "finalized" and not entry.get("tx_hash"):
        raise ValueError("finalized entry requires tx_hash")
    entry.setdefault("record_version", 2)
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    print(f"appended to {LEDGER_PATH}")


def list_entries() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    out = []
    with open(LEDGER_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("--entry", required=True, help="JSON object as string")
    a.add_argument("--file", help="Read JSON from file instead of --entry")
    l = sub.add_parser("list")
    l.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if args.cmd == "append":
        if args.file:
            entry = json.loads(Path(args.file).read_text())
        else:
            entry = json.loads(args.entry)
        append_entry(entry)
    elif args.cmd == "list":
        for e in list_entries()[-args.limit :]:
            print(json.dumps(e, indent=2, default=str))


if __name__ == "__main__":
    main()