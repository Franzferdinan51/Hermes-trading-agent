#!/usr/bin/env python3
"""Append and read a durable, tagged cross-cron handoff ledger.

Designed for the crypto-trading-setup cron workdir. Each append produces both
an audit-friendly Markdown section and a machine-readable JSONL row under
state/. File locking prevents concurrent cron jobs from interleaving writes.
"""
import argparse
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
MARKDOWN = STATE / "cron_handoff.md"
JSONL = STATE / "cron_handoff.jsonl"


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean(text: str) -> str:
    return " ".join((text or "").split())


def append_entry(job: str, tag: str, status: str, summary: str, details: str, facts: str):
    ts = iso_now()
    try:
        facts_obj = json.loads(facts) if facts else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--facts must be valid JSON: {exc}")
    entry = {
        "timestamp_utc": ts,
        "job": clean(job),
        "tag": clean(tag).upper(),
        "status": clean(status).upper(),
        "summary": clean(summary),
        "details": clean(details),
        "facts": facts_obj,
    }
    STATE.mkdir(exist_ok=True)
    with JSONL.open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    facts_md = json.dumps(facts_obj, sort_keys=True) if facts_obj else "{}"
    block = (
        f"\n## [{entry['tag']}] {entry['job']} — {entry['timestamp_utc']}\n\n"
        f"- **Status:** {entry['status']}\n"
        f"- **Summary:** {entry['summary']}\n"
        f"- **Details:** {entry['details']}\n"
        f"- **Facts:** `{facts_md}`\n"
    )
    with MARKDOWN.open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        if fh.tell() == 0:
            fh.write("# Cron Shared Handoff Ledger\n\n")
            fh.write("> Append-only, UTC-dated operational state shared by trading crons. "
                     "Read recent entries before a material decision; append a tagged result after each cycle.\n")
        fh.write(block)
        fh.flush()
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    print(json.dumps(entry, indent=2))


def read_entries(limit: int):
    if not MARKDOWN.exists():
        print("# Cron Shared Handoff Ledger\n\nNo entries yet.")
        return
    lines = MARKDOWN.read_text().splitlines()
    headings = [i for i, line in enumerate(lines) if line.startswith("## [")]
    start = headings[-limit] if len(headings) > limit else 0
    print("\n".join(lines[start:]))


def main():
    parser = argparse.ArgumentParser(description="Cross-cron handoff ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    app = sub.add_parser("append")
    app.add_argument("--job", required=True)
    app.add_argument("--tag", required=True, help="e.g. PERPS, RISK, MARKET, NEWS, RECONCILIATION")
    app.add_argument("--status", required=True, help="e.g. OK, WATCH, ALERT, ACTION, HOLD")
    app.add_argument("--summary", required=True)
    app.add_argument("--details", default="")
    app.add_argument("--facts", default="{}", help="Valid one-line JSON object")
    read = sub.add_parser("read")
    read.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    if args.command == "append":
        append_entry(args.job, args.tag, args.status, args.summary, args.details, args.facts)
    else:
        read_entries(args.limit)


if __name__ == "__main__":
    main()
