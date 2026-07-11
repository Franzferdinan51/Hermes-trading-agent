#!/usr/bin/env python3
"""Compute transparent performance metrics from trade_ledger.jsonl.

The ledger includes historical drafts and attempted actions.  Counts therefore
separate finalized transactions from drafts, failed records, and entries with no
status instead of presenting all non-finalized records as one opaque bucket.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "logs" / "trade_ledger.jsonl"


def load() -> list[dict]:
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    rows.append({"status": "malformed_ledger_record"})
    return rows


def report() -> dict:
    rows = load()
    statuses = Counter(str(row.get("status", "missing_status")) for row in rows)
    finalized = [row for row in rows if row.get("status") == "finalized"]
    failures = [row for row in rows if str(row.get("status", "")).lower() in {"failed", "error", "reverted"}]
    drafts = [
        row for row in rows
        if "pending" in str(row.get("status", "")).lower()
        or str(row.get("status", "")).lower() == "draft"
    ]
    missing = [row for row in rows if row.get("status") is None]
    return {
        "records_total": len(rows),
        "status_counts": dict(sorted(statuses.items())),
        "finalized": len(finalized),
        "failed": len(failures),
        "draft_or_pending": len(drafts),
        "missing_status": len(missing),
        "finalized_txs": [row.get("tx_hash") for row in finalized if row.get("tx_hash")],
        "note": "P&L is not estimated unless a realized exit or mark-to-market field is recorded.",
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
