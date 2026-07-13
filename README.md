# Hermes Trading Agent

A bounded, policy-controlled crypto operations and trading agent for **Solana via Jupiter** and **Base via Coinbase CDP**. It combines live wallet reconciliation, mandatory pre-buy research, risk-proportionate entry evaluation, sell/exit review, profitability analysis, and platform-local execution. Guardrails include exact asset identity, fresh quotes, liquidity and cost checks, transaction decoding, simulation, finalized settlement, independent reconciliation, emergency stop, and one-trade locking.

> **Current status:** Jupiter/Solana spot operations and bounded Coinbase CDP Base `USDC→WETH` are the active execution paths. Tokenized stocks/xStocks are research-enabled but execution-gated. PancakeSwap and other venues remain separately gated.

> This repository is a fork-and-configure template. Replace example wallet addresses before using it. Never commit API keys, wallet secrets, private keys, `.env` files, or runtime evidence/logs.

## Scope

- **Active:** Solana via Jupiter aggregator for bounded spot swaps and reconciled portfolio operations.
- **Active:** Base via Coinbase CDP only for the allowlisted `USDC→WETH` route through `tools/cdp_base_executor.mjs` (≤$100 USDC, ≤100 bps slippage, fresh quote/simulation, positive net-edge gate, supervisor authorization, and independent receipt/balance verification). Live CDP token balances are queried through the official SDK token-balance listing.
- **Buy evaluation:** Every buy requires the `buy-evaluation` procedure: mandatory, risk-proportionate research, exact identity, liquidity, cost, exit-path, jurisdiction, and positive-net-edge checks. Decisions are `BUY`, `DO NOT BUY`, or `RESEARCH MORE`.
- **Tokenized stocks/xStocks:** Research and monitoring enabled; execution remains gated per asset until mint, issuer/backing, rights, redemption, liquidity, custody, settlement, and jurisdiction checks pass.
- **Authorized profit strategies:** spot, earn/yield, liquidity provision, staking, lending, and other strategy classes only when their venue-specific executor and risk gates are verified. Leverage/perps, bridges, and predictions remain separately gated.
- **Primary venues:** Jupiter/Solana and PancakeSwap (Base/Solana). The supervisor compares only verified routes and selects the better risk-adjusted net outcome.
- **First fallback:** Coinbase CDP on Base when a primary venue is unavailable, unsupported, or materially worse after all costs.
- **Secondary fallbacks:** Avantis, Robinhood, SunSwap, and TronLink remain independently gated; none may be used until its platform-specific readiness and policy requirements are met.
- **Not selected:** Aerodrome is explicitly disabled.
- **Legacy (do not use):** Keplr / Cosmos / Osmosis workflows are preserved under
  `legacy/` for the historical record only. They are explicitly deprecated and ignored
  by the active code path.

## Profitability and portfolio buckets

The operating objective is risk-adjusted profitability, not trade frequency. Candidates must show positive expected net edge after fees, spread, slippage, gas, funding, liquidity impact, transfer costs, and opportunity cost. A clean **HOLD** is preferable to a forced trade. Research is mandatory before every buy, but diligence is risk-proportionate: established liquid assets may use a lighter entry review, while speculative, illiquid, tokenized-stock, RWA, and unfamiliar assets require deeper verification.

Current global ceilings are **3% maximum total/active risk** and **3% normal maximum daily realized loss**, with a **5% emergency hard stop** that disables new trading for the rest of the session. There is no arbitrary maximum number of open positions; the portfolio may hold as many justified positions as fit within aggregate risk, liquidity, correlation, fee-efficiency, reserve, and exit-capacity constraints. These are ceilings, not targets; position size is determined by downside, liquidity, concentration, and confidence—not available balance.

**Fixed-capital operating constraint:** The currently funded wallets are the complete available trading capital. Do not assume or request additional deposits. Preserve native fee reserves and operate within verified current balances; internal transfers are balance reclassification, not new capital or profit.

Capital is managed by bucket:

- **Treasury/stable reserve:** operational liquidity and fee runway.
- **Short-term/day trading:** current catalyst or repeatable edge, explicit exit and time stop.
- **Long-term/core:** thesis, target, invalidation, tokenomics, concentration review, and a productive-use plan where verified.
- **Long-term utilization:** prefer verified staking, governance/voting, lending, or yield routes for idle long-term assets when expected net yield and strategic value justify the additional smart-contract, custody, oracle, lockup, depeg, and withdrawal risks. Keep a liquid reserve and do not deploy assets merely to chase APY.
- **Long-term staking:** JupSOL-style yield versus depeg, validator, liquidity, and contract risk.
- **Long-term earn/yield:** JL-USDC-style APY versus withdrawal, smart-contract, oracle, borrower, and depeg risk.
- **Yield watchlist:** researched but unheld products such as JLP.
- **Speculative:** capped exact-mint positions with security/liquidity review, time stop, and no averaging down.
- **Dormant strategies:** perps, predictions, scanners, LP, and other modules require separate enablement.

Transfers between buckets require a documented source, destination, reason, costs, and updated exposure.

## Scheduled trading workflow

The active Hermes scheduler includes market/research collectors, three day-trading collectors, portfolio/risk management, an hourly sell/exit evaluator, a daily canonical profit sweep, reconciliation/health checks, and one autonomous portfolio supervisor. The supervisor consumes those outputs and is the only layer that may authorize a bounded executor action.

The sell/exit evaluator classifies positions as `HOLD`, `WATCH`, `SELL-READY`, or `URGENT-EXIT` by checking targets, invalidations, time stops, liquidity, reverse quotes, and all-in net outcome. Profit sweeps are also subject to bucket-aware profitability and reserve gates.


### Active (use this)

| Path | Purpose |
|------|---------|
| `tools/privy_jupiter_executor.py` | The bounded executor. Hard-coded mint allowlist, dynamic per-mint runtime allowlist, transaction decoding, simulation, fee-payer check, Jupiter-router enforcement, minimum-output verification, post-trade balance reconciliation, single-use consumption of dynamic entries. |
| `tools/cdp_base_executor.mjs` | Official Coinbase CDP SDK Base executor. Dry-run by default, USDC→WETH allowlist, Permit2 approval handling, gas precheck, slippage/notional caps, idempotency, receipt and balance verification. |
| `tools/policy_engine.py` | The preflight guard. Numeric validation, quote-age cap, price-impact cap, slippage cap, notional/risk ratios (sourced from `state/position_rules.json`), one-trade filesystem lock, emergency-stop marker. |
| `tools/dynamic_allowlist.py` | Runtime per-mint allowlist managed by the supervisor. TTL cap, per-mint notional cap, mandatory Token-2022 extension report, single-use consumption, kill switch. |
| `tools/dynamic_allowlist_cli.py` | Operator CLI for the dynamic allowlist (`halt`, `resume`, `status`, `list`, `show`, `purge-expired`). |
| `tools/trade_ledger.py` | Append-only ledger of action records; rejects malformed finalized entries. |
| `tools/jupiter_api.py` | Thin wrapper around Jupiter Lite API endpoints. |
| `tools/price-monitor.py` | Reads prices and writes a JSONL log. |
| `tools/performance_report.py` | Validates finalized ledger records. |
| `tools/sync_state.py` | State snapshot helper for post-trade updates. |
| `tools/smoke-test-policy-guard.py` | Isolated policy-guard smoke test (no production state touched). |
| `tools/dashboard/app.py` | Local read-only web trading terminal server with portfolio, macro, market, chart, news, alerts, and health endpoints. |
| `tools/dashboard/templates/index.html` | Trading terminal UI with portfolio, P&L, macro, market, chart, news, and alert panels. |
| `tools/dashboard/data_fetcher.py` | Dashboard data layer with graceful API degradation; live reconciliation remains authoritative over dashboard fallback values. |
| `tools/dashboard/docker-compose.yml` | Local dashboard container definition. |
| `tools/dashboard/Dockerfile` | Dashboard image definition. |
| `tools/dashboard/requirements.txt` | Dashboard Python dependencies. |
| `state/position_rules.json` | Tunable active cap, per-trade ratio, fee reserve, loss caps, risk ratios, speculation rules. |
| `state/position_theses.json` | Per-asset rationale, target, invalidation, time horizon, yield plan, risk notes. |
| `buy-evaluation` skill | Hermes pre-buy decision procedure: `BUY`, `DO NOT BUY`, or `RESEARCH MORE`. |
| `wallet-portfolio-briefing` skill | Verified multi-wallet briefing procedure with mandatory live CDP token listing. |

| `tests/` | Regression tests for the policy guard, executor, and dynamic allowlist. |
| `docs/CURRENT_JUPITER_OPERATIONS.md` | Live operational source of truth. |
| `docs/JUPITER_STACK_AUDIT_2026-07-11.md` | Most recent comprehensive audit. |
| `docs/SECURITY.md` | Threat model and operator checklist. |

### Legacy (read-only history, do not execute)

| Path | Purpose |
|------|---------|
| `legacy/` | Deprecated Keplr / Cosmos / Osmosis workflows. Do not run anything here. See `legacy/README.md`. |

## Quick start

```bash
# 1. Clone and install Python deps (Python 3.11+, solders required for executor)
git clone https://github.com/<your-username>/Hermes-trading-agent.git
cd Hermes-trading-agent
python3 -m pip install solders pytest

# 2. Replace example wallet addresses in:
#    - tools/privy_jupiter_executor.py   (EXAMPLE_WALLET)
#    - tests/test_speculative_gate.py     (WALLET)
#    - state/position_rules.json          (verified_balances_snapshot, verified_wallet_nav_usd)
#    - state/position_theses.json         (wallet_snapshot, positions[].mint where applicable)

# 3. Configure your signer (Privy, Turnkey, Openfort, Phantom, etc.)
#    Edit PRIVY_SIGN and PRIVY_SIGN_KWARGS in tools/privy_jupiter_executor.py.

# 4. Review the hard-coded core ALLOWLIST in tools/privy_jupiter_executor.py.
#    New assets must also pass the buy-evaluation procedure and, when needed,
#    a deliberate dynamic-allowlist entry. Never add a token from a ticker alone.

# 5. Run the regression suite before touching real funds
python3 -m pytest tests/ -q
python3 tools/smoke-test-policy-guard.py

# 6. Try a dry-run on your wallet
python3 tools/privy_jupiter_executor.py \
  --wallet <YOUR_PRIVY_SOLANA_WALLET> \
  --thesis-id manual-smoke-1 \
  --input-mint So11111111111111111111111111111111111111112 \
  --output-mint EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v \
  --amount 1000000 \
  --notional-usd 0.08 \
  --wallet-value-usd <YOUR_NAV> \
  --max-loss-usd 0.01 \
  --slippage-bps 50
```

If the dry-run succeeds, the same command with `--execute` appended will sign and broadcast.

## How autonomy is bounded

The owner grants bounded autonomy by:

1. Hard-coding which mints can ever be touched (`ALLOWLIST` in `privy_jupiter_executor.py`).
2. Tuning caps and ratios in `state/position_rules.json` (no code change needed).
3. Letting a supervisor cron dynamically add short-lived, per-mint entries to
   `state/active_allowlist.json` via the dynamic allowlist — every entry has a TTL,
   a per-mint notional cap, mandatory Token-2022 extension inspection, liquidity
   evidence, and is consumed after a single trade.
4. Hard-coded safety floors in `tools/policy_engine.py` that cannot be relaxed by
   the dynamic allowlist: approved programs (System, Compute Budget, ATA, Token,
   Jupiter router), fee-payer check, Jupiter-router presence, transaction
   transaction decoding, unsigned-simulation success, ≤0.5% price impact, ≤100 bps slippage,
   ≤20-second quote age, 0.02 SOL fee reserve, 3% maximum total/active risk, and 5% maximum daily realized loss.

## Hard controls summary

- One-trade filesystem lock (`state/trade.lock`)
- Emergency-stop marker (`state/EMERGENCY_STOP` blocks new trades)
- Fresh quote with measured age, ≤20s TTL
- Wallet fingerprint check (state at quote time == state at sign time)
- Transaction decoding before signing: fee payer, top-level programs, Jupiter router
- Unsigned transaction simulation must succeed
- Minimum output verified against `otherAmountThreshold`
- Post-trade balance reconciliation
- Single-use consumption of dynamic allowlist entries
- Dynamic allowlist kill switch: `python3 tools/dynamic_allowlist_cli.py halt "reason"`

## Profit-take automation (advisory)

A separate tool `tools/profit_take.py` runs in the supervisor loop:

```bash
# Dry-run (what would happen)
python3 tools/profit_take.py

# Execute qualifying profit-takes + allocation advisory
python3 tools/profit_take.py --execute
```

**What it does:**
1. Reads live balances and current prices
2. For each holding with a thesis target/invalidation:
   - Below invalidation → full exit into USDC (urgent)
   - At or above target → take 33% slice into USDC (configurable via `--slice-pct`)
   - Between → HOLD
3. Filters for positive net edge after slippage + priority fee
4. Enforces active cap ($50 default) and per-trade ratio (25% default)
3. On successful trade, runs profit allocation advisory:
   - 50% → USDC stable reserve
   - 25% → reinvestment capital (dry powder)
   - 25% → cbBTC **when USDC reserve > $50** (advisory only)
4. All profit allocation is advisory — the supervisor decides whether to act

**Config** in `state/position_rules.json`:
```json
"profit_allocation": {
  "mode": "advisory",
  "usdc_stable_pct": 50,
  "btc_pct": 25,
  "reinvest_pct": 25,
  "btc_trigger_usdc_reserve": 50.0,
  "btc_target_mint": "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",
  "note": "Loose advisory guidelines — supervisor considers these when allocating realized profits but is not bound by them."
}
```

**Usage:**
```bash
# Dry-run report
python3 tools/profit_take.py

# Execute with allocation advisory
python3 tools/profit_take.py --execute --slice-pct 33
```

## Supervisor context and execution

The autonomous supervisor is not limited to reviewing pre-approved `Ready` cards. Each cycle independently reads the latest market collector, wallet reconciliation, multi-platform readiness, research scans, portfolio risk manager, yield/staking monitor, news monitor, sell/exit, and profit-sweep outputs through its configured context handoff. This prevents generic `HOLD` decisions caused by missing or stale research context.

**Live-data mandate:** Before every report, ranking, or decision, the relevant cron must refresh wallet balances, token accounts, prices, quotes, liquidity, positions, P&L, platform readiness, and current yield/earn rates. Stale, unavailable, or unreconciled information must be labeled explicitly; material decisions must remain `HOLD` until live reconciliation is restored.

**Long-hold utilization:** Every material long-term or extra-long-term holding—not only USDC—must be evaluated for verified staking, liquid staking, governance/voting, lending, Earn, LP/JLP, vault, or other productive-use routes. This includes SOL, JUP, BTC/cbBTC, liquid-staking assets, LP/LST receipts, governance assets, and other verified holdings where applicable. Compare net yield or strategic value against lockup, withdrawal, smart-contract, oracle, validator, borrower/liquidation, custody, depeg, liquidity, and opportunity costs. Preserve liquidity and do not deploy automatically.

The supervisor may consider day trades and multiple simultaneous positions when justified. There is no arbitrary position-count cap; aggregate risk, liquidity, correlation, fee efficiency, reserves, and exit capacity are the constraints. Direct SOL-funded routes may be evaluated when the SOL fee reserve is preserved; zero USDC is not an automatic blocker.

Only verified bounded routes may execute, and every action still requires positive net edge after costs, current balance reconciliation, exact asset identity, route authorization, simulation/preflight, finalized receipt verification, and post-trade reconciliation.

## Dashboard and runtime wrappers

The GitHub repository includes the read-only web trading terminal under `tools/dashboard/`. Start it locally with the dashboard's Docker Compose definition or the Flask entry point; it exposes portfolio, macro, market, chart, news, alerts, and health endpoints.

Hermes scheduler definitions and machine-specific wrapper scripts live under `~/.hermes/cron/` and are intentionally not copied into this repository. They may contain local paths, profile-specific settings, and runtime integration details. Runtime `evidence/`, `logs/`, and dashboard fallback data must not be treated as authoritative over live reconciliation.

The dashboard is an observability surface, not an execution authority. Buys and other position changes must go through the buy-evaluation gate, supervisor authorization, platform-local executor, simulation, and post-trade reconciliation.

## What this does NOT do

- Withdraw to external addresses
- Sweep profits to treasury hardware wallets
- Call arbitrary Solana programs
- Trade Token-2022 mints with transfer hooks, permanent delegates, transfer fees,
  or default-frozen accounts (the dynamic-allowlist writer must reject these)
- Bridge assets
- Open leverage or perpetual positions
- Modify wallet permissions or session keys

## Cron topology

The active Hermes scheduler runs live market collectors, reconciliation and executor-health checks, yield/liquidity and news monitoring, multiple Jupiter research windows, portfolio/risk management, buy-entry evaluation, hourly sell/exit review, profit-sweep evaluation, daily portfolio reporting, and one autonomous execution supervisor. Read-only collectors and research jobs feed the supervisor; only the supervisor may authorize a bounded executor action.

Every buy-capable workflow applies the `buy-evaluation` gate before promotion or execution. The gate returns `BUY`, `DO NOT BUY`, or `RESEARCH MORE`, with risk-proportionate diligence and explicit sizing, maximum loss, invalidation, time stop, and exit route.

The supervisor runs every 2 hours, consumes current collector outputs via `context_from`, validates candidates against the policy guard, and only invokes an executor for fully specified candidates with verified net edge. Runtime evidence and logs remain local and uncommitted.

## License

MIT. See `LICENSE`.

## Disclaimer

This is experimental software. It has been tested with small positions and has lost
nothing, but it can lose everything. Test with dust first, never exceed what you can
afford to lose, and keep a hardware-wallet treasury separate from the agent wallet.