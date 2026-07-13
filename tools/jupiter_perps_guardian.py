#!/usr/bin/env python3
"""Silent Jupiter Perps position guardian.

Runs read-only. It writes nothing when all live positions have valid protection.
It emits an alert when Jupiter Perps data cannot be read, a position lacks a
full TP/SL, a trigger is within 0.75% of mark price, or liquidation safety is
below the configured 30% buffer.

It deliberately NEVER opens, modifies, or closes a trade. Existing TP/SL
orders remain the first-line on-chain protection.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from jupiter_perps_executor import get_positions  # noqa: E402

TRIGGER_ALERT_DISTANCE_PCT = 0.0075  # 0.75% from an on-chain TP/SL trigger
MIN_LIQUIDATION_BUFFER_PCT = 0.30    # 30% minimum adverse-move room


def usd(micros):
    return float(micros or 0) / 1_000_000


def main(report=False):
    try:
        positions = get_positions()
    except Exception as exc:
        print(f"🚨 JUPITER PERPS GUARDIAN ALERT\nCannot read open positions: {exc}")
        return 2

    alerts = []
    snapshots = []
    for p in positions:
        asset = p.get("asset", "UNKNOWN")
        side = str(p.get("side", "")).lower()
        mark = usd(p.get("markPriceUsd"))
        entry = usd(p.get("entryPriceUsd"))
        liquidation = usd(p.get("liquidationPriceUsd"))
        size = usd(p.get("sizeUsd"))
        pnl = usd(p.get("pnlAfterFeesUsd"))
        pubkey = p.get("positionPubkey", "unknown")
        tpsl = p.get("tpslRequests") or []
        tp = next((x for x in tpsl if x.get("requestType") == "tp" and x.get("sizePercentage") == "100.00"), None)
        sl = next((x for x in tpsl if x.get("requestType") == "sl" and x.get("sizePercentage") == "100.00"), None)

        missing = []
        if not tp:
            missing.append("full TP")
        if not sl:
            missing.append("full stop-loss")
        if missing:
            alerts.append(f"{asset} {side}: missing {', '.join(missing)} (position {pubkey})")
            continue

        tp_price = usd(tp.get("triggerPriceUsd"))
        sl_price = usd(sl.get("triggerPriceUsd"))
        if mark <= 0:
            alerts.append(f"{asset} {side}: invalid mark price from Jupiter")
            continue

        # For shorts, liquidation must be above mark; for longs, below mark.
        if side == "short":
            liq_buffer = (liquidation - mark) / mark
        elif side == "long":
            liq_buffer = (mark - liquidation) / mark
        else:
            alerts.append(f"{asset}: unknown side '{side}'")
            continue

        if liq_buffer < MIN_LIQUIDATION_BUFFER_PCT:
            alerts.append(f"{asset} {side}: liquidation buffer {liq_buffer:.1%} below 30% minimum")

        trigger_distance = min(abs(mark - tp_price), abs(mark - sl_price)) / mark
        snapshots.append({
            "asset": asset,
            "side": side,
            "position_pubkey": pubkey,
            "size_usd": round(size, 4),
            "entry_usd": round(entry, 6),
            "mark_usd": round(mark, 6),
            "pnl_usd": round(pnl, 6),
            "liquidation_usd": round(liquidation, 6),
            "liquidation_buffer_pct": round(liq_buffer * 100, 3),
            "tp_usd": round(tp_price, 6),
            "stop_usd": round(sl_price, 6),
            "nearest_trigger_distance_pct": round(trigger_distance * 100, 3),
            "full_tp": True,
            "full_stop": True,
        })
        if trigger_distance <= TRIGGER_ALERT_DISTANCE_PCT:
            alerts.append(
                f"{asset} {side}: mark ${mark:.2f} is {trigger_distance:.2%} from TP ${tp_price:.2f} or stop ${sl_price:.2f}; "
                f"size ${size:.2f}, P/L ${pnl:.2f}"
            )

    if alerts:
        print("🚨 JUPITER PERPS GUARDIAN ALERT")
        print("\n".join(f"• {a}" for a in alerts))
        return 1
    if report:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "healthy",
            "open_positions": len(positions),
            "positions": snapshots,
        }
        state_dir = ROOT / "state"
        state_dir.mkdir(exist_ok=True)
        (state_dir / "perps_monitor_latest.json").write_text(json.dumps(payload, indent=2) + "\n")
        lines = [
            "# Jupiter Perps Monitor State",
            "",
            f"Updated (UTC): {payload['generated_at']}",
            f"Status: {payload['status']}",
            f"Open positions: {payload['open_positions']}",
            "",
        ]
        for row in snapshots:
            lines.extend([
                f"## {row['asset']} {row['side'].upper()}",
                f"- Size: ${row['size_usd']:.2f}",
                f"- Entry / Mark: ${row['entry_usd']:.4f} / ${row['mark_usd']:.4f}",
                f"- P/L: ${row['pnl_usd']:.4f}",
                f"- TP / Stop: ${row['tp_usd']:.4f} / ${row['stop_usd']:.4f}",
                f"- Liquidation: ${row['liquidation_usd']:.4f} ({row['liquidation_buffer_pct']:.2f}% buffer)",
                f"- Nearest trigger distance: {row['nearest_trigger_distance_pct']:.3f}%",
                f"- Full TP / stop: {row['full_tp']} / {row['full_stop']}",
                "",
            ])
        (state_dir / "perps_monitor_latest.md").write_text("\n".join(lines))
        print(json.dumps(payload, indent=2))
    # Empty stdout means silent healthy run for no_agent cron jobs.
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only Jupiter Perps guardian")
    parser.add_argument("--report", action="store_true", help="emit healthy position state for an LLM monitor")
    args = parser.parse_args()
    raise SystemExit(main(report=args.report))
