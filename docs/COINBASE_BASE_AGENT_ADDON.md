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

The current environment has no detected CDP credentials and no Coinbase AgentKit Python package installed. The additive readiness checker is installed, but Base wallet creation and signing remain intentionally disabled until credentials, wallet policy, and the exact Coinbase SDK/CLI path are configured.
