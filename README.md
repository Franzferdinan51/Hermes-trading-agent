# Hermes Trading Agent

A bounded, policy-controlled crypto trading agent for **Solana via Jupiter**, with a
permissive dynamic allowlist for opportunistic trades and a hard-coded core allowlist
for routine rebalancing. Built around a small set of guardrails (allowlisted mints,
file locks, emergency stop, fresh quotes, decoded transactions, simulation, finalized
reconciliation) so a runaway or hallucinated prompt cannot move funds outside what the
owner has approved.

> This repository is a fork-and-configure template. Replace the example wallet addresses
> with your own before doing anything. Do not deposit funds into any address that appears
> in the documentation — those are placeholders.

## Scope

- **Active:** Solana via Jupiter aggregator (spot swaps, JL-USDC Earn deposits/withdrawals,
  dynamic-allowlist opportunistic trades). Use this.
- **Legacy (do not use):** Keplr / Cosmos / Osmosis workflows are preserved under
  `legacy/` for the historical record only. They are explicitly deprecated and ignored
  by the active code path.

## What's in here

### Active (use this)

| Path | Purpose |
|------|---------|
| `tools/privy_jupiter_executor.py` | The bounded executor. Hard-coded mint allowlist, dynamic per-mint runtime allowlist, transaction decoding, simulation, fee-payer check, Jupiter-router enforcement, minimum-output verification, post-trade balance reconciliation, single-use consumption of dynamic entries. |
| `tools/policy_engine.py` | The preflight guard. Numeric validation, quote-age cap, price-impact cap, slippage cap, notional/risk ratios (sourced from `state/position_rules.json`), one-trade filesystem lock, emergency-stop marker. |
| `tools/dynamic_allowlist.py` | Runtime per-mint allowlist managed by the supervisor. TTL cap, per-mint notional cap, mandatory Token-2022 extension report, single-use consumption, kill switch. |
| `tools/dynamic_allowlist_cli.py` | Operator CLI for the dynamic allowlist (`halt`, `resume`, `status`, `list`, `show`, `purge-expired`). |
| `tools/trade_ledger.py` | Append-only ledger of action records; rejects malformed finalized entries. |
| `tools/jupiter_api.py` | Thin wrapper around Jupiter Lite API endpoints. |
| `tools/price-monitor.py` | Reads prices and writes a JSONL log. |
| `tools/performance_report.py` | Validates finalized ledger records. |
| `tools/sync_state.py` | State snapshot helper for post-trade updates. |
| `tools/smoke-test-policy-guard.py` | Isolated policy-guard smoke test (no production state touched). |
| `state/position_rules.json` | Tunable active cap, per-trade ratio, fee reserve, loss caps, risk ratios, speculation rules. |
| `state/position_theses.json` | Per-asset rationale, target, invalidation, time horizon, yield plan, risk notes. |
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

# 4. Edit the hard-coded ALLOWLIST in tools/privy_jupiter_executor.py
#    to include the mints you want to trade. The five defaults are
#    SOL, USDC, JUP, cbBTC, JupSOL.

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
   decoding, unsigned-simulation success, ≤0.5% price impact, ≤100 bps slippage,
   ≤20-second quote age, 0.02 SOL fee reserve, 1% NAV max loss, 2% daily realized loss.

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

## What this does NOT do

- Withdraw to external addresses
- Sweep profits to treasury hardware wallets
- Call arbitrary Solana programs
- Trade Token-2022 mints with transfer hooks, permanent delegates, transfer fees,
  or default-frozen accounts (the dynamic-allowlist writer must reject these)
- Bridge assets
- Open leverage or perpetual positions
- Modify wallet permissions or session keys

## Cron topology (original Hermes agent)

The original Hermes agent ran 15+ scheduled jobs across two model families:

- **MiniMax M2.7 Pro** (cheap collectors): price, reconciliation, yield/staking, news
- **GPT-5.6 Luna** (synthesis + decisions): research windows, day-trading, risk manager,
  autonomous execution supervisor

The supervisor runs every 2 hours, consumes collector outputs via `context_from`, validates
candidates against the policy guard, and only invokes the executor for fully-specified
Ready cards with verified net edge. This template ships the executor and policy guard —
the cron orchestration and supervisor prompts are part of the Hermes Agent skill
(`hermes-agent`) and are not bundled here.

## License

MIT. See `LICENSE`.

## Disclaimer

This is experimental software. It has been tested with small positions and has lost
nothing, but it can lose everything. Test with dust first, never exceed what you can
afford to lose, and keep a hardware-wallet treasury separate from the agent wallet.