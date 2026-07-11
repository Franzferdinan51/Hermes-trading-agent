# Security Protocol

> **Scope clarification (2026-07-11):** This override governs legacy Keplr/Cosmos/Osmosis wallets and all treasury or hardware-wallet transfers. The active Privy/Jupiter Solana agent wallet may autonomously sign and broadcast allowlisted Jupiter spot swaps only through `tools/privy_jupiter_executor.py` after policy preflight, fresh quote, decoded transaction checks, and finalized reconciliation. Withdrawals, Tangem sweeps, arbitrary contracts, wallet-permission changes, leverage, and unknown programs remain prohibited.

**Last Updated:** July 9, 2026  
**Status:** MANDATORY READING FOR ALL AGENTS

---

## 🛡️ Defense in Depth

This document outlines the security architecture for the autonomous crypto trading system. Both DuckBot and Hermes MUST follow these rules without exception.

---

## 🔐 Wallet Security

### Hot Wallet Generation
- Generated using cryptographically secure random number generator
- Seed phrases encrypted with AES-256 before storage
- NEVER stored in plaintext anywhere
- Backup encrypted to separate secure location

### Cold Wallet (HARDWARE)
- **Main stack remains on hardware wallet at ALL times**
- **Owner has primary access** via:
  - **Tangem (primary hardware wallet)** — main signing device
  - **Ledger (secondary hardware wallet)** — backup device
- Agent NEVER has access to cold wallet private keys
- Cold wallet address is ONLY for profit reception
- Agent cannot initiate cold wallet transactions
- Every outbound cold-storage signing requires Tangem (primary) or Ledger (secondary) confirmation on the physical device screen
- Documented Cosmos destination: `<YOUR_COSMOS_ADDRESS>` — re-derive on the Tangem card and visually confirm before sending

### Key Storage
```
~/Desktop/crypto-trading-setup/wallets/
├── duckbot/
│   ├── hot_wallet.json     ← Encrypted with user password
│   └── seed_phrase.enc     ← AES-256 encrypted seed
└── hermes/
    └── [same structure]
```

---

## 📏 Trading Limits

### DuckBot Limits (Starting)
| Parameter | Value | Notes |
|-----------|-------|-------|
| Max position | $10 | Per single trade |
| Daily limit | $25 | Total trades per day |
| Portfolio cap | $50 | Max in hot wallet |
| Loss limit | $5/day | Auto-stop if hit |
| Sweep trigger | 20% gain | 50% to USDC, 25% to BTC |

### Profit Accumulation
| Asset | Allocation | Condition |
|-------|------------|----------|
| **USDC** | 50% of profits | Always |
| **BTC** | 25% of profits | Only if USDC > $50 |
| **Reinvest** | 25% of profits | Always |

### Temporary Limits (Can be adjusted)
| Parameter | Value | Notes |
|-----------|-------|-------|
| Test period | 30 days | $10 max, $5 loss limit |
| Phase 2 | 30-90 days | $25 max, $10 loss limit |
| Phase 3 | 90+ days | $50 max, $20 loss limit |

---

## ✅ Allowed Operations

### CAN DO (Autonomous)
1. Check token balances
2. Check prices on whitelisted DEXs
3. Execute swaps up to position limit
4. Send profits to cold wallet (up to sweep threshold)
5. Send price alerts to owner
6. Log all transactions

### CANNOT DO (Blocked)
1. Withdraw to non-whitelisted addresses
2. Send full wallet balance in one transaction
3. Execute trades during blacklisted times
4. Trade non-whitelisted tokens
5. Enable any form of leverage
6. Participate in flash loans
7. Access cold wallet keys
8. Reveal seed phrases to any party

### NEED APPROVAL (Human-in-the-Loop)
1. Any trade > $10 (notify owner)
2. Any trade > $50 (explicit approval required)
3. Any new token pair (explicit approval required)
4. Changing any trading parameter
5. Increasing position limits
6. Adding new DEX to whitelist

---

## 🚨 Emergency Stop

### Automatic Triggers
- Daily loss exceeds $5 → STOP TRADING
- Portfolio drops below $3 → STOP AND ALERT
- Smart contract flagged as malicious → STOP AND ALERT
- Abnormal activity detected → FREEZE AND ALERT

### Manual Triggers
Owner can emergency stop via:
- Telegram command: `/stoptrading`
- Direct message to agent
- Editing `STOP_TRADING` flag file

---

## 📋 Audit Log

Every trade logged with:
- Timestamp (UTC)
- Agent ID (DuckBot/Hermes)
- Token pair
- Entry price
- Exit price
- Position size (USD)
- Profit/Loss
- Transaction hash
- Wallet address (truncated)
- Any alerts sent

Location: `~/Desktop/crypto-trading-setup/logs/`

---

## 🔒 Network Security

### RPC/API Security
- All API keys stored encrypted
- RPC endpoints verified against official sources
- No API key in plaintext logs
- Rate limiting respected

### Node Security
- Use trusted public RPC nodes
- Verify node certificates
- Monitor for unusual responses
- Fallback nodes configured

---

## 🚫 Scam Prevention

### Whitelisted DEXs Only
- **ATOM:** Osmosis (official)
- **SOL:** Raydium, Jupiter Aggregator

### Red Flags That Trigger Alert
- Unusual gas fees
- New/unverified tokens
- Pools with < $1000 liquidity
- Tokens with honeypot potential
- Requests for seed phrases
- Unexpected contract interactions

### Before Any Trade
1. Verify contract address on official source
2. Check pool liquidity
3. Verify transaction simulation
4. Confirm balance before/after

---

## 📞 Incident Response

### If Compromise Suspected
1. IMMEDIATELY freeze all trading
2. Alert owner via Telegram
3. Do NOT attempt to move funds without approval
4. Document all recent transactions
5. Preserve logs for investigation

### If Loss Occurs
1. Log full details
2. Report to owner immediately
3. Do NOT hide losses
4. Review and adjust parameters
5. No revenge trading

---

## ⚖️ Legal Disclaimer

Trading cryptocurrency carries risk. Past performance does not guarantee future results. Agents operate within defined parameters but losses can still occur. Owner accepts all risk and understands the volatile nature of cryptocurrency markets.

---

**BOTH AGENTS MUST ACKNOWLEDGE THIS DOCUMENT BEFORE TRADING**

---

## 💎 HARD WALLET (Profit Destination)

**BTC Address:** `bc1q733czwuelntfug8jgur6md2lhzcx7l5ufks9y7`

All profits are eventually converted to BTC and sent here.

### Profit Flow:
```
Trading Wallet (ATOM/OSMO)
       ↓
   Profit Swap
       ↓
USDC/USDT (temporary holding)
       ↓
   BTC Purchase
       ↓
Hard Wallet (bc1q733czwuelntfug8jgur6md2lhzcx7l5ufks9y7)
```

### Sweep Rules:
- **Nightly at 6 PM ET:** Sweep all OSMO to USDC
- **When USDC > $50:** Convert 50% to BTC
- **When USDC > $100:** Convert 75% to BTC
- **BTC always goes to hard wallet**
