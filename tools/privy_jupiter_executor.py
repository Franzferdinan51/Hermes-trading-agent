#!/usr/bin/env python3
"""Bounded Privy + Jupiter Solana executor.

Default mode is dry-run: quote and preflight only.  --execute is required to
request a Privy signature and broadcast.  This tool never withdraws, sweeps,
or calls arbitrary programs; it only accepts an explicit allowlist of spot mints.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from solders.transaction import VersionedTransaction

from policy_engine import HALT, PolicyError, halt, preflight, trade_lock

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "logs" / "trade_ledger.jsonl"
THESIS = ROOT / "state" / "position_theses.json"
RPC = "https://api.mainnet-beta.solana.com"
QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
SWAP_URL = "https://api.jup.ag/swap/v1/swap"
PRIVY = ["pnpm", "--package=@privy-io/agent-wallet-cli", "dlx", "privy-agent-wallet", "rpc"]
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
CBBTC = "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij"
JUPSOL = "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v"
ANSEM = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"
JLUSDC = "9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D"
ALLOWLIST = {SOL, USDC, JUP, CBBTC, JUPSOL, ANSEM, JLUSDC}
ALLOWLIST_INTENT = {
    SOL: "core",
    USDC: "core",
    JUP: "core",
    CBBTC: "core",
    JUPSOL: "core",
    ANSEM: "speculation_exit",
    JLUSDC: "core_earn_redeem",
}
SPECULATIVE_ALLOWLIST = {ANSEM}
FEE_RESERVE_LAMPORTS = 20_000_000
QUOTE_TTL_SECONDS = 20
JUPITER_ROUTER = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
APPROVED_TOP_LEVEL_PROGRAMS = {
    "11111111111111111111111111111111",
    "ComputeBudget111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    JUPITER_ROUTER,
}


def http_json(url: str, *, method: str = "GET", body: dict | None = None) -> dict:
    """Call RPC/Jupiter with bounded retry for transient Jupiter rate limits.

    Quotes must be fresh at execution time, so retry only the request itself and
    never reuse a cached quote. Jupiter calls use the same authenticated,
    browser-like headers as the verified quote helper.
    """
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if url.startswith("https://api.jup.ag/"):
        key = os.environ.get("JUPITER_API_KEY")
        if not key:
            result = subprocess.run(
                ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", "jupiter-api-key", "-w"],
                capture_output=True, text=True, check=True,
            )
            key = result.stdout.strip()
        headers.update({"x-api-key": key, "User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else float(2 ** attempt)
            time.sleep(delay)
    raise RuntimeError("unreachable Jupiter retry state")


def rpc(method: str, params: list) -> object:
    result = http_json(RPC, method="POST", body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in result:
        raise RuntimeError(f"Solana RPC {method}: {result['error']}")
    return result["result"]


TOKEN_PROGRAMS = [
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
]


def balances(address: str) -> dict:
    native = rpc("getBalance", [address])["value"]
    tokens = {}
    token_raw_amounts = {}
    for program_id in TOKEN_PROGRAMS:
        rows = rpc("getTokenAccountsByOwner", [address, {"programId": program_id}, {"encoding": "jsonParsed"}])["value"]
        for row in rows:
            info = row["account"]["data"]["parsed"]["info"]
            mint = info["mint"]
            raw = int(info["tokenAmount"]["amount"])
            decimals = int(info["tokenAmount"]["decimals"])
            if raw:
                token_raw_amounts[mint] = token_raw_amounts.get(mint, 0) + raw
                total = token_raw_amounts[mint]
                tokens[mint] = f"{total / (10 ** decimals):.{decimals}f}".rstrip("0").rstrip(".")
    return {"sol_lamports": native, "tokens": tokens, "token_raw_amounts": token_raw_amounts}


def speculative_buy_allowed(mint: str) -> bool:
    """Allow a speculative buy only with a fresh supervisor-created entry.

    The entry must explicitly use ``intent=speculation_buy`` and is single-use
    with a short TTL.  No entry means buys remain disabled.
    """
    try:
        from dynamic_allowlist import entry_for
        entry = entry_for(mint)
    except ImportError:
        return False
    return bool(entry and entry.get("intent") == "speculation_buy")


def speculative_exit_only(mint: str) -> bool:
    return mint in SPECULATIVE_ALLOWLIST


def enforce_speculative_direction(input_mint: str, output_mint: str) -> None:
    """Speculative-exit mints may be sold but never bought in the spot executor."""
    if output_mint in SPECULATIVE_ALLOWLIST and not speculative_buy_allowed(output_mint):
        raise PolicyError(
            f"speculative mint {output_mint} is allowlisted for exit only; buys are not permitted"
        )


def asset_raw_balance(snapshot: dict, mint: str) -> int:
    if mint == SOL:
        return int(snapshot.get("sol_lamports", 0))
    return int(snapshot.get("token_raw_amounts", {}).get(mint, 0))


def _jupiter_can_route(mint: str) -> bool:
    """Return True if Jupiter can route a quote for this mint (USDC or SOL as the other leg).
    Uses a small SOL amount (1M lamports = 0.001 SOL) to probe routing without meaningful cost.
    """
    import urllib.parse
    # Always probe via SOL first since SOL pairs are the most universal on Solana
    for other, probe_amount in ((USDC, "1000000"), (SOL, "1000000")):
        try:
            query = urllib.parse.urlencode({
                "inputMint": mint if mint != other else SOL,
                "outputMint": other if mint != other else USDC,
                "amount": probe_amount,
                "slippageBps": "500",
            })
            result = http_json(f"{QUOTE_URL}?{query}")
            if result.get("outAmount") and int(result["outAmount"]) > 0:
                return True
        except Exception:
            pass
    return False


def is_dynamic_allowlist_tradeable(mint: str) -> tuple[bool, dict | None, str]:
    """Return (allowed, entry, reason). Core mints always pass.
    For other mints: dynamic allowlist entry → pass; otherwise ask Jupiter.
    """
    if mint in ALLOWLIST:
        return True, None, "hard_coded"
    try:
        from dynamic_allowlist import entry_for, is_halted
    except ImportError:
        pass
    else:
        if not is_halted():
            entry = entry_for(mint)
            if entry is not None:
                return True, entry, "dynamic"
    # No allowlist entry — ask Jupiter if it can route this mint
    if _jupiter_can_route(mint):
        return True, None, "jupiter_routed"
    return False, None, "no_active_authorization"


def verify_post_trade(before: dict, after: dict, input_mint: str, output_mint: str,
                      input_amount: int, minimum_out: int) -> None:
    output_delta = asset_raw_balance(after, output_mint) - asset_raw_balance(before, output_mint)
    if output_delta < minimum_out:
        raise PolicyError(
            f"post-trade output below minimum output: observed {output_delta}, required {minimum_out}"
        )
    input_delta = asset_raw_balance(before, input_mint) - asset_raw_balance(after, input_mint)
    if input_delta <= 0:
        raise PolicyError("post-trade input balance did not decrease")
    if input_mint != SOL and input_delta < input_amount:
        raise PolicyError(
            f"post-trade input debit below requested amount: observed {input_delta}, requested {input_amount}"
        )
    if int(after.get("sol_lamports", 0)) < FEE_RESERVE_LAMPORTS:
        raise PolicyError("post-trade SOL balance fell below the 0.02 SOL fee reserve")


def fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int,
          *, only_direct_routes: bool = False) -> dict:
    query = urllib.parse.urlencode({
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "restrictIntermediateTokens": "true",
        "onlyDirectRoutes": str(only_direct_routes).lower(),
        # Deriverse routes have repeatedly failed unsigned simulation with
        # custom error 0x14; exclude them until the venue is verified again.
        "excludeDexes": "Deriverse,Metric",
        "maxAccounts": "32",
    })
    return http_json(f"{QUOTE_URL}?{query}")


def decode_and_validate_transaction(transaction_b64: str, wallet: str) -> dict:
    try:
        tx = VersionedTransaction.from_bytes(base64.b64decode(transaction_b64, validate=True))
    except Exception as exc:
        raise PolicyError(f"cannot decode Jupiter transaction: {exc}") from exc
    message = tx.message
    keys = list(message.account_keys)
    if not keys or str(keys[0]) != wallet:
        raise PolicyError(f"unexpected transaction fee payer: {keys[0] if keys else 'missing'}")
    programs = []
    for instruction in message.instructions:
        program = str(keys[instruction.program_id_index])
        programs.append(program)
        if program not in APPROVED_TOP_LEVEL_PROGRAMS:
            raise PolicyError(f"unapproved top-level program in Jupiter transaction: {program}")
    if JUPITER_ROUTER not in programs:
        raise PolicyError("Jupiter router instruction missing from swap transaction")
    return {"fee_payer": str(keys[0]), "account_count": len(keys), "programs": programs}


def simulate_unsigned(transaction_b64: str) -> dict:
    result = rpc("simulateTransaction", [transaction_b64, {
        "encoding": "base64",
        "sigVerify": False,
        "replaceRecentBlockhash": True,
        "commitment": "confirmed",
    }])
    value = result.get("value", {})
    if value.get("err") is not None:
        logs = value.get("logs") or []
        detail = " | ".join(str(line) for line in logs[-12:])
        raise PolicyError(f"unsigned transaction simulation failed: {value['err']}; logs: {detail}")
    return {"units_consumed": value.get("unitsConsumed")}


def require_not_halted(stage: str) -> None:
    if HALT.exists():
        raise PolicyError(f"emergency stop became active before {stage}")


def build_swap(q: dict, wallet: str) -> tuple[dict, dict, dict]:
    swap = http_json(SWAP_URL, method="POST", body={
        "quoteResponse": q,
        "userPublicKey": wallet,
        "asLegacyTransaction": False,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    })
    tx_b64 = swap.get("swapTransaction")
    if not isinstance(tx_b64, str):
        raise PolicyError("Jupiter swap response did not contain swapTransaction")
    decoded = decode_and_validate_transaction(tx_b64, wallet)
    simulation = simulate_unsigned(tx_b64)
    return swap, decoded, simulation


def privy_sign(transaction_b64: str) -> str:
    payload = {"method": "signTransaction", "params": {"transaction": transaction_b64, "encoding": "base64"}}
    command = ["pnpm", "--package=@privy-io/agent-wallet-cli", "dlx", "privy-agent-wallet", "rpc", "--json", json.dumps(payload)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if proc.returncode:
        raise RuntimeError(f"Privy signTransaction failed: {proc.stderr.strip() or proc.stdout.strip()}")
    parsed = json.loads(proc.stdout)
    # CLI response schemas may wrap the signed transaction differently.
    for key in ("signedTransaction", "signed_transaction", "transaction", "result", "data"):
        value = parsed.get(key) if isinstance(parsed, dict) else None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for nested in ("signedTransaction", "signed_transaction", "transaction"):
                if isinstance(value.get(nested), str):
                    return value[nested]
    raise RuntimeError("Privy response did not contain a signed transaction")


def finalize(signature: str, timeout_s: int = 75) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])["value"][0]
        if status and status.get("confirmationStatus") == "finalized":
            if status.get("err") is not None:
                raise RuntimeError(f"transaction finalized with error: {status['err']}")
            return status
        time.sleep(2)
    raise RuntimeError("transaction did not reach finalized state before timeout")


def record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", required=True)
    ap.add_argument("--thesis-id", required=True, help="stable thesis/Kanban identifier recorded in the ledger")
    ap.add_argument("--input-mint", required=True)
    ap.add_argument("--output-mint", required=True)
    ap.add_argument("--amount", required=True, type=int, help="input amount in smallest units")
    ap.add_argument("--notional-usd", required=True, type=float)
    ap.add_argument("--wallet-value-usd", required=True, type=float)
    ap.add_argument("--max-loss-usd", required=True, type=float)
    ap.add_argument("--slippage-bps", type=int, default=50)
    ap.add_argument("--only-direct-routes", action="store_true", help="require a single direct Jupiter route; use after a multi-hop route failure")
    ap.add_argument("--execute", action="store_true", help="sign and broadcast; without this flag the tool is dry-run only")
    args = ap.parse_args()

    if args.input_mint == args.output_mint:
        raise SystemExit("input and output mints must differ")
    allowed_in, entry_in, reason_in = is_dynamic_allowlist_tradeable(args.input_mint)
    if not allowed_in:
        raise SystemExit(f"input mint {args.input_mint} not allowlisted ({reason_in})")
    allowed_out, entry_out, reason_out = is_dynamic_allowlist_tradeable(args.output_mint)
    if not allowed_out:
        raise SystemExit(f"output mint {args.output_mint} not allowlisted ({reason_out})")
    for entry in (entry_in, entry_out):
        if entry and entry.get("max_notional_usd") and args.notional_usd > entry["max_notional_usd"]:
            raise SystemExit(
                f"notional {args.notional_usd} exceeds per-mint cap {entry['max_notional_usd']} for {entry['mint']}"
            )
    before = balances(args.wallet)
    if args.input_mint == SOL and before["sol_lamports"] - args.amount < FEE_RESERVE_LAMPORTS:
        raise PolicyError("trade would consume the 0.02 SOL fee reserve")
    enforce_speculative_direction(args.input_mint, args.output_mint)
    before_fp = fingerprint(before)
    quote_received_at = time.monotonic()
    q = quote(args.input_mint, args.output_mint, args.amount, args.slippage_bps,
              only_direct_routes=args.only_direct_routes)
    impact = float(q.get("priceImpactPct", 0)) * 100
    expected = int(q["outAmount"])
    minimum = int(q["otherAmountThreshold"])
    swap, decoded, simulation = build_swap(q, args.wallet)
    quote_age = time.monotonic() - quote_received_at
    preflight(
        wallet_value_usd=args.wallet_value_usd,
        notional_usd=args.notional_usd,
        max_loss_usd=args.max_loss_usd,
        quote_age_s=quote_age,
        price_impact_pct=impact,
        slippage_bps=args.slippage_bps,
        expected_out=expected,
        min_out=minimum,
        current_fingerprint=before_fp,
        before_fingerprint=before_fp,
    )
    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "wallet": args.wallet,
        "thesis_id": args.thesis_id,
        "input_mint": args.input_mint,
        "output_mint": args.output_mint,
        "input_mint_intent": ALLOWLIST_INTENT.get(args.input_mint, "unknown"),
        "output_mint_intent": ALLOWLIST_INTENT.get(args.output_mint, "unknown"),
        "amount": args.amount,
        "out_amount": q["outAmount"],
        "minimum_out": q["otherAmountThreshold"],
        "price_impact_pct": q.get("priceImpactPct"),
        "route": [x.get("swapInfo", {}).get("label") for x in q.get("routePlan", [])],
        "quote_age_seconds": round(quote_age, 3),
        "decoded_transaction": decoded,
        "simulation": simulation,
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return

    with trade_lock():
        try:
            require_not_halted("fresh execution preflight")
            before = balances(args.wallet)
            if args.input_mint == SOL and before["sol_lamports"] - args.amount < FEE_RESERVE_LAMPORTS:
                raise PolicyError("trade would consume the 0.02 SOL fee reserve")
            enforce_speculative_direction(args.input_mint, args.output_mint)
            current = balances(args.wallet)
            preflight(
                wallet_value_usd=args.wallet_value_usd,
                notional_usd=args.notional_usd,
                max_loss_usd=args.max_loss_usd,
                quote_age_s=time.monotonic() - quote_received_at,
                price_impact_pct=impact,
                slippage_bps=args.slippage_bps,
                expected_out=expected,
                min_out=minimum,
                current_fingerprint=fingerprint(current),
                before_fingerprint=before_fp,
            )
            route = [x.get("swapInfo", {}).get("label") for x in q.get("routePlan", [])]
            record({
                "ts": datetime.now(timezone.utc).isoformat(), "record_version": 4,
                "record_type": "EXECUTION_INTENT", "wallet": args.wallet,
                "thesis_id": args.thesis_id, "status": "prepared",
                "in_mint": args.input_mint, "out_mint": args.output_mint,
                "in_amount": str(args.amount), "quoted_out": q["outAmount"],
                "min_out": q["otherAmountThreshold"], "route": route,
                "decoded_transaction": decoded, "simulation": simulation,
            })
            require_not_halted("signing")
            signed = privy_sign(swap["swapTransaction"])
            require_not_halted("broadcast")
            signature = rpc("sendTransaction", [signed, {"encoding": "base64", "skipPreflight": False, "preflightCommitment": "confirmed"}])
            record({
                "ts": datetime.now(timezone.utc).isoformat(), "record_version": 4,
                "record_type": "EXECUTION_BROADCAST", "wallet": args.wallet,
                "thesis_id": args.thesis_id, "status": "broadcast",
                "tx_hash": signature,
            })
            status = finalize(signature)
            after = balances(args.wallet)
            verify_post_trade(before, after, args.input_mint, args.output_mint, args.amount, minimum)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "record_version": 4,
                "wallet": args.wallet,
                "thesis_id": args.thesis_id,
                "action": "JUPITER_PRIVY_SWAP",
                "in_mint": args.input_mint,
                "out_mint": args.output_mint,
                "in_amount": str(args.amount),
                "quoted_out": q["outAmount"],
                "min_out": q["otherAmountThreshold"],
                "observed_out_raw": str(asset_raw_balance(after, args.output_mint) - asset_raw_balance(before, args.output_mint)),
                "price_impact_pct": q.get("priceImpactPct"),
                "route": route,
                "tx_hash": signature,
                "status": "finalized",
                "slot": status.get("slot"),
                "balance_before": before,
                "balance_after": after,
                "decoded_transaction": decoded,
                "simulation": simulation,
                "verifiers_passed": 1,
            }
            record(entry)
            print(json.dumps(entry, indent=2))
            try:
                from dynamic_allowlist import consume_entry
                for m in (args.input_mint, args.output_mint):
                    if m not in ALLOWLIST:
                        consume_entry(m)
            except ImportError:
                pass
        except Exception as exc:
            halt(f"executor anomaly for thesis {args.thesis_id}: {exc}")
            record({
                "ts": datetime.now(timezone.utc).isoformat(), "record_version": 4,
                "record_type": "EXECUTION_FAILURE", "wallet": args.wallet,
                "thesis_id": args.thesis_id, "status": "halted", "error": str(exc),
            })
            raise


if __name__ == "__main__":
    main()
