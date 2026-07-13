# Jupiter Perps Operations and Monitoring

> **Status:** Active on Solana mainnet. This runbook governs live SOL, WBTC, and ETH perpetual positions through Jupiter Perps v2.

## Supported markets and adapter

| Market | Jupiter Perps v2 mint | Status |
|---|---|---|
| SOL | `So11111111111111111111111111111111111111112` | Active |
| WBTC | `3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh` | Active |
| ETH | `7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs` | Active |

- Market/position API: `https://perps-api.jup.ag/v2`
- Executor: `tools/jupiter_perps_executor.py`
- Guardian: `tools/jupiter_perps_guardian.py`
- Wallet signing: Privy managed Solana wallet only.
- No Hyperliquid, bridge, arbitrary contract, withdrawal, or direct private-key flow is permitted.

## Required transaction path

Jupiter Perps transactions have multiple required signatures. The Privy wallet provides the owner signature and Jupiter provides a required co-signature. **Direct Solana RPC `sendTransaction` is invalid for this flow** because it lacks Jupiter's co-signature.

```text
1. POST /positions/increase or /positions/decrease creates an unsigned transaction
2. Privy signTransaction signs the owner slot
3. POST /transaction/execute with the signed transaction
4. Jupiter completes its co-signature and broadcasts
5. Verify finalized Solana signature
6. Independently query /positions to verify the actual position and TP/SL orders
```

An API response, Privy hash, or a submitted-looking RPC value is never considered success by itself. A trade is successful only when both the Solana transaction finalizes without error and Jupiter's positions API reports the expected state.

## Position-entry procedure

1. **Collect live evidence:** Jupiter Perps market data, BTC/ETH correlation, SOL trend/volume, Fear & Greed, macro calendar, CPI/Fed or other high-impact events, news/security events, fees, and liquidation buffer.
2. **Select a directional setup:**
   - Long only after confirmed reclaim/breakout or a verified support reversal with favorable macro confirmation.
   - Short only after confirmed breakdown/rejection with correlated weakness. Do not chase a decline directly into support.
3. **Use policy bounds:** max 3x leverage, maximum aggregate Perps exposure 10% of live NAV, and a minimum 30% liquidation buffer. Jupiter currently requires collateral of at least $10 and leverage greater than 1.1x.
4. **Require a full TP and full stop-loss** at creation. Both must cover 100% of the position.
5. **Build quote and inspect:** verify side, collateral, actual leverage, entry/mark, liquidation price, price impact, opening fee, TP, stop, and expected size.
6. **Execute only through the required transaction path** above.
7. **Verify independently:** finalized Solana result plus `/positions` result. Record evidence, timestamp, position pubkey, TP/SL order IDs, and real P/L.

## Perps valuation in portfolio reports

Portfolio, profit-sweep, and risk reports include every open Perps position using **Perps equity**: `collateralUsd + pnlAfterFeesUsd`. They must not add full notional position size, because that double-counts borrowed exposure. If live equity is unavailable, label NAV incomplete rather than silently excluding the position.

## Monitoring while a position is open

### First line: hourly MiniMax M2.7 monitor

Cron: **Jupiter Perps Position Monitor - Hourly** (`e08ffb7be83e`)

It uses **MiniMax M2.7** plus a read-only position script. Every hour it emits a compact Telegram card while a position is open and writes the same authoritative snapshot to `state/perps_monitor_latest.json` and `state/perps_monitor_latest.md`. The supervisor, exit evaluator, price monitor, risk manager, news monitor, and profit-sweep evaluator receive its latest cron output through `context_from`; they must also read the shared state file when making a Perps conclusion. It reports and escalates:

- Jupiter's positions API cannot be read;
- a position is missing a full 100% TP or stop-loss;
- mark price is within 0.75% of a TP or stop trigger; or
- the liquidation buffer falls below 30%.

The guardian never opens, changes, or closes trades.

### Decision layers

| Job | Frequency | Responsibility |
|---|---:|---|
| Perps Position Monitor | 1 hour | MiniMax M2.7 read-only position, TP/SL, trigger, liquidation, and macro report |
| Sell and Exit Evaluator | Hourly | Live position and exit/thesis review |
| Supervisor | 2 hours | GPT Luna execution authority; may change a policy-valid position after verification |
| Price Monitor | 2 hours | Trend, volatility, support/resistance, BTC/ETH correlation |
| News Monitor | 4 hours | Macro, CPI/Fed, security, regulatory, and catalyst risk |
| Risk Manager | Daily | Aggregate exposure, reserve, liquidation, and allocation review |

No Perps guardian may be disabled while a position is open.

## Immediate response rules

| Event | Required response |
|---|---|
| TP or stop triggers | Confirm finalized close and Jupiter position disappearance; reconcile USDC/P&L before any new trade |
| Missing TP/SL | Critical alert; block new Perps entries and obtain a supervisor protection-repair decision |
| Guardian/API outage | Do not add exposure; restore live position visibility before modifying a position |
| Mark within 0.75% of TP/SL | Alert; watch settlement and do not interfere unless there is a verified order problem |
| Macro shock / security event | Re-evaluate exposure, correlation, liquidity, and exit path before any discretionary action |
| Any confirmation mismatch | Treat execution as failed/unconfirmed; do not retry blindly or duplicate the position |

## Current live test position (reconcile, do not treat as static)

A successful minimum-size live adapter test opened a SOL short with about $10 USDC collateral and roughly $12 exposure at about 1.19x leverage. It has a $71.50 full TP and a $75.25 full stop. Its current state must always be read from `tools/jupiter_perps_executor.py positions`; this document is not an authoritative position ledger.
