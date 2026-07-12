# Multi-Platform Trading Protocol

**Status:** additive cross-management layer; Jupiter/Solana remains active, Coinbase/Base is configured but execution-disabled until funded and verified.

## Purpose

This protocol gives the supervisor one portfolio view across multiple platforms without merging private keys or assuming that assets on different chains are interchangeable. It provides a common lifecycle for discovery, reconciliation, thesis review, platform-local execution, and independent verification.

## Platform registry

The canonical registry is:

```text
state/platforms.json
```

The read-only wrapper is:

```text
tools/platform_orchestrator.py
```

Invoke it through the `terminal` tool:

```text
python3 tools/platform_orchestrator.py snapshot
python3 tools/platform_orchestrator.py evaluate <candidate-json>
```

The wrapper loads the registry, produces normalized dashboard-ready state, applies the MoA decision gate, and forces HOLD when the selected platform is not execution-enabled. It never signs, broadcasts, bridges, withdraws, or changes wallet permissions.

The read-only registry tool is:

```text
tools/platform_registry.py
```

Invoke it through the `terminal` tool:

```text
python3 tools/platform_registry.py
```

## Current platforms

| Platform | Chain | Wallet/signer | Status | Execution |
|---|---|---|---|---|
| Jupiter | Solana | Privy | active | enabled through `tools/privy_jupiter_executor.py` |
| Coinbase/CDP | Base, chain ID 8453 | Coinbase CDP `base-agent` | configured, unfunded | disabled pending funding and transaction verification |

Jupiter and Coinbase keep separate wallets, asset identities, fee reserves, policies, and executors. The common supervisor may compare their balances and opportunities, but it may not use a platform’s signer for another platform.

## Common lifecycle

1. **Discover:** collect current platform data, prices, liquidity, fees, news, and protocol status.
2. **Identify:** record chain, exact mint/contract, token standard, decimals, issuer/protocol, and custody path.
3. **Reconcile:** query the platform’s authoritative balance source and compare it with state, ledger, and collector outputs.
4. **Thesis:** record role, entry/reference, target, invalidation, maximum loss, time horizon, utility, and complete exit path.
5. **Compare:** calculate portfolio concentration, global risk, cross-platform price differences, transfer costs, latency, settlement, bridge risk, and liquidity.
6. **Select platform:** choose the platform only when its jurisdiction, asset support, route, fees, and executor are verified.
7. **Dry-run:** use the platform-local executor in preview mode; inspect exact destination, asset, amount, route, slippage, fees, signer, and policy result.
8. **Execute:** only the platform-local executor may sign; no generic cross-platform signer exists.
9. **Verify:** require finalized transaction status, independent balance reconciliation, ledger entry, thesis update, and platform evidence.
10. **Coordinate:** update the global portfolio view and platform-local state. A cross-platform transfer is a separate action, never an implicit rebalance.

## Global rules

- Global maximum risk: 1% of verified NAV per trade.
- Global maximum realized daily loss: 2% of verified NAV.
- Require current balance reconciliation before every action.
- Require exact asset identity; symbols are insufficient.
- No autonomous withdrawals, treasury sweeps, bridges, or arbitrary contract calls.
- Cross-platform arbitrage must remain positive after trading fees, transfer/bridge costs, spread, slippage, latency, inventory, settlement, depeg, and failure-to-fill risk.
- A platform with stale or conflicting data is HOLD/BLOCKED, not eligible for execution.
- Platform-local policy can be stricter than the global policy.
- Base remains disabled until a small funding test, Base balance verification, policy review, and a successful read-only/dry-run path are complete.

## Platform adapter contract

Each future platform must provide these documented fields before it can be added:

```text
platform_id
chain_or_network
wallet_address
signer_provider
supported_assets
balance_source
market_data_source
quote_or_order_source
executor_command_or_api
fee_asset
risk_limits
jurisdiction_status
post_trade_verifiers
execution_enabled
```

A new platform starts as `research_only` or `configured_unfunded`. It cannot be marked `enabled_for_execution` until its adapter has passed balance, quote, dry-run, signer, finality, and reconciliation tests.

## Future platform onboarding

For every new platform, create a platform entry in `state/platforms.json`, a platform-specific protocol document, a read-only collector, and a bounded executor or documented manual boundary. Add its collector output to the supervisor’s `context_from` list only after the collector has a verified output schema. Add execution only after the platform-specific gate passes.

## Verification

Invoke through the `terminal` tool:

```text
python3 tools/platform_registry.py
```

The output must show Jupiter as the only execution-enabled platform until Base funding and verification are completed. Run the existing Jupiter tests separately:

```text
python3 -m pytest tests/test_policy_executor.py -q
```
