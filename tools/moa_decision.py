#!/usr/bin/env python3
"""Deterministic MoA vote gate for platform candidates.

Reference agents provide JSON votes; this module aggregates them without
calling models or signing transactions. The Hermes aggregator can use the
result as a hard input to its final platform-local decision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "state" / "moa_presets.json"
HARD_STOPS = {"balance_discrepancy", "stale_data", "unsupported_asset", "jurisdiction_block", "unknown_contract", "emergency_stop"}


def decide(candidate: dict, votes: list[dict], preset: str = "default") -> dict:
    cfg = json.loads(PRESETS.read_text())["presets"].get(preset)
    if cfg is None:
        raise ValueError(f"unknown preset: {preset}")
    stops = set(candidate.get("hard_stops", []))
    passed = [v for v in votes if v.get("decision") == "PASS" and not v.get("hard_stop")]
    failed = [v for v in votes if v.get("decision") != "PASS" or v.get("hard_stop")]
    confidences = [float(v.get("confidence", 0)) for v in votes]
    score = round(sum(confidences) / len(confidences) * 10, 2) if confidences else 0.0
    required = set(cfg["references"])
    present = {v.get("role") for v in votes}
    complete = required.issubset(present)
    approved = not stops & HARD_STOPS and complete and len(passed) >= cfg["min_pass_votes"] and score >= cfg["min_consensus_score"]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "preset": preset,
        "decision": "PASS" if approved else "HOLD",
        "consensus_score": score,
        "required_roles": sorted(required),
        "present_roles": sorted(r for r in present if r),
        "passed_roles": sorted([str(v["role"]) for v in passed if v.get("role")]),
        "failed_roles": sorted([str(v["role"]) for v in failed if v.get("role")]),
        "hard_stops": sorted(stops),
        "reason": "all required votes passed" if approved else "missing votes, insufficient consensus, failed vote, or hard stop",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="JSON file containing candidate, votes, and optional preset")
    args = ap.parse_args()
    payload = json.loads(Path(args.input).read_text())
    print(json.dumps(decide(payload["candidate"], payload["votes"], payload.get("preset", "default")), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
