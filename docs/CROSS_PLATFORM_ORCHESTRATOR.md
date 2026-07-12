# Cross-Platform Orchestrator v1

## Scope

The orchestrator coordinates Jupiter/Solana and Coinbase/Base without merging signers. It adds:

- normalized platform reports;
- Mixture-of-Agents (MoA) candidate review;
- independent risk voting;
- event-trigger evaluation;
- dry-run simulation and backtesting interfaces;
- dashboard-ready JSON outputs;
- global audit records.

## Shared worker pool

The same bounded workers review every platform and chain:

- `market`
- `portfolio`
- `protocol`
- `execution`
- `transfer` when cross-platform movement is proposed

Workers consume the normalized candidate contract and return the same vote schema regardless of venue. They do not become platform-specific agents and they do not receive signer access.

```text
Jupiter / Solana   ┐
Coinbase / Base    │
Robinhood / MCP    ├─> shared normalized candidate -> shared MoA workers -> shared risk gate
TRONLink / SunSwap ┘                                      -> local adapter only
```

Platform differences are represented as adapter metadata: chain, asset identity, quote source, fee asset, signer, executor, and verification method. The global protocol, worker roles, budgets, consensus rules, audit fields, and kill switches remain shared.

## Decision pipeline

```text
platform collectors
  -> normalized snapshots
  -> candidate generation
  -> independent market/risk/protocol/execution reviews
  -> risk vote
  -> simulation/backtest
  -> global policy gate
  -> platform-local dry-run
  -> platform-local executor
  -> independent verification
  -> ledger + dashboard
```

MoA adds evidence and disagreement detection. In Hermes, run independent perspectives with `delegate_task` for bounded reviews or separate `hermes chat -q` processes for durable work. Use `cronjob` with `context_from` to pass collector outputs into the synthesizer. Use the Hermes Kanban board for durable candidate state and worker ownership. MoA never overrides hard stops, jurisdiction restrictions, stale data, unsupported assets, or platform-local policy.

## Risk voting

Each candidate receives votes from separate dimensions:

- market: trend, volatility, liquidity, catalyst;
- portfolio: concentration, NAV, drawdown, reserve;
- protocol: contract, oracle, custody, issuer, bridge, and redemption risks;
- execution: quote freshness, route, fees, slippage, finality, and failure recovery.

A candidate is execution-eligible only when all required dimensions pass and no hard stop is present. A disagreement becomes `REVIEW` or `HOLD`, never an automatic trade.

## Event triggers

Triggers are read-only until a candidate passes the same policy gate as a scheduled trade. Examples:

- price/target/invalidation crossing;
- liquidity or spread threshold;
- stablecoin depeg;
- validator or protocol incident;
- abnormal volatility;
- stale or conflicting wallet data;
- news/security event;
- platform outage or jurisdiction change.

## Simulation and backtesting

Simulation must use recorded historical snapshots and explicit assumptions. It must report fees, slippage, latency, fill assumptions, and failure cases. Backtest output is research evidence only; it does not authorize live execution.

## Dashboard contract

The dashboard should consume normalized JSON containing:

```text
platforms
wallets
nav
exposures
candidates
moa_votes
risk_decision
triggers
simulation
backtest
execution_status
verification
```

## Safety boundary

Only a verified platform adapter may sign. The orchestrator may not hold secrets, create generic transactions, bridge assets, withdraw funds, or bypass platform-local executors.
