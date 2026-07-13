# Cron Jobs Documentation

Complete reference for all 26 scheduled jobs that power the Hermes Trading Agent.

> Jobs run on the active Hermes profile. Live state is in `~/.hermes/cron/jobs.json` (gitignored). This document is the authoritative reference for what each job does, when it runs, and which model it uses.

## Quick Reference

| # | Job | Schedule | Model | Purpose |
|---|---|---|---|---|
| 1 | daily-defcon-scan | daily | nemotron-3-ultra | DEFCON threat intel (affects crypto) |
| 2 | Brain Decay Pruning | daily | M2.7-Pro | RAG memory cleanup |
| 3 | Brain Reflect | weekly | M2.7 | Episodic → semantic consolidation |
| 4 | Jupiter Price Monitor | every 2h | M2.7 | Live SOL/JUP/cbBTC/JupSOL prices |
| 5 | Crypto Profit Sweep | daily 6 PM ET | M3 | Sweep calculation (Solana) |
| 6-11 | Jupiter Research (6 jobs) | varies | M2.7 | Opportunity scans (Morning/Afternoon/Evening/Night/Overnight/Midday) |
| 12-14 | Jupiter Day Trading (3 jobs) | M-F | M3 | Intraday trade candidates |
| 15 | Portfolio Risk Manager | daily 7:30 AM ET | M3 | Targets/invalidations review |
| 16 | **Autonomous Supervisor** | every 2h | **GPT Luna** | Execution authority, /moa with M3-Pro |
| 17 | Jupiter Reconciliation | every 2h | M2.7 | State vs live wallet reconciliation |
| 18 | Jupiter Yield Monitor | every 4h | M3 | APY diligence (JL-USDC, JupSOL) |
| 19 | Jupiter News Monitor | every 4h | M2.7 | News + macro intel |
| 20 | Multi-Platform Readiness | every 2h | M2.7-Pro | Coinbase/Robinhood/PancakeSwap status |
| 21 | Jupiter Sell/Exit Evaluator | every 1h | M3 | Sell triggers |
| 22 | Portfolio Profit Sweep | daily 6 PM ET | M3 | Sweep calculation |
| 23 | Daily Multi-Platform Report | daily | M2.7 | End-of-day NAV + activity |
| 24 | DuckBot Crypto Trading | every 2h | M3 | Solana trading scan |
| 25 | DuckBot Profit Sweep | daily 6 PM ET | M3 | Solana sweep |
| 26 | DuckBot Wallet Poller | every 30 min | M2.7 | Balance monitoring |

## Model Hierarchy

| Tier | Model | Use |
|---|---|---|
| 1 | GPT Terra | Reserved for explicit user requests only |
| 2 | **MiniMax M3-Pro (MoA)** | Supervisor only — synthesis partner for all /moa calls |
| 3 | **GPT Luna** | Autonomous Supervisor — execution authority |
| 4 | MiniMax M3 | Trading, risk, yield, sell/exit, day trading |
| 5 | MiniMax M2.7 Pro (MoA) | Multi-platform readiness |
| 6 | MiniMax M2.7 | Research, collectors, reports, poller |

**Token spend is balanced across providers:** Luna (1 supervisor) → M3 (5 trading/risk) → M2.7 (10 research/collector) → M3-Pro MoA only on /moa invocation.

## Job Categories

### 1. Research & Discovery (M2.7 — cheap)
- **Jupiter Research Morning Open / Midday / Afternoon / Evening / Night / Overnight** — Read-only opportunity scans
- **Jupiter Price and Market Monitor** — Every 2 hours live prices
- **Jupiter News and Market Impact Monitor** — Every 4 hours news via Brave/web_search + CoinGecko

### 2. Trading & Execution (M3 — thinking)
- **Jupiter Day Trading Open / Midday Collector / Afternoon** — Intraday M-F
- **Portfolio Targets and Risk Manager** — Daily 7:30 AM ET thesis review
- **Jupiter Yield, Staking and Liquidity Monitor** — Every 4 hours APY diligence
- **Jupiter Sell and Exit Evaluator** — Every hour sell triggers
- **Portfolio Profit Sweep Evaluator** — Daily 6 PM ET sweep calc
- **Crypto Profit Sweep** (DuckBot) — Daily 6 PM ET Solana sweep
- **DuckBot Crypto Trading** — Every 2 hours Solana scan

### 3. Monitoring (M2.7 — lightweight)
- **Jupiter Portfolio Reconciliation** — Every 2 hours state vs live
- **Multi-Platform Readiness** — Every 2 hours Coinbase/Robinhood status
- **Daily Multi-Platform Portfolio Report** — End-of-day summary
- **DuckBot Wallet Poller** — Every 30 minutes balance check

### 4. Execution Authority
- **Autonomous Portfolio Execution Supervisor** — GPT Luna, every 2 hours
  - Sole authority to invoke executor with `--execute`
  - Uses `/moa` with MiniMax M3-Pro as synthesis partner
  - Validates policy gates: 1% max risk, 2% daily loss, 0.02 SOL fee reserve, allowlist

### 5. Brain & Memory
- **Brain Decay Pruning** — Daily RAG cleanup
- **Brain Reflect** — Weekly episodic → semantic consolidation

### 6. Macro Intelligence
- **daily-defcon-scan** — DEFCON threat levels (affects crypto risk)

## Non-Spot Strategies

| Strategy | Status | Notes |
|---|---|---|
| `perps` | DORMANT | Requires Jupiter Perps SDK |
| `predictions` | DORMANT | Requires Jupiter Terminal predictions |
| `market_scanner` | **ACTIVE** ✅ | Wired into all research crons |
| `macro_monitor` | **ACTIVE** ✅ | Wired into supervisor, price/news monitor |

**market_scanner** queries Jupiter Terminal API for top-traded + cooking tokens. All candidates must pass: exact mint verification, Token-2022 extension check, issuer confirmation, top-10 holder concentration <30%, independent LP liquidity, CoinGecko presence, honeypot screen.

**macro_monitor** checks: BTC price/dominance, Fear & Greed (≤20 buy / ≥85 sell), DXY move (≥0.5% alert), S&P 500, VIX (≥5pts spike alert), Solana network health, high-impact macro events.

## Swap Base Currency Protocol

Before any swap, supervisor selects optimal input asset:

| Priority | Asset | Condition |
|---|---|---|
| 1 | **USDC** | Available ≥ notional (no price exposure) |
| 2 | **SOL** | SOL ≥ notional + 0.001 gas AND direct route |
| 3 | **JupSOL** | SOL insufficient but JupSOL ≥ notional + gas |
| 4 | **SOL → USDC → TOKEN** | Last resort (double gas justified) |
| — | **HOLD** | No viable route OR reserve threatened |

Always preserve ≥0.02 SOL fee reserve.

## Output Format

All jobs delivering to Telegram use rich Markdown:
- Tables (`| col | col |`)
- Task lists (`- [ ]` / `- [x]`)
- Bold key terms
- Status emojis (🟢/🟡/🔴/⚫)
- Indicators (✅/⚠️/❌)

Maximum 25 lines. No JSON dumps. No prose paragraphs.

## Scam Checks (mandatory before any non-core token buy)

| Check | Rule |
|---|---|
| Mint authority | Verify creator/authority — ruggable mints flagged |
| LP age/depth | Reject pools <24h or <$1k unless thesis justifies |
| Holder concentration | Flag if top 5 hold >80% supply |
| Contract type | Reject if Token-2022 extensions include mint/freeze/pause |
| External checks | Flag honeypot/rug-check lists |
| Exit path | Must have ≥1 Jupiter-routable pair with >$500 24h volume |

## Known Constraints

- Sub-$100 portfolio NAV means passive yield is <$2/yr; growth must come from trading
- 0.40% round-trip cost on $20 swap → 0.50% minimum viable edge
- Fee reserve must remain ≥0.02 SOL
- Max 1% NAV risk per trade, 2% daily loss limit
- $23 active cap per trade at $92 NAV (auto-scales)
- Supabase RPC rate-limits on JupSOL mint (use program-ID query fallback)

## Recovery Commands

```bash
# List jobs
hermes cron list

# Pause/Resume
hermes cron pause <job_id>
hermes cron resume <job_id>

# Run immediately
hermes cron run <job_id> --accept-hooks

# Check status
hermes cron status

# Remove
hermes cron remove <job_id>
```

## File Locations

- Live jobs: `~/.hermes/cron/jobs.json` (gitignored)
- Outputs: `~/.hermes/cron/output/<job_id>/`
- Scripts: `~/.hermes/scripts/*-wrapper.sh`
- State: `state/position_rules.json`, `state/position_theses.json`
- Evidence: `state/evidence/`
- Logs: `logs/`