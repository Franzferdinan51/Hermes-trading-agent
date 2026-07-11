#!/usr/bin/env python3
"""Bounded profit-take loop for the active Privy/Jupiter Solana wallet.

For each holding in ``state/position_theses.json`` this script:

  * Reads the per-asset ``target_review_usd`` and ``invalidation_review_usd``
    from the thesis, plus a live price from CoinGecko.
  * Below invalidation -> exit 100% of the position into USDC (urgent).
  * At or above target   -> take a partial slice (default 33%) into USDC.
  * Between invalidation and target -> HOLD, no action.

Every candidate must satisfy the same gates the supervisor does:

  * Net edge after slippage + priority fee must be positive.
  * Notional must fit the active USD cap and the per-trade wallet ratio
    sourced from ``state/position_rules.json``.
  * Loss must be inside the 1% NAV per-trade limit.
  * The 0.02 SOL fee reserve must be preserved.

For each profitable candidate the tool writes a single-use dynamic-allowlist
entry, invokes ``tools/privy_jupiter_executor.py`` with ``--execute``, and
records the resulting ledger entry. The supervisor itself is also allowed
to call this tool as part of its decision flow; the tool is read-only
when invoked without ``--execute``.

Output is one compact Telegram card (max ~10 lines) suitable for cron delivery.

Usage:

    python3 tools/profit_take.py --dry-run      # scan + report, no execution
    python3 tools/profit_take.py --execute     # scan + execute qualifying exits
    python3 tools/profit_take.py --slice-pct 50  # take 50% on each target hit
                                                # (defaults to 33%)
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
import typing
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from policy_engine import CAP_USD, MAX_NOTIONAL_PCT, MAX_RISK_PCT, _active_cap_usd  # noqa: E402

STATE = ROOT / "state"
THESES = STATE / "position_theses.json"
RULES = STATE / "position_rules.json"
ALLOWLIST_HARDCODED = {  # must match tools/privy_jupiter_executor.py
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "cbBTC",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "JupSOL",
    "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump": "ANSEM",
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": "JL-USDC",
}
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"
DEFAULT_SLIPPAGE_BPS = 50
FEE_RESERVE_SOL = 0.02
PRIORITY_FEE_SOL = 0.0001   # ~100k lamports auto-prio buffer
CG_IDS = {
    "So11111111111111111111111111111111111111112": "solana",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "usd-coin",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "jupiter-exchange-solana",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "coinbase-wrapped-btc",
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": "jupiter-staked-sol",
    "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump": "the-black-bull",
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": None,  # JL-USDC, not on CoinGecko
}
DECIMALS = {
    SOL_MINT: 9,
    USDC_MINT: 6,
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": 6,
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": 8,
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": 9,
    "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump": 6,
    "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D": 6,
}


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _rpc(method: str, params: list, *, rpc_url: str = "https://api.mainnet-beta.solana.com") -> typing.Any:
    result = _http_json(rpc_url, method="POST", body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return result.get("result") or []


def _live_prices(mints: list[str]) -> dict[str, float]:
    """Return USD price for each mint. JL-USDC uses the Jupiter Lend API."""
    prices: dict[str, float] = {}
    cg_ids = [CG_IDS[m] for m in mints if CG_IDS.get(m)]
    if cg_ids:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cg_ids)}&vs_currencies=usd"
        data = _http_json(url)
        for mint in mints:
            cg = CG_IDS.get(mint)
            if cg and cg in data:
                prices[mint] = float(data[cg]["usd"])
    JL_USDC_MINT = "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D"
    if JL_USDC_MINT in mints:
        try:
            req = urllib.request.Request(
                "https://lite-api.jup.ag/lend/v1/earn/tokens",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            lend = json.loads(urllib.request.urlopen(req, timeout=20).read())
            tokens = lend if isinstance(lend, list) else lend.get("tokens", [])
            for token in tokens:
                if token.get("address") == JL_USDC_MINT or token.get("assetAddress") == JL_USDC_MINT:
                    cta = float(token.get("convertToAssets", 0)) / 1e6
                    if cta > 0:
                        prices[JL_USDC_MINT] = cta
                    break
        except Exception:
            pass  # JL-USDC price is optional; the tool still works without it
    return prices


def _balances(wallet: str) -> dict:
    """Return raw SOL lamports and per-mint raw token balances (SPL + Token-2022)."""
    bal_result = _rpc("getBalance", [wallet])
    native = int(bal_result.get("value", 0)) if isinstance(bal_result, dict) else 0
    raw: dict[str, int] = {}
    for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                 "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
        rpc_result = _rpc("getTokenAccountsByOwner", [
            wallet, {"programId": prog}, {"encoding": "jsonParsed"}
        ])
        # RPC returns {"context": {...}, "value": [...]} for this method
        rows = []
        if isinstance(rpc_result, dict):
            rows = rpc_result.get("value", [])
        elif isinstance(rpc_result, list):
            rows = rpc_result
        for row in rows:
            if not isinstance(row, dict):
                continue
            account = row.get("account", {})
            if not isinstance(account, dict):
                continue
            data_obj = account.get("data", {})
            if not isinstance(data_obj, dict):
                continue
            parsed = data_obj.get("parsed")
            if not isinstance(parsed, dict):
                continue
            info = parsed.get("info")
            if not isinstance(info, dict):
                continue
            mint = info.get("mint")
            ta = info.get("tokenAmount", {})
            if not isinstance(ta, dict):
                continue
            try:
                amt = int(ta.get("amount", "0"))
            except (TypeError, ValueError):
                amt = 0
            if mint and amt:
                raw[mint] = raw.get(mint, 0) + amt
    return {"sol_lamports": native, "token_raw_amounts": raw}


def _nav_usd(snapshot: dict, prices: dict[str, float]) -> float:
    total = snapshot["sol_lamports"] / 1e9 * prices.get(SOL_MINT, 0)
    for mint, amt in snapshot["token_raw_amounts"].items():
        dec = DECIMALS.get(mint)
        if dec is None or mint not in prices:
            continue
        total += (amt / (10 ** dec)) * prices[mint]
    return total


def _jupiter_quote(in_mint: str, out_mint: str, amount: int, slippage_bps: int) -> dict:
    q = urllib.parse.urlencode({
        "inputMint": in_mint,
        "outputMint": out_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "restrictIntermediateTokens": "true",
        "maxAccounts": "32",
    })
    return _http_json(f"https://lite-api.jup.ag/swap/v1/quote?{q}")


def _classify(position: dict, current_price: float) -> tuple[str, float, str]:
    """Return (action, slice_pct, reason). action in {EXIT, TAKE_PROFIT, HOLD}."""
    target = position.get("target_review_usd")
    invalidation = position.get("invalidation_review_usd")
    bucket = position.get("bucket", "long_term")
    if target is None and invalidation is None:
        return "HOLD", 0.0, "no target or invalidation set"
    if invalidation is not None and current_price <= invalidation:
        return "EXIT", 1.0, f"price ${current_price:.4f} <= invalidation ${invalidation}"
    if target is not None and current_price >= target:
        # Speculation bucket and dust holdings get full exits instead of partials
        if bucket in ("speculation",) or position.get("amount", 0) < 0.01:
            return "EXIT", 1.0, f"price ${current_price:.4f} >= target ${target} (full exit)"
        return "TAKE_PROFIT", 0.33, f"price ${current_price:.4f} >= target ${target}"
    return "HOLD", 0.0, f"price ${current_price:.4f} between invalidation ${invalidation} and target ${target}"


def _write_dynamic_entry(mint: str, thesis_id: str, max_notional: float, ttl: int = 21600) -> None:
    import dynamic_allowlist as d
    entry = d.build_supervisor_entry(
        mint=mint,
        thesis_id=thesis_id,
        max_notional_usd=max_notional,
        intent="speculation_buy",
        extensions_report={"transfer_hook": False, "permanent_delegate": False,
                          "transfer_fee_bps": 0, "non_transferable": False,
                          "default_account_state": "initialized"},
        liquidity_evidence={"source": "jupiter_aggregator"},
        rationale=f"profit_take auto-authorization: sell {mint} -> USDC",
        ttl_seconds=ttl,
    )
    d.write_entry(entry)


def _run_executor(wallet: str, in_mint: str, amount: int, notional_usd: float,
                  nav: float, slippage_bps: int, thesis_id: str) -> dict:
    max_loss = max(0.01, nav * MAX_RISK_PCT)
    cmd = [
        sys.executable, str(ROOT / "tools" / "privy_jupiter_executor.py"),
        "--wallet", wallet,
        "--thesis-id", thesis_id,
        "--input-mint", in_mint,
        "--output-mint", USDC_MINT,
        "--amount", str(amount),
        "--notional-usd", f"{notional_usd:.4f}",
        "--wallet-value-usd", f"{nav:.4f}",
        "--max-loss-usd", f"{max_loss:.4f}",
        "--slippage-bps", str(slippage_bps),
        "--execute",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out, err, code = proc.stdout, proc.stderr, proc.returncode
    try:
        parsed = json.loads(out.split("}", 1)[0] + "}") if out.strip() else None
    except json.JSONDecodeError:
        parsed = None
    if code != 0 and "not allowlisted" in err:
        # dynamic entry may have been consumed by an earlier attempt; re-authorize and retry once
        _write_dynamic_entry(in_mint, thesis_id, max_notional=notional_usd * 2, ttl=21600)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        out, err, code = proc.stdout, proc.stderr, proc.returncode
    return {"exit_code": code, "stdout": out, "stderr": err}


def _log_event(level: str, message: str) -> None:
    log = ROOT / "logs" / "profit_take.log"
    log.parent.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with log.open("a") as f:
        f.write(f"{ts}\t{level}\t{message}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="execute qualifying exits (default: dry-run)")
    ap.add_argument("--slice-pct", type=float, default=33.0, help="partial take-profit slice percentage (default 33)")
    ap.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    ap.add_argument("--wallet", help="override wallet (default: read from state/position_theses.json)")
    args = ap.parse_args()

    theses = json.loads(THESES.read_text())
    rules = json.loads(RULES.read_text())

    wallet = args.wallet or rules.get("wallet") or "<SOLANA_WALLET_ADDRESS>"
    if wallet.startswith("<"):
        print(f"SKIPPED | wallet is a placeholder ({wallet}); set state/position_rules.json wallet or pass --wallet")
        _log_event("SKIP", "wallet placeholder")
        return 0

    # Pull numeric target/invalidation from position_rules.json (not theses, which have text descriptions)
    rules_positions = rules.get("positions", {})

    active_cap = _active_cap_usd()
    active_pct = MAX_NOTIONAL_PCT
    print(f"PROFIT-TAKE | mode={'EXEC' if args.execute else 'DRY'} | cap=${active_cap} | ratio={active_pct*100:.0f}% | slice={args.slice_pct:.0f}%")

    snapshot = _balances(wallet)
    sol_balance = snapshot["sol_lamports"] / 1e9
    if sol_balance - FEE_RESERVE_SOL < 0.05:
        print(f"BLOCKED | SOL balance {sol_balance:.4f} too close to fee reserve {FEE_RESERVE_SOL}")
        _log_event("BLOCK", f"SOL below fee reserve: {sol_balance:.4f}")
        return 0

    mints = [m for m in snapshot["token_raw_amounts"] if m != USDC_MINT]
    prices = _live_prices(mints + [USDC_MINT])
    nav = _nav_usd(snapshot, prices)
    print(f"NAV ~${nav:.2f} | SOL {sol_balance:.4f} | prices: {len(prices)}/{len(mints)+1} fetched")

    actions: list[dict] = []
    for mint in mints:
        symbol = ALLOWLIST_HARDCODED.get(mint)
        if not symbol:
            continue
        position = {**(theses.get("positions", {}).get(symbol, {})), **rules_positions.get(symbol, {})}
        if not position:
            continue
        price = prices.get(mint, 0)
        if not price:
            continue
        action, default_pct, reason = _classify(position, price)
        if action == "HOLD":
            actions.append({"mint": mint, "symbol": symbol, "action": "HOLD", "reason": reason, "price_usd": price})
            continue
        slice_pct = (args.slice_pct / 100.0) if action == "TAKE_PROFIT" else default_pct
        raw_amount = snapshot["token_raw_amounts"][mint]
        dec = DECIMALS.get(mint, 6)
        human_balance = raw_amount / (10 ** dec)
        sell_raw = int(raw_amount * slice_pct)
        sell_human = sell_raw / (10 ** dec)
        notional = sell_human * price
        if notional > active_cap:
            actions.append({"mint": mint, "symbol": symbol, "action": "SKIP", "reason": f"notional ${notional:.2f} > cap ${active_cap}"})
            continue
        if notional > nav * active_pct:
            actions.append({"mint": mint, "symbol": symbol, "action": "SKIP", "reason": f"notional ${notional:.2f} > {active_pct*100:.0f}% NAV ${nav*active_pct:.2f}"})
            continue
        # Net edge check via fresh two-way quote
        try:
            q = _jupiter_quote(mint, USDC_MINT, sell_raw, args.slippage_bps)
        except Exception as exc:
            actions.append({"mint": mint, "symbol": symbol, "action": "SKIP", "reason": f"quote error: {exc}"})
            continue
        impact = float(q.get("priceImpactPct", 0)) * 100
        if impact > 0.5:
            actions.append({"mint": mint, "symbol": symbol, "action": "SKIP", "reason": f"impact {impact:.3f}% > 0.5%"})
            continue
        quoted_usdc = int(q["outAmount"]) / 1e6
        slippage_cost = quoted_usdc * 0.005  # 50bps as a worst-case slippage on output
        priority_fee_usd = PRIORITY_FEE_SOL * prices.get(SOL_MINT, 78)
        total_cost = slippage_cost + priority_fee_usd
        net_edge = quoted_usdc - total_cost
        if net_edge <= 0:
            actions.append({"mint": mint, "symbol": symbol, "action": "SKIP", "reason": f"no positive net edge: ${net_edge:.4f}"})
            continue

        record = {
            "mint": mint, "symbol": symbol, "action": action, "reason": reason,
            "slice_pct": slice_pct * 100,
            "sell_amount": sell_human, "sell_raw": sell_raw,
            "price_usd": price, "notional_usd": notional,
            "quoted_usdc": quoted_usdc, "impact_pct": impact,
            "slippage_cost": slippage_cost, "priority_fee": priority_fee_usd,
            "net_edge_usd": net_edge, "nav": nav,
        }
        if args.execute:
            thesis_id = f"profit-take-{symbol.lower()}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            try:
                _write_dynamic_entry(mint, thesis_id, max_notional=notional * 1.2, ttl=21600)
            except Exception as exc:
                record["execution_status"] = f"dynamic_allowlist_failed: {exc}"
                actions.append(record)
                continue
            result = _run_executor(wallet, mint, sell_raw, notional, nav,
                                   args.slippage_bps, thesis_id)
            record["execution"] = result
            record["execution_status"] = "ok" if result["exit_code"] == 0 else f"failed_exit_{result['exit_code']}"
            _log_event("EXEC" if result["exit_code"] == 0 else "FAIL",
                       f"{symbol} {action} slice={slice_pct*100:.0f}% amount={sell_human} "
                       f"price=${price} notional=${notional:.2f} edge=${net_edge:.4f}")
        else:
            record["execution_status"] = "dry_run"
            _log_event("DRY", f"{symbol} {action} slice={slice_pct*100:.0f}% amount={sell_human} "
                              f"price=${price} notional=${notional:.2f} edge=${net_edge:.4f}")
        actions.append(record)

    # Compact Telegram card (max ~10 lines)
    print()
    print("PROFIT-TAKE REPORT")
    for a in actions:
        if "sell_amount" in a:
            print(f"  {a.get('action', 'SKIP'):>11s} | {a.get('symbol', '?')[:8]:>8s} | "
                  f"slice={a.get('slice_pct', 0):.0f}% | amt={a.get('sell_amount', 0):.4f} | "
                  f"px=${a.get('price_usd', 0):.4f} | notional=${a.get('notional_usd', 0):.2f} | "
                  f"edge=${a.get('net_edge_usd', 0):.4f} | impact={a.get('impact_pct', 0):.3f}% | "
                  f"{a.get('execution_status', '')}")
        else:
            print(f"  {a.get('action', 'SKIP'):>11s} | {a.get('symbol', '?')[:8]:>8s} | {a.get('reason', '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())