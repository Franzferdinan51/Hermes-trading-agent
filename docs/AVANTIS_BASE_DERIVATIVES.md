# Base Derivatives Research: Avantis

## Finding

The strongest current Base-native perpetuals candidate found is **Avantis**, a perpetual futures DEX on Base using USDC collateral. Its documented markets include crypto and other categories; it exposes data and transaction-builder surfaces for agent integrations.

Official references:

- Base Avantis plugin: `https://docs.base.org/agents/plugins/native/avantis`
- Avantis docs: `https://docs.avantisfi.com`
- Avantis data API: `https://data.avantisfi.com`
- Avantis core API: `https://core.avantisfi.com`
- Avantis history/API: `https://api.avantisfi.com`
- Avantis transaction builder: `https://tx-builder.avantisfi.com`
- Avantis integration SDK: `https://github.com/Avantis-Labs/avantisfi-integration`

## What the Coinbase Base wallet can do

The funded CDP Base wallet can serve as the wallet/collateral account for a future Avantis adapter. The current Coinbase Agentic Wallet CLI/CDP wrapper does not provide a native `perp` command, so Avantis must be integrated as a separate protocol adapter.

## Current status

```text
avantis_base: research_only_disabled
collateral: USDC
wallet_adapter: coinbase_base
enabled_for_execution: false
```

## Required adapter gates

Before any leverage or live position:

1. Read pair configuration, oracle/mark price, max leverage, fees, funding/base fees, collateral rules, and liquidation thresholds.
2. Read current positions, PnL, open orders, and account health.
3. Build unsigned calldata through the documented transaction-builder/SDK path.
4. Decode and allowlist every contract, selector, recipient, token approval, and value field.
5. Enforce isolated-only positions, tiny notional, hard leverage cap, maximum loss, liquidation buffer, TP/SL, and maximum holding time.
6. Simulate before signing and reject stale quotes or changed account state.
7. Require explicit approval for the first test position.
8. Independently verify position, margin, PnL, funding, and liquidation data after execution.

## Initial policy

- Research and read-only data first.
- No leverage until the adapter and risk tests pass.
- No cross-margin.
- No automated liquidation-risk escalation.
- No autonomous top-ups, withdrawals, or arbitrary contract calls.
- A perps position must pass the same MoA workers and global risk gate as spot trades, with an added derivatives worker review for leverage, liquidation, funding, oracle, and counterparty risk.
