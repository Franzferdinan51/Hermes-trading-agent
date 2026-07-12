# Cron Platform Policy

## Active now

Jupiter/Solana monitoring, reconciliation, research, and the bounded supervisor are active. Coinbase/CDP Base is also enabled solely for the verified `tools/cdp_base_executor.mjs` USDC→WETH path: ≤$100 USDC, ≤100 bps slippage, fresh complete-simulation quote, positive net edge, supervisor authorization, and independent receipt/balance verification. All other platform-local execution remains disabled.

## Disabled pending readiness

Robinhood Agentic/MCP, TronLink/TRON, SunSwap/SUN MCP, PancakeSwap Base/Solana, and Avantis/Base are registered in the wrapper but are not fully verified for execution. They must remain `HOLD`/disabled in scheduled work. Coinbase/Base is the sole exception: only its allowlisted CDP USDC→WETH executor is enabled.

## Shared readiness cron

Hermes job: `Multi-Platform Readiness and MoA Monitor`

- Job ID: `7202c99f98a0`
- Schedule: every 120 minutes
- Model: MiniMax M2.7 Pro
- Mode: read-only collector
- Status: paused until the user enables it
- Worker cap: shared bounded pool from `state/moa_presets.json`
- No credentials, signing, orders, bridges, withdrawals, or account creation

## Enabling criteria

Do not resume the readiness job or add a platform to execution merely because an MCP endpoint responds. A platform needs verified authentication, current balances, supported asset identity, a tested adapter, policy checks, dry-run/simulation, and independent post-action verification. Funding is required for wallet-based execution; Robinhood requires its dedicated Agentic account and desktop authentication.

## Cost controls

Use MiniMax M2.7 Pro or the configured free NVIDIA fallback for collection/reference work. Reserve the aggregator for synthesis and risk interpretation. Do not spawn 49-agent councils; obey the configured four-agent default and five-agent cross-platform maximum.

## PancakeSwap Base quote activation

PancakeSwap Base quote discovery is enabled through `tools/pancakeswap_base_quote.mjs` using the official `@pancakeswap/smart-router` package. It finds routes across V2/V3 pools and builds Base calldata for the official Smart Router, but it never signs or broadcasts. PancakeSwap execution remains HOLD until an exact-amount Permit2 approval/permit flow, transaction simulation, CDP sender adapter, and independent settlement verifier are implemented and tested. PancakeSwap Solana remains disabled because no current official program/route integration has been verified.
