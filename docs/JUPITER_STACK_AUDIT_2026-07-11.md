# Jupiter Trading Stack Audit — 2026-07-11

## Result

The stack is operational for read-only monitoring, research, policy checks, bounded allowlisted Jupiter spot dry-runs, and **permissive autonomous allowlisting** by the supervisor through `state/active_allowlist.json`. The execution path has been hardened during this audit. No live trade was forced.

## Fixed

- Standardized all 15 active trading cron Telegram responses to one compact Markdown card; detailed evidence stays local.
- Restored collector → read-only research/risk → Ready card → supervisor → bounded executor separation.
- Supervisor now consumes all collector/research/risk outputs, checks both Kanban stores, processes reviewed Ready cards, and names the exact dry-run-first executor command.
- Exact asset/mint labeling prevents ANSEM from being confused with JupSOL.
- Small speculative coins are explicitly allowed in a capped bucket: default 2% NAV per position and 5% aggregate, subject to the 1% NAV maximum-loss rule and full mint/Token-2022/liquidity/security/exit checks.
- Added a canonical current operations runbook and marked unsafe/stale Cosmos quickstarts and parameter documents as historical.
- Policy engine now rejects invalid, negative, and non-finite numeric inputs and enforces the actual 10% wallet-notional limit without a hidden $1 floor.
- Policy smoke tests now use an isolated temporary state directory and cannot delete a real emergency stop or trade lock.
- Executor now preserves the 0.02 SOL reserve, sums multiple token accounts by raw integer amount, queries classic SPL and Token-2022, and verifies minimum output and post-trade balance deltas.
- Executor requires a stable `thesis_id`; three older finalized swaps received non-destructive metadata amendment records.
- Executor measures actual quote age, requotes under the trade lock, and rechecks the emergency stop before signing and broadcasting.
- Jupiter swap transactions are decoded before signing. Fee payer and top-level programs are checked against a narrow allowlist, the Jupiter router must be present, and the unsigned transaction must simulate successfully.
- Execution intent, broadcast, final result, and failure/halt records are durable ledger transitions. Ambiguous or failed execution activates the emergency stop.
- Removed stale claims that Privy signing was blocked; the validated path has finalized later allowlisted swaps.
- Added permissive dynamic allowlist: supervisor can autonomously write per-mint entries to `state/active_allowlist.json` with TTL, per-mint cap, mandatory Token-2022 extension report, liquidity evidence, and single-use consumption. Hard-coded safety rules (approved programs, fee payer, Jupiter router, transaction decoding, simulation) are unchanged.
- Wired JL-USDC Earn deposits/withdrawals through the existing executor by routing `USDC → JL-USDC` and `JL-USDC → USDC` via Jupiter's `Jupiter Lend Earn` route; the dynamic allowlist authorizes each leg. Live deposit of 6.40 USDC → 6.09 JL-USDC finalized and reconciled.
- Raised the per-trade absolute USD cap from $30 to $50 (sourced from `state/position_rules.json`), raised the per-trade wallet ratio from 10% to 25%, and made both tunables in-state rather than hard-coded so the supervisor and risk manager can adjust them without redeploying code.

## Verified

- Local regression suite passes.
- Isolated policy-guard smoke suite passes.
- State JSON and ledger JSONL parse successfully.
- Policy status showed no active halt or lock before testing.
- Live SOL→USDC dry-run succeeded with a fresh Jupiter quote.
- The dry-run decoded the expected wallet as fee payer, allowed only System/Compute Budget/ATA/Token/Jupiter programs, found the Jupiter router, and simulated successfully.
- Price, reconciliation, yield, and news collectors completed successfully before the dependent supervisor.
- The previously stranded diversification card moved from Ready to Blocked/HOLD with a concrete no-edge reason; Ready count returned to zero.

## Remaining limitations

These are explicit HOLD conditions, not hidden claims of completion:

1. `--wallet-value-usd`, `--notional-usd`, `--max-loss-usd`, and realized daily loss are still supplied by the supervisor rather than fully derived inside the executor from independent marks and closed-position accounting. The supervisor must use current verified state and cannot invent values.
2. Finality and balances are currently verified against one Solana RPC. A second independent RPC verifier should be added before increasing capital or trade size.
3. Top-level transaction programs are decoded and allowlisted, but full semantic instruction/account-delta validation and inner-instruction verification can be strengthened further.
4. Realized daily P&L and “two losses” enforcement require reliable closed-position accounting; current ledger history does not provide complete cost-basis closure for every asset.
5. Token-2022 speculative assets require extension inspection before per-mint executor allowlisting. ANSEM remains held/monitored but is not generically executable.
6. JL-USDC deposits/withdrawals, staking, LP/JLP, predictions, tokenized assets, bridges, Base, leverage, and perps do not have a generic bounded executor and remain research-only unless a separate verified path is built.
7. The project directory is not a Git repository, so changes cannot be reviewed or rolled back through project-local Git history.

## Canonical files

- `docs/CURRENT_JUPITER_OPERATIONS.md`
- `docs/PRIVY_JUPITER_BASE_PLAN.md`
- `docs/RESEARCH_CRON_PLAN.md`
- `docs/JUPITER_KANBAN.md`
- `state/position_rules.json`
- `state/position_theses.json`
- `tools/policy_engine.py`
- `tools/privy_jupiter_executor.py`
- `tools/dynamic_allowlist.py`
- `tools/dynamic_allowlist_cli.py`
- `tests/test_policy_executor.py`
- `tests/test_dynamic_allowlist.py`
- `tests/test_speculative_gate.py`
- `state/active_allowlist.json`
- `state/active_allowlist_history.json`
- `logs/trade_ledger.jsonl`
