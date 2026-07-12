# Base Agent Setup — Home Handoff

**Status:** additive setup prepared; no Base wallet was created and no funds moved.
**Last verified:** 2026-07-11

## Executive summary

The existing Privy Solana/Jupiter system remains intact. Base is being added as a separate Coinbase CDP/AgentKit execution path. The Base readiness checker is installed and successfully reached Base mainnet, but Coinbase credentials and an explicit Base agent wallet have not yet been configured.

## What is already verified

- Solana Privy wallet remains the active Solana/Jupiter wallet.
- Solana executor was not modified by the Base add-on.
- Base RPC: `https://mainnet.base.org`
- Base chain ID: `8453`
- Base RPC connectivity: passed
- Latest observed Base block during setup: `48512524`
- No Coinbase/CDP secrets were found in the environment.
- Dedicated Coinbase CDP EVM account `base-agent` was created and listed successfully.
- Base agent address: `<BASE_WALLET_ADDRESS>`
- No Base transaction, bridge, deposit, approval, or contract call was attempted.

## Files added

```text
tools/base_agent_readiness.py
docs/COINBASE_BASE_AGENT_ADDON.md
docs/BASE_AGENT_HANDOFF.md
```

## Solana preservation rule

Do not remove or replace:

```text
tools/privy_jupiter_executor.py
```

Solana remains the separate Privy/Jupiter path for SOL, JUP, JupSOL, cbBTC, USDC, and speculative ANSEM handling. Base must use a separate wallet/policy scope and must not alter Solana allowlists, balances, cron jobs, or executor settings.

## Official Coinbase references

- AgentKit overview: https://docs.cdp.coinbase.com/agent-kit/welcome
- Wallet management: https://docs.cdp.coinbase.com/agent-kit/core-concepts/wallet-management
- CDP wallet security: https://docs.cdp.coinbase.com/wallets/security-and-policies/security-overview
- Privy/AgentKit wallet-provider reference: https://docs.cdp.coinbase.com/agent-kit/core-concepts/wallet-management

## Required configuration

Create/configure these through Coinbase’s official developer console or protected runtime environment:

```text
CDP_API_KEY_FILE=~/secure/cdp_api_key.json
CDP_WALLET_SECRET
BASE_AGENT_ADDRESS
```

The supplied JSON file has the expected `id` and `privateKey` fields and is now owner-only (`0600`). Do not print or copy its values. `CDP_WALLET_SECRET` and a verified Base agent address are still separate requirements.

Do not put secret values in this document, source files, cron prompts, chat, logs, Git, or a committed `.env` file. Prefer the macOS Keychain or an equivalent secret manager.

## Readiness command

From the project directory, invoke through the `terminal` tool:

```bash
cd <LOCAL_USER_HOME>/Desktop/crypto-trading-setup
python3 tools/base_agent_readiness.py
```

Expected completed-state conditions:

```text
credentials_present: all True
chain_id: 8453
chain_ok: True
next_step: review policy before enabling transactions
```

The checker is read-only. It does not create wallets, sign, broadcast, bridge, approve, or spend.

## Home setup sequence

1. Create or enable the Coinbase Developer Platform/CDP project.
2. Create the required API credentials and store them securely.
3. Create or identify a dedicated Base agent wallet. Do not reuse the Solana wallet.
4. Set `BASE_AGENT_ADDRESS` to the public Base address only.
5. Run the readiness checker.
6. Verify the address and chain through BaseScan and the Base RPC.
7. Fund only a tiny test amount first.
8. Use Base-native ETH for gas and native USDC for the initial stable asset.
9. Do not bridge until the bridge route, token, recipient, fees, and recovery behavior have been separately reviewed.
10. Add policy guards before any transaction capability is enabled.
11. Perform a read-only balance check.
12. Prepare a tiny test transaction and show the decoded destination, chain ID, token, amount, gas, and contract.
13. Require explicit approval immediately before signing.
14. Verify the resulting transaction on BaseScan and through an independent RPC.
15. Only after successful testing, consider approved Base platforms or routers.

## Initial Base policy

- Base ETH and native Base USDC only.
- Separate Base wallet and separate ledger bucket.
- No arbitrary contract calls.
- No autonomous withdrawals or arbitrary contract calls. Cross-platform transfer/bridge automation is permitted only through an exact allowlisted route with source/destination, asset, fee, finality, positive net-edge, supervisor, and independent reconciliation gates.
- No autonomous withdrawals or profit sweeps.
- Approved-contract allowlist only.
- Small balance cap.
- Per-trade notional and daily-loss limits matching Solana policy.
- Stop on unknown signer prompts, changed transaction data, RPC disagreement, unexpected balance changes, or unsupported token contracts.
- Keep a gas reserve in Base ETH.
- Verify token contract addresses; never rely on tickers alone.

## Coinbase vs Privy decision

For Base-native agent trading, Coinbase CDP/AgentKit is the selected Base path because its official AgentKit documentation directly covers agent wallet management, EVM networks, Base, onchain actions, and wallet security. Privy remains the existing Solana/Jupiter path. This is a separation decision, not a migration: both systems should coexist.

## Known blockers

- CDP credentials are not configured.
- No Base agent address has been created or verified.
- Coinbase AgentKit package/SDK is not installed in the project environment.
- No Base wallet balance exists or has been checked.
- No Base router or platform has been selected.
- No Base transaction policy has been implemented yet.

These are setup blockers only. They do not indicate a problem with the Solana wallet or Solana executor.
