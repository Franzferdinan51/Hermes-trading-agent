#!/usr/bin/env python3
"""Perpetuals trading module — DORMANT by default.

This module is completely inactive until explicitly enabled via config.
It integrates with the existing policy engine, dynamic allowlist, and executor
patterns but adds perp-specific primitives: margin accounts, positions,
funding rates, liquidation monitoring, and health factors.

Enable by setting `perps.enabled = true` in state/position_rules.json.
"""
from __future__ import annotations

import json
import time
import typing
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
RULES_FILE = STATE / "position_rules.json"

JUPITER_PERPS_API = "https://perps-api.jup.ag/v2"
DRIFT_API = "https://api.drift.trade"  # alternative

# Jupiter Perps v2 only supports 3 markets (as of 2026-07-13)
# Mints verified from perps-api.jup.ag/v2/market-stats enum
JUPITER_PERPS_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "WBTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
    "ETH": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
}

# Solana RPC
RPC_URL = "https://api.mainnet-beta.solana.com"


def _rpc(method: str, params: list) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("result", {})


def _http_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


@dataclass
class PerpMarket:
    """Perpetual market metadata."""
    market_index: int
    symbol: str                    # e.g., "SOL-PERP"
    base_mint: str                 # underlying asset mint
    quote_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
    max_leverage: int = 10
    min_order_size: float = 0.01
    tick_size: float = 0.001
    funding_rate: float = 0.0
    next_funding_ts: int = 0
    oracle_price: float = 0.0
    mark_price: float = 0.0
    open_interest: float = 0.0
    is_active: bool = True


@dataclass
class PerpPosition:
    """Open perpetual position."""
    market_symbol: str
    side: str                      # "long" or "short"
    size: float                    # contracts (base asset)
    entry_price: float
    leverage: int
    collateral_usdc: float         # USDC locked as margin
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    funding_paid: float = 0.0
    opened_ts: int = field(default_factory=lambda: int(time.time()))
    last_updated_ts: int = field(default_factory=lambda: int(time.time()))

    @property
    def notional_usd(self) -> float:
        return self.size * self.entry_price

    @property
    def margin_ratio(self) -> float:
        """Collateral / notional. Higher = safer."""
        if self.notional_usd == 0:
            return float('inf')
        return self.collateral_usdc / self.notional_usd

    @property
    def health_factor(self) -> float:
        """Simplified health factor. < 1.0 = liquidatable."""
        # In practice: (collateral + unrealized_pnl) / (notional * maintenance_margin)
        maint_margin = 0.05  # 5% maintenance
        equity = self.collateral_usdc + self.unrealized_pnl
        required = self.notional_usd * maint_margin
        return equity / required if required > 0 else float('inf')


@dataclass
class MarginAccount:
    """Cross-margin perp account."""
    authority: str                  # wallet pubkey
    usdc_balance: float = 0.0       # free USDC
    locked_margin: float = 0.0      # USDC locked in positions
    positions: dict[str, PerpPosition] = field(default_factory=dict)

    @property
    def total_equity(self) -> float:
        return self.usdc_balance + self.locked_margin + sum(
            p.unrealized_pnl for p in self.positions.values()
        )

    @property
    def free_collateral(self) -> float:
        return self.usdc_balance


class PerpsClient:
    """Jupiter Perps API client (read-only for now)."""

    def __init__(self, api_base: str = JUPITER_PERPS_API):
        self.api_base = api_base

    def fetch_markets(self) -> list[PerpMarket]:
        """Fetch Jupiter Perps market stats for all 3 supported markets (SOL, WBTC, ETH).

        The Jupiter v2 API does not have a /markets list endpoint — only /market-stats
        per individual mint. We enumerate the 3 known mints and collect their stats.
        """
        markets = []
        for mint in JUPITER_PERPS_MINTS.values():
            try:
                data = _http_json(f"{self.api_base}/market-stats?mint={mint}")
                # Map symbol from mint
                symbol = next((k for k, v in JUPITER_PERPS_MINTS.items() if v == mint), "UNKNOWN")
                markets.append(PerpMarket(
                    market_index=hash(mint) % 1000,
                    symbol=symbol,
                    base_mint=mint,
                    max_leverage=100,  # Jupiter Perps allows up to 100x on most pairs
                    min_order_size=0.01,
                    tick_size=0.001,
                    funding_rate=0.0,  # Not in market-stats; need separate endpoint
                    next_funding_ts=0,
                    oracle_price=float(data.get("price", 0)),
                    mark_price=float(data.get("price", 0)),
                    open_interest=float(data.get("volume", 0)),
                    is_active=True,
                ))
            except Exception as e:
                print(f"PerpsClient.fetch_markets error for {mint}: {e}")
        return markets

    def fetch_funding_rates(self) -> dict[str, float]:
        """Fetch funding rates from Jupiter Perps v2.

        The v2 API does not expose a public funding-rates endpoint — funding is
        computed at position level on Jupiter. For now, we return zeros; the
        funding rate will be inferred from position metadata when positions exist.
        """
        # Jupiter v2 doesn't have a public funding rate endpoint
        # Funding is implicit in the position's borrowFeesUsd and totalFeesUsd
        return {symbol: 0.0 for symbol in JUPITER_PERPS_MINTS.keys()}

    def fetch_orderbook(self, symbol: str) -> dict | None:
        """Fetch orderbook for a symbol.

        Jupiter v2 does not expose orderbook publicly — prices are derived from
        the JLP pool. The market-stats endpoint provides the current mark price.
        """
        try:
            mint = JUPITER_PERPS_MINTS.get(symbol.upper())
            if not mint:
                return None
            return _http_json(f"{self.api_base}/market-stats?mint={mint}")
        except Exception:
            return None


class PerpsEngine:
    """Core perp trading engine — DORMANT unless enabled in config."""

    def __init__(self, wallet: str | None = None):
        self.wallet = wallet
        self.client = PerpsClient()
        self.markets: dict[str, PerpMarket] = {}
        self.account: MarginAccount | None = None
        self._enabled = False
        self._load_config()

    def _load_config(self) -> None:
        try:
            rules = json.loads(RULES_FILE.read_text())
            perps_cfg = rules.get("global", {}).get("perps", {})
            self._enabled = perps_cfg.get("enabled", False)
            self.max_leverage = perps_cfg.get("max_leverage", 5)
            self.max_position_pct_nav = perps_cfg.get("max_position_pct_nav", 0.10)
            self.liquidation_buffer = perps_cfg.get("liquidation_buffer", 1.2)
            self.allowed_markets = set(perps_cfg.get("allowed_markets", ["SOL-PERP", "BTC-PERP", "ETH-PERP"]))
            self.auto_monitor = perps_cfg.get("auto_monitor", True)
            self.funding_threshold = perps_cfg.get("funding_threshold", 0.0001)  # 1bp/hour
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> bool:
        if not self._enabled:
            self._enabled = True
            self._persist_enable()
            self._refresh_markets()
        return True

    def disable(self) -> bool:
        self._enabled = False
        self._persist_enable()
        return True

    def _persist_enable(self) -> None:
        rules = json.loads(RULES_FILE.read_text())
        rules.setdefault("global", {}).setdefault("perps", {})["enabled"] = self._enabled
        RULES_FILE.write_text(json.dumps(rules, indent=2) + "\n")

    def _refresh_markets(self) -> None:
        self.markets = {m.symbol: m for m in self.client.fetch_markets()}

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "markets_loaded": len(self.markets),
            "account": self.account.authority if self.account else None,
            "positions": len(self.account.positions) if self.account else 0,
            "total_equity": self.account.total_equity if self.account else 0.0,
            "free_collateral": self.account.free_collateral if self.account else 0.0,
        }

    # --- Read-only market data (safe to call anytime) ---
    def get_market(self, symbol: str) -> PerpMarket | None:
        if symbol not in self.markets:
            self._refresh_markets()
        return self.markets.get(symbol)

    def get_funding_rate(self, symbol: str) -> float:
        return self.client.fetch_funding_rates().get(symbol, 0.0)

    # --- Account management (requires enabled) ---
    def initialize_account(self, wallet: str) -> MarginAccount:
        if not self._enabled:
            raise RuntimeError("Perps engine is disabled. Enable in config first.")
        self.wallet = wallet
        self.account = MarginAccount(authority=wallet)
        # Fetch actual USDC balance from wallet
        bal = _rpc("getTokenAccountsByOwner", [
            wallet, {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}, {"encoding": "jsonParsed"}
        ])
        total = 0.0
        for row in bal.get("value", []):
            info = row.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            total += float(info.get("tokenAmount", {}).get("uiAmount", 0) or 0)
        self.account.usdc_balance = total
        return self.account

    def load_account(self, wallet: str) -> MarginAccount:
        return self.initialize_account(wallet)

    # --- Position management (requires enabled) ---
    def open_position(
        self,
        symbol: str,
        side: str,
        size_usd: float,
        leverage: int,
        max_slippage_bps: int = 50,
    ) -> dict:
        if not self._enabled:
            return {"ok": False, "error": "Perps engine disabled"}
        if not self.account:
            return {"ok": False, "error": "Account not initialized"}
        if symbol not in self.allowed_markets:
            return {"ok": False, "error": f"Market {symbol} not in allowed list"}
        market = self.get_market(symbol)
        if not market or not market.is_active:
            return {"ok": False, "error": f"Market {symbol} not found or inactive"}
        if leverage > min(self.max_leverage, market.max_leverage):
            return {"ok": False, "error": f"Leverage {leverage}x exceeds max {min(self.max_leverage, market.max_leverage)}x"}

        # Check NAV limit
        # (would need NAV from position_rules.json or live fetch)

        # Required collateral
        collateral_needed = size_usd / leverage
        if self.account.free_collateral < collateral_needed:
            return {"ok": False, "error": f"Insufficient free collateral: ${self.account.free_collateral:.2f} < ${collateral_needed:.2f}"}

        # Build order (would call Jupiter Perps API or Drift SDK)
        # This is a placeholder — actual execution needs SDK integration
        order = {
            "market": symbol,
            "side": side,
            "size_usd": size_usd,
            "leverage": leverage,
            "collateral_usdc": collateral_needed,
            "slippage_bps": max_slippage_bps,
        }

        # Lock collateral
        self.account.usdc_balance -= collateral_needed
        self.account.locked_margin += collateral_needed

        # Create position placeholder (real fill would come from callback)
        pos = PerpPosition(
            market_symbol=symbol,
            side=side,
            size=size_usd / market.mark_price if market.mark_price > 0 else 0,
            entry_price=market.mark_price,
            leverage=leverage,
            collateral_usdc=collateral_needed,
        )
        self.account.positions[symbol] = pos

        return {"ok": True, "order": order, "position": pos.__dict__}

    def close_position(self, symbol: str, size_pct: float = 100.0) -> dict:
        if not self._enabled or not self.account:
            return {"ok": False, "error": "Perps disabled or no account"}
        pos = self.account.positions.get(symbol)
        if not pos:
            return {"ok": False, "error": f"No position in {symbol}"}
        # Placeholder for close order
        return {"ok": True, "note": "Close order placeholder — needs SDK integration"}

    def update_positions(self) -> dict:
        """Mark-to-market all positions, check health, process funding."""
        if not self._enabled or not self.account:
            return {"ok": False, "error": "Perps disabled"}

        alerts = []
        for symbol, pos in self.account.positions.items():
            market = self.get_market(symbol)
            if not market:
                continue
            # Update unrealized PnL
            if pos.side == "long":
                pos.unrealized_pnl = (market.mark_price - pos.entry_price) * pos.size
            else:
                pos.unrealized_pnl = (pos.entry_price - market.mark_price) * pos.size

            # Check health factor
            hf = pos.health_factor
            if hf < self.liquidation_buffer:
                alerts.append({
                    "type": "LIQUIDATION_RISK",
                    "symbol": symbol,
                    "health_factor": hf,
                    "buffer": self.liquidation_buffer,
                })

            # Check funding
            fr = market.funding_rate
            if abs(fr) > self.funding_threshold:
                alerts.append({
                    "type": "HIGH_FUNDING",
                    "symbol": symbol,
                    "funding_rate": fr,
                    "threshold": self.funding_threshold,
                })

        return {"ok": True, "alerts": alerts, "positions": len(self.account.positions)}


# Singleton instance (lazy-loaded)
_engine: PerpsEngine | None = None


def get_engine(wallet: str | None = None) -> PerpsEngine:
    global _engine
    if _engine is None:
        _engine = PerpsEngine(wallet)
    return _engine


def is_enabled() -> bool:
    return get_engine().enabled


def enable_perps(wallet: str | None = None) -> bool:
    return get_engine(wallet).enable()


def disable_perps() -> bool:
    return get_engine().disable()


# CLI for manual control
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Perps engine control (DORMANT by default)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--wallet", type=str)
    ap.add_argument("--markets", action="store_true")
    ap.add_argument("--init-account", action="store_true")
    args = ap.parse_args()

    eng = get_engine(args.wallet)

    if args.status:
        print(json.dumps(eng.status(), indent=2))
    elif args.enable:
        print("Enabled:", eng.enable())
    elif args.disable:
        print("Disabled:", eng.disable())
    elif args.markets:
        eng._refresh_markets()
        for m in eng.markets.values():
            print(f"  {m.symbol}: mark={m.mark_price:.4f} funding={m.funding_rate:.6f} oi=${m.open_interest:,.0f}")
    elif args.init_account:
        if not args.wallet:
            print("Error: --wallet required")
        else:
            acc = eng.initialize_account(args.wallet)
            print(f"Account initialized: {acc.authority}, USDC={acc.usdc_balance:.2f}")
    else:
        ap.print_help()