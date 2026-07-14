# Current Jupiter Trading Operations

**Canonical operational status:** 2026-07-13 UTC  
**Active scope:** isolated Privy Solana wallet + Jupiter spot and Jupiter Perps  
**Wallet:** `<SOLANA_WALLET_ADDRESS>`

This document is the current operational source of truth. Older Cosmos/Osmosis and Keplr material remains historical/reference unless the owner explicitly reactivates it.

## 1. Safety and authority boundary

- Autonomous spot execution uses `tools/privy_jupiter_executor.py`; Jupiter Perps execution uses `tools/jupiter_perps_executor.py`.
- Both executors default to dry-run. Signing and broadcast require their explicit execution path.
- Spot token eligibility is route-based: a candidate must have a verified Jupiter route and pass policy/scam checks. The old hard-coded mint allowlist is not the tradability authority.
- `cbBTC` is a long-term BTC-diversification holding, not a prohibited or dust-only asset. Its wrapped-asset custody/reserve/redemption risks must be reviewed before increasing allocation.
- Hard controls: one-trade filesystem lock, emergency-stop marker, fresh quote, wallet fingerprint, state-defined caps, per-trade notional ratio, SOL fee reserve, finalized transaction with `err:null`, minimum-output verification, and post-trade reconciliation.
- Jupiter Perps is active for SOL, WBTC, and ETH. New or changed Perps positions require policy-valid leverage/exposure, **a 100%-size take-profit and 100%-size stop-loss attached before entry finality**, Privy owner signature, Jupiter co-sign/broadcast, finalized Solana verification, and positions-API verification. After a high-impact macro catalyst, the system may open a 3-5% NAV starter only after momentum confirmation; additions require a successful retest, refreshed evidence, and remain within the 10% aggregate Perps cap.
- Prohibited: withdrawals, treasury sweeps, arbitrary contracts, unknown programs, and unverified bridges. No Hyperliquid route is permitted.
- Non-spot products such as Earn/Lend/Stake/LP/JLP/predictions/tokenized assets require feature-specific research and risk gates. Current held JL-USDC is monitored; the generic spot executor does not automate deposits or withdrawals.

### Active Capital Deployment

- The system must not hoard idle USDC or SOL merely because it is reserve. It preserves a minimum **0.02 SOL** transaction-fee reserve and **$10 USDC** operating reserve, then actively evaluates deployment of a bounded slice when live evidence supports positive net edge, sufficient liquidity, defined invalidation, and a verified exit path.
- A qualifying initial spot position may use up to **10% of verified NAV**. A confirmed macro-Perps starter may use **3-5% of NAV**; it retains the separately required full TP/SL, ≤3x leverage, ≥30% liquidation buffer, and retest-only add rule.
- A HOLD remains valid when there is no verified edge. Idle capital alone is never a reason to reject a qualified, policy-valid opportunity.

### Target and Profit-Pull Governance


- **Daily Portfolio Targets and Risk Manager** recalibrates each target/invalidation against live price, volatility, liquidity, concentration, fees, expected dollar profit, and the partial-slice economics.
- **Hourly Sell & Exit Evaluator** performs an immediate re-evaluation after a material price/volatility move, macro surprise, news/tokenomics/security event, liquidity/route deterioration, depeg/validator issue, or concentration change.
- A target may be retained, revised, or classified as **rebalance-only**. Targets whose expected partial-sale profit is below `$1` after costs must be flagged `TARGET_TOO_SMALL_FOR_PROFIT_PULL` rather than treated as an internal harvest trigger.
- Internal system harvesting may retain realized net gains of at least `$1` after costs in the reserve/reinvestment bucket when a target, risk trigger, or verified positive edge supports it. Owner profit transfers, once a dedicated outbound transfer executor is independently verified, require **$20 cumulative realized, finalized, independently reconciled net profit after costs** and are **native SOL on Solana only** to the verified owner destination. Never sweep principal, fee reserve, bridges, Base/Ethereum assets, or another chain.
- Mandatory pre-buy research applies to every coin, token, and tokenized asset before any buy consideration: exact identity, legitimacy, liquidity, costs, exit path, jurisdiction/compliance, and expected net edge must be verified first.
- Small speculative coins are allowed in a separate speculation bucket. Default limits are 2% of verified NAV per speculative position and 5% aggregate speculative exposure, further constrained by the 3% NAV maximum-total-risk rule.
## 2. Exact asset identity

| Asset | Mint/program note |
|---|---|
| SOL | `So11111111111111111111111111111111111111112` |
| USDC | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` |
| JUP | `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` |
| cbBTC | `cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij` |
| JupSOL | `jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v` |
| JL-USDC receipt | `9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D` |
| ANSEM | `9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump` — Token-2022; **not JupSOL** |

Every reconciliation must query both classic SPL Token and Token-2022.

## 3. Execution workflow

1. Collect current prices, news, wallet balances, yield, liquidity, and status.
2. Research jobs are read-only. They may update evidence and Kanban and promote a fully specified candidate to `Ready`; they never sign or broadcast.
3. Risk manager is read-only and updates adaptive rules.
4. Supervisor revalidates every Ready card with fresh data.
5. Run executor without `--execute`:

```bash
python3 tools/privy_jupiter_executor.py \
  --wallet <SOLANA_WALLET_ADDRESS> \
  --thesis-id <STABLE_THESIS_OR_KANBAN_ID> \
  --input-mint <EXACT_MINT> \
  --output-mint <EXACT_MINT> \
  --amount <RAW_AMOUNT> \
  --notional-usd <CURRENT_NOTIONAL> \
  --wallet-value-usd <CURRENT_NAV> \
  --max-loss-usd <THESIS_MAX_LOSS> \
  --slippage-bps <APPROVED_BPS>
```

6. Only if the dry-run and every policy/thesis gate pass, obtain a fresh quote and rerun with `--execute`.
7. Success requires finalized `err:null`, verified output at or above minimum, fee reserve intact, reconciled balances, ledger append, thesis update, and Kanban transition.
8. A scheduler `OK`, Privy response, returned signature, or UI change is not proof of a trade.

## 4. Cron architecture

### Collectors

| Job | ID | Schedule | Model |
|---|---|---|---|
| Price/market monitor | `360ea3632ee7` | every 2h | MiniMax M2.7 Pro |
| Portfolio reconciliation/executor health | `2c0fe6ae5f07` | every 2h | MiniMax M2.7 Pro |
| Yield/staking/liquidity | `4d6410b88412` | every 4h | MiniMax M2.7 Pro |
| News/market impact | `a91726db6f05` | every 4h | MiniMax M2.7 Pro |
| Overnight collector | `9207808c3231` | 22:00 ET | MiniMax M2.7 Pro |
| Weekday midday collector | `d0a681dd5281` | 12:30 ET | MiniMax M2.7 Pro |

### Read-only research and risk

| Job | ID | Schedule |
|---|---|---|
| Overnight research | `924ad8a43819` | 02:00 ET |
| Morning open | `8406c57fbed3` | 06:00 ET |
| Portfolio targets/risk | `10eed04c5db2` | 07:30 ET |
| Weekday day-trade open | `b2822ae47aba` | 09:30 ET |
| Morning/midday research | `e995d46f5380` | 10:00 ET |
| Afternoon research | `e2ebd0513b04` | 14:00 ET |
| Weekday day-trade PM | `7868408e20fc` | 15:30 ET |
| Evening research | `e907460f3ed8` | 18:00 ET |

### Execution supervisor

- `a1de626cbce6`, every 2 hours, GPT-5.6 Luna.
- Receives latest collector/research/risk outputs through `context_from`.
- Only component authorized to invoke the bounded executor.
- Must process each reviewed Ready card into Executing, Monitoring/Completed, or Blocked/HOLD in the same cycle.

All Telegram outputs use compact line-limited templates; detailed evidence belongs in `docs/kanban-evidence/`, state files, and logs.

## 5. Yield accounting

Every portfolio/risk/reconciliation report must include:

- JL-USDC current underlying value, supply rate, rewards rate, total rate, withdrawal liquidity, and annual USD-equivalent yield.
- JupSOL current value, JupSOL/SOL conversion ratio, and a defensible APY source. A single exchange-rate snapshot is not an APY; use documented current staking rate or measured ratio growth over a valid interval and label uncertainty.
- Total weighted portfolio APY: `sum(position_value × APY) / NAV`.
- Annual USD-equivalent yield: `sum(position_value × APY)`.
- Basis-point contribution to NAV for each yield-bearing position.

Never infer yield from receipt-token premium alone; JL-USDC conversion value is accrued underlying value, while APY is a rate over time.

## 5a. Earn deposit and withdraw flow

JL-USDC Earn deposits and withdrawals are executed via Jupiter's router rather than a direct protocol call: the swap route for `USDC → JL-USDC` and `JL-USDC → USDC` is `Jupiter Lend Earn` directly, so the existing executor handles both directions as a normal spot swap.

Operational sequence for any JL-USDC rebalance:

1. Write a dynamic allowlist entry for `JL-USDC` (`9BEcn9aPEmhSPbPQeFGjidRiEKki46fVQDyPpSQXPA2D`) with the desired per-trade notional cap and a TTL up to 24 hours. The mint is not in the hard-coded allowlist, so it cannot be traded without this step.
2. Run the bounded executor with `input_mint` and `output_mint` set to either side. Pre-flight checks, program allowlist, transaction decoding, simulation, and post-trade verification all apply normally.
3. After the trade finalizes, the dynamic allowlist entry is consumed (single-use). A follow-up rebalance requires a fresh entry.

Required policy gates: the notional must satisfy both the active USD cap from `state/position_rules.json` (hard floor $50) and the per-trade wallet ratio from the same file (hard floor 25%). On the current ~$64 wallet that gives a maximum ~$16 single-trade notional.

## 6. Opportunity and arbitrage gate

Scans cover spot, stablecoins, liquid-staking dislocations, synchronized route/venue arbitrage, Earn/Lend/Stake, LP/JLP, prediction markets, tokenized assets, and Jupiter ecosystem products.

A candidate requires exact mint/program, issuer/backing/economic rights, entry, target, invalidation, maximum loss, size, current liquidity, all costs, and complete exit/redemption. Arbitrage must use synchronized two-way quotes and remain positive after fees, spread, slippage, priority fee, latency, MEV, inventory, liquidity, settlement, depeg, and failure-to-fill risk. Headline or unsynchronized spreads do not qualify.

## 7. State and evidence

- `state/position_theses.json`: holdings, exact mints, rationale, risks, yield and exit plans.
- `state/position_rules.json`: active cap and risk limits.
- `logs/trade_ledger.jsonl`: append-only action records. Do not infer realized P&L from entries that lack a closed position.
- `docs/JUPITER_KANBAN.md`: project trading lifecycle and evidence archive.
- `~/.hermes/kanban.db`: dashboard task store; separate from the markdown board.
- `docs/kanban-evidence/`: timestamped detailed research/reconciliation artifacts.

## 8. Health commands

```bash
python3 -m pytest tests/test_policy_executor.py -q
python3 tools/smoke-test-policy-guard.py
python3 tools/policy_engine.py status
hermes kanban stats
hermes cronjob list
```

Safe executor test: run the command in section 3 without `--execute`. Never use a made-up NAV, notional, maximum loss, mint, or raw amount.

## 9. Current known limitations

- JL-USDC Earn deposits/withdrawals work through the dynamic allowlist + Jupiter router (route `Jupiter Lend Earn`); no dedicated protocol-call executor yet, so each rebalance consumes a dynamic-allowlist entry. A direct-protocol Earn path would skip the dynamic-allowlist hop but adds Anchor discriminator handling and is not yet built.
- Staking (JupSOL), LP/JLP, prediction markets, tokenized assets, bridges, Base, and perps do not have a generic bounded executor and remain research-only unless a separate verified path is built.
- Realized daily P&L and two-loss counting are policy requirements but need reliable closed-position accounting before they can be derived automatically; the supervisor must not invent them.
- Jupiter/Privy/external endpoints can fail or change. Preserve errors verbatim and HOLD on stale or conflicting data.
- Live on-chain reconciliation is authoritative; historical snapshots in evidence files must not be used as current balances. If `state/position_rules.json`, `state/position_theses.json`, ledger, and RPC disagree, the supervisor must reconcile from both SPL token programs and native SOL before considering any Ready card. Stale or conflicting state is a HOLD condition.
- Dashboard Kanban and markdown Kanban are separate; both must be checked to avoid stranded Ready work.
- Cross-platform coordination is defined in `docs/MULTI_PLATFORM_PROTOCOL.md` and `state/platforms.json`. The supervisor may compare platform opportunities, but each platform retains its own signer/executor; Coinbase/CDP Base is enabled only for the bounded USDC→WETH executor, while every other Base venue remains separately gated.
