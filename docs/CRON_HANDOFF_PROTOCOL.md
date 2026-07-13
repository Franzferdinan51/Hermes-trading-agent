# Cross-Cron Shared Handoff Protocol

`state/cron_handoff.md` is the append-only, human-readable operating history for the crypto stack. `state/cron_handoff.jsonl` contains the same records for programmatic review. Every record is UTC-dated, tagged by domain, tied to the job that produced it, and preserves the facts needed by a later cron to understand what happened, when it happened, why it mattered, and what remains to be done.

## Mandatory cycle behavior

Every trading, monitoring, research, risk, news, reconciliation, yield, execution, and portfolio cron must:

1. Read the most recent twelve entries before its analysis:
   ```bash
   python3 tools/cron_handoff.py read --limit 12
   ```
2. Refresh its own live sources; the shared ledger never overrides authoritative live APIs, wallet balances, quotes, or positions.
3. Append one detailed record before completing:
   ```bash
   python3 tools/cron_handoff.py append \
     --job 'Exact Cron Job Name' \
     --tag 'MARKET' \
     --status 'WATCH' \
     --summary 'One-sentence conclusion.' \
     --details 'Concrete result, change since prior run, rationale, and next trigger.' \
     --facts '{"price_usd":74.56,"source":"Jupiter"}'
   ```

Use single quotes around every argument passed through the shell. This preserves dollar signs, JSON, and punctuation without shell expansion.

## Standard tags and required facts

| Tag | Use | Minimum facts to hand off |
|---|---|---|
| `PERPS` | Open Perps positions, TP/SL, liquidation, P/L | asset, side, size/equity, entry, mark, P/L, liquidation, TP, stop, protection state |
| `MARKET` | Prices, trend, volume, support/resistance, correlation | assets/prices, change window, trend level, source, next trigger |
| `NEWS` | Catalysts, CPI/Fed, regulatory/security developments | source/date, event, expected market impact, confidence, action window |
| `RISK` | Exposure, concentration, reserves, invalidations | NAV basis, exposure, reserve, breach/none, required action |
| `RECONCILIATION` | Balance or state corrections | source, before/after, discrepancy, file updated, verification |
| `YIELD` | Lend/stake/LP diligence | protocol, asset, APY source, liquidity/exit risk, readiness |
| `EXECUTION` | Any build/sign/broadcast/settlement attempt | intent, route, amount, policy checks, signature, finality, post-state |
| `PORTFOLIO` | NAV, allocation, profit sweep, treasury action | Solana/Base/combined NAV, Perps equity, material changes, decision |
| `SECURITY` | Exploit, scam, wallet, or protocol threat | source, affected assets, severity, exposure, mitigation |
| `WALLET` | Wallet changes, fee reserve, token-account observations | wallet scope, balance deltas, fee reserve, source, Perps state |
| `READINESS` | Adapter/venue availability and blockers | venue, capability, test result, blocker, next verification |
| `MEMORY` | Brain pruning or reflection lifecycle only | operation, safe aggregate counts, errors, next action |
| `REPORT` | Consolidated daily or cross-venue report | NAV basis, positions, material events, decisions, open items |

## Kanban coordination

Every scheduled job also checks `hermes kanban list` at the start of its cycle. Kanban is the actionable-work layer: a material `WATCH`, `ALERT`, blocker, discrepancy, security event, or research finding that needs follow-up must create or update a card, with evidence and UTC timing. A routine healthy/HOLD cycle stays in the handoff ledger and does not create noise cards; verified resolutions complete their Kanban card and record its ID in the ledger.

## Cross-cron dependency rules

- The hourly Perps monitor writes `state/perps_monitor_latest.json` and `state/perps_monitor_latest.md` in addition to its `PERPS` ledger record.
- Supervisor, Sell/Exit, Price, Risk, News, and Profit Sweep receive the monitor output with `context_from` and must read the shared Perps files before a Perps conclusion.
- Portfolio reports include Perps **equity** (`collateralUsd + pnlAfterFeesUsd`), not full borrowed notional.
- A cron may append a correction to an earlier record but must never rewrite or delete history.
- Missing live data, a failed adapter, or a stale source must be explicitly recorded with tag, timestamp, error, effect, and next check.

## Reading history

Use `read_file` for a targeted historical review and `search_files` to locate prior tagged events. The `cron_handoff.py read` command is the fastest view of recent records.

```bash
python3 tools/cron_handoff.py read --limit 25
```
