# Coinbase CDP Base Agent Add-On

This is an additive Base setup. It does not replace or modify the Privy Solana/Jupiter wallet.

## Wallet separation

- Solana: existing Privy wallet and `tools/privy_jupiter_executor.py`
- Base: separate Coinbase CDP/AgentKit wallet and Base-only policy
- Treasury: remain separate; no autonomous withdrawals or bridges

## Official Coinbase components

- Coinbase AgentKit: https://docs.cdp.coinbase.com/agent-kit/welcome
- CDP wallet management: https://docs.cdp.coinbase.com/agent-kit/core-concepts/wallet-management
- CDP wallet security: https://docs.cdp.coinbase.com/wallets/security-and-policies/security-overview
- Base mainnet chain ID: `8453`
- Base RPC default used by the readiness checker: `https://mainnet.base.org`

## Required credentials

Create and store these outside the repository, preferably in the OS credential manager or a protected runtime environment:

```text
CDP_API_KEY_ID
CDP_API_KEY_SECRET
CDP_WALLET_SECRET
BASE_AGENT_ADDRESS
```

Never put secrets in `.env` files committed to git, cron prompts, logs, chat, or source code.

## Read-only check

Invoke through the `terminal` tool:

```bash
python3 tools/base_agent_readiness.py
```

This checks configuration and Base RPC reachability only. It does not create a wallet or transact.

## Initial Base scope

Before enabling any transaction capability:

- Base ETH and native Base USDC only
- Read-only balance and contract checks first
- Small isolated wallet balance
- Approved router/contract allowlist only
- Explicit transaction preview before signing
- Per-trade and daily-loss caps matching Solana policy
- No bridges, arbitrary contract calls, leverage, or withdrawals
- Verify every transaction on BaseScan and through an independent RPC

## Current status

- CDP credentials are configured and the Base wallet `<BASE_WALLET_ADDRESS>` is funded.
- Live balance probe: `node tools/cdp_base_balance.mjs` (official CDP SDK, primary source).
- Execution: bounded USDC→WETH via `node tools/cdp_base_executor.mjs --amount N --slippage-bps N --execute`.
- The supervisor template and `platforms.json` treat Jupiter/Solana and Coinbase CDP/Base as equal co-primary first-tier venues.
- PancakeSwap Base/Solana are first-tier research/quote venues; execution remains gated pending Permit2/simulation/adapter verification.
