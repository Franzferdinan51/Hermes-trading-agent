# Portfolio Report Data Integrity

This runbook governs the `Daily Multi-Platform Portfolio Report` cron (`804bed3eebe8`). It prevents stale balances, raw-unit errors, confusing quote labels, and Perps double counting. The report is read-only; it never signs or changes a position.

## Authoritative sources

| Data | Required source | Rule |
|---|---|---|
| Solana balances | `python3 tools/wallet_poller.py` | Use the JSON `balances` from the same report cycle, never a state-file snapshot. |
| Solana exit values | `python3 tools/jupiter_quote.py <asset> USDC <raw_amount> --slippage-bps 100` | Convert `outAmount` from micro-USDC by dividing by `1_000_000`. |
| Base balances | `node tools/cdp_base_balance.mjs` | Convert `amount / 10**decimals`; filter unsolicited airdrop/scam tokens. |
| Perps | `python3 tools/jupiter_perps_executor.py positions` | Equity is `(collateralUsd + pnlAfterFeesUsd) / 1_000_000`. |
| Perps protection | `state/perps_monitor_latest.json` | Confirm full TP/stop, liquidation buffer, and nearest trigger. |

## Jupiter quote rules

- The canonical quote helper uses `https://api.jup.ag/swap/v1/quote` and obtains its key through the configured macOS keychain service.
- `quote-api.jup.ag` DNS failure is a legacy-host problem; it does not prove that Jupiter, `api.jup.ag`, or `lite-api.jup.ag` is unavailable.
- Symbol lookup is case-insensitive for `cbBTC` and `JupSOL`; the helper maps them to their exact mints.
- A full-balance exit quote is **not** a unit price. Label it `Full-balance <asset> exit: $X.XX`; calculate per-unit price as `out_usdc / input_ui_amount`.
- For JupSOL, use its exact balance in raw six-decimal units. A successful full-balance quote is authoritative for that cycle and supersedes an older price-v3 mark.

## NAV rules

```text
Solana NAV = sum(live spot holding values) + Perps equity
Base NAV   = sum(verified ETH/WETH/USDC values)
Combined   = Solana NAV + Base NAV
```

Do not add Perps notional: it double-counts borrowed exposure. If the displayed holdings plus Perps equity do not reconcile to Solana NAV within `$0.05`, publish `RECONCILIATION HOLD` instead of a combined NAV.

## Verification

Invoke through the `terminal` tool from `<HERMES_REPO_PATH>`:

```bash
python3 tools/wallet_poller.py
python3 tools/jupiter_quote.py JupSOL USDC 79124960 --slippage-bps 100
python3 tools/jupiter_perps_executor.py positions
node tools/cdp_base_balance.mjs
```

A valid report labels full-balance quotes correctly, contains no raw Base wei in the quote section, displays Perps equity separately, and uses the wallet-poller USDC balance from the same cycle.
