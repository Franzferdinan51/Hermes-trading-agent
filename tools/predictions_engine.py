#!/usr/bin/env python3
"""Prediction markets engine — DORMANT by default.

Scans Jupiter Terminal prediction markets (YES/NO outcome tokens priced 0-1 USDC).
Each market is a binary question with expiry. The engine:
- Fetches open markets from Jupiter Terminal API
- Calculates implied probability from token prices
- Compares against external probability sources (odds, models)
- Flags markets where edge > threshold
- Supports position sizing, expiry tracking, auto-resolve

Enable by setting `predictions.enabled = true` in state/position_rules.json.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
RULES_FILE = STATE / "position_rules.json"

# Jupiter Terminal API
TERMINAL_API = "https://terminal.jup.ag/api"
TERMINAL_MARKETS = f"{TERMINAL_API}/markets"
TERMINAL_MARKET = f"{TERMINAL_API}/markets/{{market_id}}"
TERMINAL_ORDERBOOK = f"{TERMINAL_API}/orderbook/{{market_id}}"

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
class PredictionMarket:
    """Jupiter Terminal prediction market."""
    market_id: str
    question: str
    category: str                    # "crypto", "defi", "macro", "sports", etc.
    yes_mint: str                    # YES outcome token
    no_mint: str                     # NO outcome token
    expiry_ts: int                   # Unix timestamp
    resolution_source: str           # "api", "oracle", "manual"
    status: str                      # "open", "resolved", "cancelled"
    # Live data
    yes_price: float = 0.0           # USDC per YES token (0-1)
    no_price: float = 0.0            # USDC per NO token (0-1)
    yes_volume: float = 0.0
    no_volume: float = 0.0
    total_volume: float = 0.0
    implied_prob_yes: float = 0.0    # yes_price / (yes_price + no_price)
    implied_prob_no: float = 0.0
    created_ts: int = 0
    resolved_outcome: str | None = None  # "yes", "no", None


@dataclass
class PredictionPosition:
    """Open prediction market position."""
    market_id: str
    question: str
    side: str                        # "yes" or "no"
    size: float                      # number of outcome tokens
    entry_price: float               # price paid per token
    expiry_ts: int
    invested_usdc: float
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_ts: int = field(default_factory=lambda: int(time.time()))

    @property
    def implied_prob(self) -> float:
        return self.entry_price  # for binary markets, price ≈ probability


class TerminalClient:
    """Jupiter Terminal API client."""

    def __init__(self, api_base: str = TERMINAL_API):
        self.api_base = api_base

    def fetch_markets(self, status: str = "open", category: str | None = None) -> list[PredictionMarket]:
        try:
            params = {"status": status}
            if category:
                params["category"] = category
            url = f"{TERMINAL_MARKETS}?{urllib.parse.urlencode(params)}"
            data = _http_json(url)
            markets = []
            for m in data.get("markets", []):
                markets.append(PredictionMarket(
                    market_id=m["marketId"],
                    question=m["question"],
                    category=m.get("category", "unknown"),
                    yes_mint=m["yesMint"],
                    no_mint=m["noMint"],
                    expiry_ts=m["expiryTimestamp"],
                    resolution_source=m.get("resolutionSource", "api"),
                    status=m.get("status", "open"),
                    yes_price=float(m.get("yesPrice", 0)),
                    no_price=float(m.get("noPrice", 0)),
                    yes_volume=float(m.get("yesVolume", 0)),
                    no_volume=float(m.get("noVolume", 0)),
                    total_volume=float(m.get("totalVolume", 0)),
                    created_ts=m.get("createdTimestamp", 0),
                    resolved_outcome=m.get("resolvedOutcome"),
                ))
            return markets
        except Exception as e:
            print(f"TerminalClient.fetch_markets error: {e}")
            return []

    def fetch_market(self, market_id: str) -> PredictionMarket | None:
        try:
            data = _http_json(f"{TERMINAL_MARKET.format(market_id=market_id)}")
            m = data.get("market", {})
            return PredictionMarket(
                market_id=m["marketId"],
                question=m["question"],
                category=m.get("category", "unknown"),
                yes_mint=m["yesMint"],
                no_mint=m["noMint"],
                expiry_ts=m["expiryTimestamp"],
                resolution_source=m.get("resolutionSource", "api"),
                status=m.get("status", "open"),
                yes_price=float(m.get("yesPrice", 0)),
                no_price=float(m.get("noPrice", 0)),
                yes_volume=float(m.get("yesVolume", 0)),
                no_volume=float(m.get("noVolume", 0)),
                total_volume=float(m.get("totalVolume", 0)),
                created_ts=m.get("createdTimestamp", 0),
                resolved_outcome=m.get("resolvedOutcome"),
            )
        except Exception as e:
            print(f"TerminalClient.fetch_market error: {e}")
            return None

    def fetch_orderbook(self, market_id: str) -> dict | None:
        try:
            return _http_json(f"{TERMINAL_ORDERBOOK.format(market_id=market_id)}")
        except Exception:
            return None


class PredictionsEngine:
    """Prediction markets engine — DORMANT unless enabled in config."""

    def __init__(self, wallet: str | None = None):
        self.wallet = wallet
        self.client = TerminalClient()
        self.markets: dict[str, PredictionMarket] = {}
        self.positions: dict[str, PredictionPosition] = {}
        self._enabled = False
        self._load_config()

    def _load_config(self) -> None:
        try:
            rules = json.loads(RULES_FILE.read_text())
            pred_cfg = rules.get("global", {}).get("predictions", {})
            self._enabled = pred_cfg.get("enabled", False)
            self.max_position_pct_nav = pred_cfg.get("max_position_pct_nav", 0.02)
            self.max_total_pct_nav = pred_cfg.get("max_total_pct_nav", 0.05)
            self.min_edge_bps = pred_cfg.get("min_edge_bps", 200)
            self.allowed_categories = set(pred_cfg.get("allowed_categories", ["crypto", "defi", "macro"]))
            self.auto_resolve = pred_cfg.get("auto_resolve", True)
            self.min_days_to_expiry = pred_cfg.get("min_days_to_expiry", 1)
            self.max_days_to_expiry = pred_cfg.get("max_days_to_expiry", 90)
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> bool:
        if not self._enabled:
            self._enabled = True
            self._persist_enable()
            self.refresh_markets()
        return True

    def disable(self) -> bool:
        self._enabled = False
        self._persist_enable()
        return True

    def _persist_enable(self) -> None:
        rules = json.loads(RULES_FILE.read_text())
        rules.setdefault("global", {}).setdefault("predictions", {})["enabled"] = self._enabled
        RULES_FILE.write_text(json.dumps(rules, indent=2) + "\n")

    def refresh_markets(self) -> int:
        self.markets = {m.market_id: m for m in self.client.fetch_markets()}
        return len(self.markets)

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "markets_loaded": len(self.markets),
            "open_positions": len(self.positions),
            "total_invested": sum(p.invested_usdc for p in self.positions.values()),
            "total_unrealized": sum(p.unrealized_pnl for p in self.positions.values()),
        }

    # --- Market data (safe anytime) ---
    def get_market(self, market_id: str) -> PredictionMarket | None:
        if market_id not in self.markets:
            self.refresh_markets()
        return self.markets.get(market_id)

    def filter_markets(self) -> list[PredictionMarket]:
        """Return markets that meet our criteria."""
        if not self.markets:
            self.refresh_markets()
        now = int(time.time())
        results = []
        for m in self.markets.values():
            if m.status != "open":
                continue
            if m.category not in self.allowed_categories:
                continue
            days_to_expiry = (m.expiry_ts - now) / 86400
            if days_to_expiry < self.min_days_to_expiry or days_to_expiry > self.max_days_to_expiry:
                continue
            if m.total_volume < 1000:  # minimum liquidity
                continue
            results.append(m)
        return results

    # --- Edge detection ---
    def calculate_edge(self, market: PredictionMarket, external_prob: float) -> dict | None:
        """Compare implied probability vs external estimate."""
        implied = market.implied_prob_yes
        edge = abs(external_prob - implied) * 10000  # bps
        if edge < self.min_edge_bps:
            return None
        direction = "yes" if external_prob > implied else "no"
        fair_price = external_prob if direction == "yes" else (1 - external_prob)
        current_price = market.yes_price if direction == "yes" else market.no_price
        return {
            "market_id": market.market_id,
            "question": market.question,
            "direction": direction,
            "implied_prob": implied,
            "external_prob": external_prob,
            "edge_bps": edge,
            "fair_price": fair_price,
            "current_price": current_price,
            "expiry_days": (market.expiry_ts - int(time.time())) / 86400,
        }

    # --- Position management (requires enabled) ---
    def open_position(
        self,
        market_id: str,
        side: str,
        size_usdc: float,
        max_slippage_bps: int = 50,
    ) -> dict:
        if not self._enabled:
            return {"ok": False, "error": "Predictions engine disabled"}
        market = self.get_market(market_id)
        if not market:
            return {"ok": False, "error": "Market not found"}
        if market.status != "open":
            return {"ok": False, "error": "Market not open"}
        if market.category not in self.allowed_categories:
            return {"ok": False, "error": f"Category {market.category} not allowed"}

        # Placeholder for actual order (needs Terminal SDK)
        price = market.yes_price if side == "yes" else market.no_price
        size = size_usdc / price if price > 0 else 0

        pos = PredictionPosition(
            market_id=market_id,
            question=market.question,
            side=side,
            size=size,
            entry_price=price,
            expiry_ts=market.expiry_ts,
            invested_usdc=size_usdc,
        )
        self.positions[market_id] = pos

        return {
            "ok": True,
            "market_id": market_id,
            "side": side,
            "size": size,
            "entry_price": price,
            "invested_usdc": size_usdc,
            "note": "Order placed (placeholder — needs Terminal SDK)",
        }

    def update_positions(self) -> dict:
        """Mark-to-market all open positions."""
        if not self._enabled:
            return {"ok": False, "error": "Engine disabled"}
        alerts = []
        for mid, pos in list(self.positions.items()):
            market = self.get_market(mid)
            if not market:
                continue
            if market.status == "resolved":
                if market.resolved_outcome == pos.side:
                    pos.realized_pnl = pos.size  # 1 USDC per winning token
                else:
                    pos.realized_pnl = 0.0
                pos.unrealized_pnl = 0.0
                alerts.append({"type": "RESOLVED", "market_id": mid, "outcome": market.resolved_outcome, "pnl": pos.realized_pnl})
                del self.positions[mid]
                continue
            # Mark to market
            current_price = market.yes_price if pos.side == "yes" else market.no_price
            pos.current_value = pos.size * current_price
            pos.unrealized_pnl = pos.current_value - pos.invested_usdc
            # Check expiry proximity
            days_left = (market.expiry_ts - int(time.time())) / 86400
            if days_left < 1:
                alerts.append({"type": "EXPIRY_SOON", "market_id": mid, "days": days_left})
        return {"ok": True, "alerts": alerts, "positions": len(self.positions)}

    # --- Probability sources (pluggable) ---
    def fetch_external_probs(self) -> dict[str, float]:
        """Fetch external probability estimates for open markets.
        Override this with real sources: betting odds, prediction models, etc."""
        # Placeholder - returns empty dict
        return {}


_engine: PredictionsEngine | None = None


def get_engine(wallet: str | None = None) -> PredictionsEngine:
    global _engine
    if _engine is None:
        _engine = PredictionsEngine(wallet)
    return _engine


def is_enabled() -> bool:
    return get_engine().enabled


def enable_predictions() -> bool:
    return get_engine().enable()


def disable_predictions() -> bool:
    return get_engine().disable()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Predictions engine (DORMANT by default)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--filter", action="store_true")
    args = ap.parse_args()

    eng = get_engine()

    if args.status:
        print(json.dumps(eng.status(), indent=2))
    elif args.enable:
        print("Enabled:", eng.enable())
    elif args.disable:
        print("Disabled:", eng.disable())
    elif args.refresh:
        print(f"Loaded {eng.refresh_markets()} markets")
    elif args.list:
        eng.refresh_markets()
        for m in eng.markets.values():
            print(f"  {m.market_id}: {m.question[:60]}... | yes={m.yes_price:.4f} no={m.no_price:.4f} | vol=${m.total_volume:,.0f} | exp={(m.expiry_ts-int(time.time()))/86400:.1f}d")
    elif args.filter:
        eng.refresh_markets()
        for m in eng.filter_markets():
            print(f"  {m.market_id}: {m.question[:60]}... | p_yes={m.implied_prob_yes:.3f} | vol=${m.total_volume:,.0f} | exp={(m.expiry_ts-int(time.time()))/86400:.1f}d")
    else:
        ap.print_help()