# TRONLink and SunSwap Integration

## Platform separation

- **TRONLink** is the TRON wallet connection and local approval layer.
- **SunSwap** is the TRON DEX adapter for quotes, routes, and swaps.
- SunSwap must use the registered TRONLink wallet adapter; it must not receive or export private keys.

Official references:

- TronLink developer docs: `https://docs.tronlink.org/dapp/getting-started`
- TronLink signer docs: `https://docs.tronlink.org/ai-support/tronlink-signer`
- SUN.io developer docs: `https://docs.sun.io`
- SunSwap interface documentation: `https://www.sunswap.com/docs/sunswap-interfaces_en.pdf`

## Current status

Both entries are registered in `state/platforms.json` and disabled:

```text
tronlink_tron  = planned_disabled
sunswap_tron   = planned_disabled
```

No wallet connection, private-key export, transaction signing, or swap was attempted.

## MCP integrations

TronLink provides official MCP options:

- `mcp-tronlink-signer` via stdio: `claude mcp add -s user tronlink-signer -- npx mcp-tronlink-signer`
- `mcp-server-tronlink`, which exposes read/query and TRON operations, including SunSwap V2/V3 swap capabilities.

The signer tools include `connect_wallet`, `get_balance`, `send_trx`, `send_trc20`, and `sign_transaction`. Signing opens a TronLink approval page; private keys never leave the wallet. Broadcast outcomes must be reconciled before any retry.

SUN.io provides an official SUN MCP Server for SunSwap:

```text
https://sun-mcp-server.bankofai.io/mcp
```

Its cloud service is read-only and requires no wallet. Writes require a local private deployment according to the SUN.io documentation. Keep the cloud MCP read-only and use TronLink’s approval-bound signer for any eventual write path.

## Required implementation gates

1. Detect TronLink and verify the selected TRON network.
2. Connect the wallet without requesting private-key export.
3. Read and reconcile TRX and TRC-20 balances.
4. Verify token contract addresses and exact asset identity.
5. Implement SunSwap quote and route retrieval from official documentation.
6. Validate router/contract addresses from an allowlist.
7. Enforce slippage, deadline, minimum-output, fee, and recipient checks.
8. Simulate or otherwise validate the transaction before requesting local approval.
9. Require an explicit TronLink approval for the first transaction.
10. Independently verify transaction ID, receipt, balances, and trade outcome.

## Initial scope

Start with read-only TRX and TRC-20 balance checks, SunSwap market/quote data, and dry-run candidate reviews. The first live transaction must be a small test swap with explicit approval. Do not enable liquidity provision, staking, farming, arbitrary contract calls, or autonomous withdrawals initially.

## Cross-platform rules

TRONLink and SunSwap participate in the same MoA and global risk system as Jupiter, Coinbase, and Robinhood, but their signer and adapter remain local to TRON. A cross-chain transfer is never implied by a portfolio recommendation.
