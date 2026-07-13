# Cron Platform Policy

## Active now

Jupiter/Solana monitoring, reconciliation, research, and the bounded supervisor are active. Coinbase/CDP Base is also enabled solely for the verified `tools/cdp_base_executor.mjs` USDC→WETH path: ≤$100 USDC, ≤100 bps slippage, fresh complete-simulation quote, positive net edge, supervisor authorization, and independent receipt/balance verification. All other platform-local execution remains disabled.

## Disabled pending readiness

Robinhood Agentic/MCP, TronLink/TRON, SunSwap/SUN MCP, PancakeSwap Base/Solana, and Avantis/Base are registered in the wrapper but are not fully verified for execution. They must remain `HOLD`/disabled in scheduled work. Coinbase/Base is the sole exception: only its allowlisted CDP USDC→WETH executor is enabled.

## First-tier venue policy

Every relevant scheduled workflow compares Jupiter/Solana, Coinbase Advanced Trade/CDP Base, and PancakeSwap Base/Solana as equal first-tier venues. Robinhood Agentic is included after authentication and dedicated-account onboarding. The scan covers crypto, equities/stocks, tokenized stocks/xStocks, staking, Earn, lending, LP, yield, transfers, and other supported products. It refreshes balances, prices, quotes, liquidity, fees, positions, P&L, readiness, and exit paths before ranking opportunities. A positive-net-edge opportunity with acceptable risk should not be rejected merely because capital is available; unsupported routes, stale data, poor liquidity, and missing reconciliation remain HOLD blockers.

Coinbase Base balance verification uses `tools/cdp_base_balance.mjs` and the official Coinbase CDP SDK before raw RPC fallback. An RPC HTTP 403 is labeled as an RPC-source limitation when the CDP probe succeeds, not as a zero Coinbase balance.


The autonomous supervisor receives the latest outputs from market collection, wallet reconciliation, multi-platform readiness, research scans, portfolio risk, yield/staking diligence, news, sell/exit, and profit-sweep jobs. It may independently create and evaluate candidates rather than waiting for a pre-approved Ready card. Day trading and multiple simultaneous positions are permitted when aggregate risk, liquidity, correlation, fee efficiency, reserves, and exit capacity support them; there is no arbitrary position-count cap. Zero USDC is not an automatic blocker when a direct SOL-funded route preserves the native fee reserve.

## Swap Base Currency Protocol

Before executing any swap, the supervisor selects the optimal input asset:

| Priority | Asset | Condition | Notes |
|---|---|---|---|
| 1 | **USDC** | Available balance ≥ notional | No price exposure, no extra swap needed |
| 2 | **SOL** | SOL ≥ notional + 0.001 SOL gas AND direct route exists | 1 swap; preserves fee reserve ≥0.02 SOL |
| 3 | **JupSOL** | SOL insufficient but JupSOL ≥ notional + 0.001 SOL gas AND direct route | Preserves ~5.7% APY on remainder; account for unstaking |
| 4 | **SOL → USDC → TOKEN** | Only as last resort; double gas must be economically justified | Only if thesis allows SOL sell-down |
| — | **HOLD** | No viable route OR reserve would be breached | Log exact blocker |

Always preserve ≥0.02 SOL fee reserve. Never reduce JupSOL below the amount needed to keep SOL ≥0.02 SOL after unstaking. Log which base asset was chosen and why for every execution.

## Scam Checks (mandatory before any non-core token buy)

| Check | Rule |
|---|---|
| Mint authority | Verify creator/authority — ruggable mints (mint authority not revoked) flagged |
| LP age/depth | Reject pools <24h old or <$1k depth unless thesis justifies it |
| Holder concentration | Flag if top 5 wallets hold >80% supply |
| Contract type | Reject if Token-2022 extensions include mint/freeze/pause authority unless explicitly authorized |
| External checks | Flag if token on honeypot/rug-check lists or has known exploit history |
| Contract immutability | Immutable preferred; only allow with explicitly authorized immutable upgrades |
| Exit path | Must have ≥1 Jupiter-routable pair with >$500 24h volume |
| Supervisor log | Log which checks passed vs waived with justification |

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

PancakeSwap Base quote discovery is enabled through `tools/pancakeswap_base_quote.mjs` using the official `@pancakeswap/smart-router` package. It finds routes across V2/V3 pools and builds Base calldata for the official Smart Router, but it never signs or broadcasts. PancakeSwap Base execution remains HOLD until an exact-amount Permit2 approval/permit flow, transaction simulation, CDP sender adapter, and independent settlement verifier are implemented and tested. PancakeSwap Solana discovery is enabled read-only; execution remains HOLD until official program/route verification, instruction decoding, simulation, fee/slippage controls, and post-trade reconciliation are implemented. Cross-platform transfers are permitted by policy when an exact same-chain or verified bridge route passes documented source/destination, asset, fee, net-edge, finality, and reconciliation gates.
