# Jupiter Executor Dry-Run Test Report
**Date:** 2026-07-11 12:10 ET
**Wallet:** <YOUR_PRIVY_SOLANA_WALLET>
**Tool:** `tools/privy_jupiter_executor.py`

---

## Summary

Executor dry-run is **functional**. Policy guard, quote fetching, preflight checks, and dry-run output all work correctly. No HALT or LOCK files are active. One meaningful limitation was found: ANSEM (Token-2022) is not on the ALLOWLIST.

---

## Test Results

### 1. JUP → USDC (1B lamports = ~$0.21 notional)
```
PASS  dry_run  mode=dry_run
route: Scorch → HumidiFi
out_amount: 208,736,771 USDC (min: 207,693,088)
price_impact_pct: 0.00032%
```
Policy preflight: PASS (notional $0.21 << $30 cap)

### 2. JUP → SOL (500M lamports = ~$0.105 notional)
```
PASS  dry_run  mode=dry_run
route: HumidiFi → TesseraV
out_amount: 1,332,945,429 SOL lamports (min: 1,326,280,702)
price_impact_pct: 0%
```
Policy preflight: PASS

### 3. SOL → USDC (30M lamports = ~$2.35 notional)
```
PASS  dry_run  mode=dry_run
route: Quantum → SolFi V2
out_amount: 2,350,415 USDC (min: 2,338,663)
price_impact_pct: 0%
```
Policy preflight: PASS

### 4. SOL → USDC (50M lamports = ~$3.91 notional)
```
PASS  dry_run  mode=dry_run
route: BisonFi
out_amount: 3,916,802 USDC (min: 3,897,218)
price_impact_pct: 0.00016%
```
Policy preflight: PASS

### 5. SOL → USDC (100M lamports = ~$7.83 notional) — REJECTED
```
PolicyError: notional exceeds 10% wallet limit
wallet 10% = $6.29;  notional $7.83
```
**Correct behavior.** Policy engine enforces `MAX_NOTIONAL_USD = 0.10` (10% of wallet). Amount needs to stay ≤ ~63M lamports to pass.

### 6. SOL → USDC (1B lamports = ~$78.29 notional) — REJECTED
```
PolicyError: notional exceeds active cap
PolicyError: notional exceeds 10% wallet limit
```
**Correct behavior.** Both the $30 hard cap and the 10% wallet rule reject this notional.

---

## Privy Wallet Status
```
Solana: <YOUR_PRIVY_SOLANA_WALLET>  (active)
Ethereum/Base: <YOUR_HERMES_ETHEREUM_WALLET>  (active)
Bitcoin: bc1qpmp7e67rfkennxx7ytrgwk3qdcdy4a25ry7kqy  (active)
```
All three wallets confirmed. Session active.

---

## Policy Guard Status
```
HALT file:  absent  (no emergency stop)
LOCK file:  absent  (no active wallet lock)
```
Safe to execute.

---

## ALLOWLIST Analysis

Current allowlist in `privy_jupiter_executor.py`:
```python
ALLOWLIST = {SOL, USDC, JUP, CBBTC, JUPSOL}
```

| Asset | On Allowlist | Status |
|-------|-------------|--------|
| SOL   | YES | Tradable |
| USDC  | YES | Tradable |
| JUP   | YES | Tradable |
| cbBTC | YES | Tradable |
| JupSOL | YES | Tradable |
| JL-USDC (receipt) | NO | Cannot route through executor |
| ANSEM | **NO** | **Cannot route through executor** |

**Issue:** ANSEM (Token-2022) is not on the ALLOWLIST. Any attempt to execute `ANSEM→SOL` or `ANSEM→USDC` via the executor would be rejected at argument parsing, not at preflight. The ledger shows ANSEM was purchased via direct Jupiter web UI, not through this executor.

---

## Trading Cron Status

The `trading-cron.py` script is still running against an **empty Cosmos/Osmosis wallet** (`cosmos1fsdzl5un...`). The cron fires every 2 hours and immediately logs "Balance $0.00 below minimum $5" — no trades executed.

**Recommendation:** The cron job `f97f00116a10` ("DuckBot Crypto Trading - Every 2 Hours") is **paused** but should either be redirected to the Solana setup or left dormant since the Cosmos position has been migrated.

---

## Active Jupiter Crons (All Healthy)

| Cron | Schedule | Model | Status |
|------|----------|-------|--------|
| Jupiter Research - Morning Open | 6 AM | GPT-5.6 Luna | OK |
| Jupiter Research - Morning Midday | 10 AM | GPT-5.6 Luna | OK |
| Jupiter Research - Afternoon | 2 PM | GPT-5.6 Luna | OK |
| Jupiter Research - Evening | 6 PM | GPT-5.6 Luna | OK |
| Jupiter Research - Overnight | 2 AM | GPT-5.6 Luna | OK |
| Jupiter Day Trading - Open | 9:30 AM weekdays | GPT-5.6 Luna | OK |
| Jupiter Day Trading - Afternoon | 3:30 PM weekdays | GPT-5.6 Luna | OK |
| Jupiter Day Trading - Midday Collector | 12:30 PM weekdays | MiniMax M2.7 | OK |
| Jupiter Price Monitor | every 2h | MiniMax M2.7 | OK |
| Portfolio Targets Manager | 7:30 AM | GPT-5.6 Luna | OK |
| Autonomous Execution Supervisor | every 2h | GPT-5.6 Luna | OK |
| Portfolio Reconciliation | every 2h | MiniMax M2.7 | OK |
| Yield/Staking/Liquidity Monitor | every 4h | MiniMax M2.7 | OK |
| News/Market Impact Monitor | every 4h | MiniMax M2.7 | OK |
| Brain Sync | hourly | — | OK (script) |

---

## Issues Found

### Issue 1: ANSEM Not on ALLOWLIST (Medium)
ANSEM is a Token-2022 asset held in the portfolio but is not a valid `--input-mint` or `--output-mint` argument for the executor. The executor's ALLOWLIST needs to be expanded if ANSEM trading through this tool is ever desired. Currently ANSEM was entered via Jupiter web UI, not via this tool.

### Issue 2: Trading Cron vs. Empty Cosmos Wallet (Low — already paused)
The `trading-cron.py` script targets an empty Cosmos wallet. The cron is paused (`f97f00116a10`, paused 2026-07-10). No action needed unless the user wants to redirect it.

### Issue 3: Hardcoded Cap in Policy Engine (Design Observation)
`policy_engine.py` line 16: `CAP_USD = 30.0` is a hardcoded constant, not read from `position_rules.json` (`active_cap_usd: 30.0`). Both currently agree, but they could diverge if the rules file is updated without syncing the Python constant. The executor uses `position_rules.json` for context but the policy engine module has its own hardcoded copy.

---

## Conditions for Actual Execution

To run `--execute` (sign + broadcast) rather than dry-run, ALL of the following must be true:

1. Quote notional ≤ $30 (active cap)
2. Quote notional ≤ 10% of wallet value ($6.29 at current NAV $62.88)
3. Price impact ≤ 0.5%
4. Slippage BPS ≤ 100
5. Quote age ≤ 20 seconds at time of signing
6. No HALT or LOCK files present
7. Wallet fingerprint unchanged since preflight
8. User has authorized the specific swap via Privy session

Current portfolio NAV ($62.88) allows a maximum SOL→USDC dry-run of ~63M lamports ($4.94) before the 10% rule blocks it.

---

## Verdict

- **Dry-run executor:** Fully functional, preflight working, Jupiter API responding correctly
- **Policy guard:** Active and correctly enforcing caps
- **Privy session:** Valid for signing
- **No operational blockers** for dry-run or execution when conditions are met
- **Main limitation:** No Token-2022 tokens (ANSEM, any future Token-2022) on allowlist; expand ALLOWLIST if needed
