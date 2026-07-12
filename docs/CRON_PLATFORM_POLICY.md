# Cron Platform Policy

## Active now

Only existing Jupiter/Solana read-only monitoring, reconciliation, research, and the bounded supervisor are active. Their platform-local execution and global risk gates remain authoritative.

## Disabled pending readiness

Coinbase/Base, Robinhood Agentic/MCP, TronLink/TRON, and SunSwap/SUN MCP are registered in the wrapper but are not funded, authenticated, or fully verified for execution. They must remain `HOLD`/disabled in scheduled work.

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
