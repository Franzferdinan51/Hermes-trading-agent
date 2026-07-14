# Robinhood Agentic Trading Integration

## Current status

The Robinhood Trading MCP endpoint is saved in Hermes as `robinhood-trading`, but it is disabled because Robinhood requires an authenticated desktop onboarding flow.

```text
https://agent.robinhood.com/mcp/trading
```

No Robinhood credentials were entered or stored, no Agentic account was opened, and no order capability was enabled.

## Official desktop setup

1. Choose an MCP-capable AI platform.
2. Add the Robinhood Trading MCP endpoint above.
3. Authenticate through Robinhood’s onboarding flow.
4. Complete the dedicated Robinhood Agentic account setup when prompted.
5. Review the account permissions and trading behavior before enabling any action.

Robinhood states that the connected agent receives read access to all Robinhood accounts, account numbers, positions, balances, transactions, order history, watchlists, and scans. The agent can place trades only in the dedicated Agentic account.

## Hermes setup

The endpoint is configured with:

```text
hermes mcp list
hermes mcp test robinhood-trading
```

It currently reports disabled/unauthenticated until the official desktop authentication is completed. After authentication, test the connection before enabling any tools in a fresh Hermes session.

## Safety policy

- Keep `robinhood_agentic.enabled_for_execution` false until authentication, account creation, and policy review are complete.
- Use read-only portfolio and market analysis first.
- Require explicit confirmation for every initial order.
- Do not enable autonomous trading, recurring trades, rebalancing, or strategy automation initially.
- Use a dedicated Agentic account with a small test allocation.
- Preserve global risk limits and independent post-trade verification.
- Never send Robinhood credentials, OTPs, or account details through Agent Mesh.
- Do not treat Robinhood MCP as interchangeable with Coinbase CDP or Jupiter.

## Robinhood Chain readiness (dormant)

Robinhood has announced a Layer-2 blockchain, but this integration is deliberately **separate from Robinhood Agentic/MCP** and remains execution-disabled. Hermes records a dormant readiness module for the future chain, but does not assume a chain ID, RPC, explorer, wallet, custody model, bridge/deposit path, supported asset list, or permissionless transaction surface until each is verified from official developer documentation.

Activation requires official chain/RPC verification; wallet and custody-model verification; exact asset/deposit matrix; a dedicated wallet/signer boundary; transaction construction and instruction validation; simulation; a small funded test; finalized receipt; and independent balance reconciliation. Funding the future module is not authorization to activate it or reuse Robinhood Agentic, Coinbase, Privy, or another venue’s signer.

## Important Robinhood disclosure

Robinhood states that AI-driven trades may execute without direct input on each transaction if configured that way, and the user remains responsible for trades and losses. Agentic trading can result in loss of the entire investment. Keep this integration disabled until its review and approval workflow is tested.
