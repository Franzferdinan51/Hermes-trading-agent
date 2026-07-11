#!/usr/bin/env python3
"""Update state/position_theses.json and state/position_rules.json after a deposit/withdraw."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THESES = ROOT / "state" / "position_theses.json"
RULES = ROOT / "state" / "position_rules.json"


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: sync_state.py <input_mint> <output_mint> <input_amount_raw> [observed_out_raw]")
        return 2
    in_mint, out_mint = sys.argv[1], sys.argv[2]
    in_amount = float(sys.argv[3])
    observed = float(sys.argv[4]) if len(sys.argv) > 4 else None

    theses = json.loads(THESES.read_text())
    positions = theses.setdefault("positions", {})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    in_label = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
                "So11111111111111111111111111111111111111112": "SOL",
                "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
                "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",
                "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
                "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
                "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump": "ANSEM"}.get(in_mint, in_mint)
    out_label = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
                 "So11111111111111111111111111111111111111112": "SOL",
                 "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
                 "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",
                 "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
                 "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
                 "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump": "ANSEM"}.get(out_mint, out_mint)

    observed_str = str(observed) if observed is not None else "(pending)"
    print(f"Recorded: {in_label} -{in_amount} -> {out_label} {observed_str}")
    theses["updated"] = now
    print(f"Theses updated: {now}")
    THESES.write_text(json.dumps(theses, indent=2) + "\n")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())