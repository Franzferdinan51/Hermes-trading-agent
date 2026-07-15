#!/usr/bin/env python3
"""Jupiter Terminal market scanners — Top Traded + Cooking feeds.

Fetches live token lists from Jupiter Terminal (top-traded, newly cooking)
and surfaces opportunities: volume spikes, price momentum, new listings,
meme/cooking tokens with tightening liquidity.

API: https://api.jup.ag/terminal/v1 (inferred)
Fallback: scrape via browser automation if API returns empty.

Enabled by policy. Uses Jupiter Terminal when available, then CoinGecko Solana ecosystem discovery as a data-only fallback. Every candidate still requires a fresh Jupiter quote and policy guard before execution.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
RULES_FILE = STATE / "state" / "position_rules.json"
RULES_FILE_FALLBACK = ROOT / "state" / "position_rules.json"

# Resolve rules file (supports both repo layouts)
if RULES_FILE.exists():
    RULES = RULES_FILE
elif RULES_FILE_FALLBACK.exists():
    RULES = RULES_FILE_FALLBACK
else:
    RULES = RULES_FILE_FALLBACK

# Jupiter Terminal API
TERMINAL_V1 = "https://api.jup.ag/terminal/v1"
TERMINAL_PRICE = "https://api.jup.ag/price/v2"


def _http_json(url: str, timeout: int = 15) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Hermes trading agent)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return {}


@dataclass
class TerminalToken:
    """A token entry from Jupiter Terminal."""
    mint: str
    symbol: str
    name: str
    price: float
    price_change_pct: float        # 24h % change
    market_cap: float | None
    fdv: float | None              # fully diluted valuation
    volume_24h: float | None
    liquidity: float | None
    age_days: int | None            # days since launch
    holders: int | None
    # Top-traded specific
    txns_24h: int | None
    traders_24h: int | None
    # Cooking-specific
    fees_paid_24h: float | None
    is_verified: bool = False
    is_new: bool = False            # listed < 7 days
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"         # "top-traded" | "cooking"


@dataclass
class MarketScan:
    """Result of a market scan pass."""
    scan_ts: str
    source: str                    # "top-traded" | "cooking"
    sort_by: str
    total_tokens: int
    tokens: list[TerminalToken]
    alerts: list[dict]             # volume spikes, new listings, price pumps


class TerminalClient:
    """Jupiter Terminal API client."""

    def __init__(self, api_base: str = TERMINAL_V1):
        self.api_base = api_base

    def fetch_top_traded(self, limit: int = 50) -> list[TerminalToken]:
        """Fetch top-traded tokens; fall back to current authenticated Jupiter verified-token feed."""
        data = _http_json(f"{self.api_base}/top-traded?limit={limit}")
        if data:
            entries = data if isinstance(data, list) else data.get("data", data.get("tokens", []))
            return [self._parse_token(t, source="top-traded") for t in entries if isinstance(t, dict)]
        return self.fetch_verified_tokens(limit)

    def fetch_verified_tokens(self, limit: int = 50) -> list[TerminalToken]:
        """Fallback discovery from CoinGecko Solana ecosystem; execution still requires Jupiter quote verification."""
        try:
            url="https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=solana-ecosystem&order=volume_desc&per_page="+str(min(limit,50))+"&page=1"
            req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"Hermes market scanner"})
            with urllib.request.urlopen(req,timeout=25) as r: rows=json.loads(r.read())
            out=[]
            for t in rows:
                try:
                    cid=t.get("id"); detail_req=urllib.request.Request(f"https://api.coingecko.com/api/v3/coins/{cid}?localization=false&tickers=false&market_data=false&community_data=false&developer_data=false",headers={"User-Agent":"Hermes market scanner"})
                    with urllib.request.urlopen(detail_req,timeout=15) as dr: detail=json.loads(dr.read())
                    mint=(detail.get("platforms",{}).get("solana") or "")
                    if not mint: continue
                    out.append(TerminalToken(mint=mint,symbol=t.get("symbol","?").upper(),name=t.get("name","?"),price=float(t.get("current_price") or 0),price_change_pct=float(t.get("price_change_percentage_24h") or 0),market_cap=self._float(t.get("market_cap")),fdv=self._float(t.get("fully_diluted_valuation")),volume_24h=self._float(t.get("total_volume")),liquidity=None,age_days=None,holders=None,txns_24h=None,traders_24h=None,fees_paid_24h=None,is_verified=False,source="coingecko-solana-fallback"))
                except Exception: continue
            return out
        except Exception: return []

    def fetch_verified_tokens_legacy(self, limit: int = 50) -> list[TerminalToken]:
        try:
            key = subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", "jupiter-api-key", "-w"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
            req = urllib.request.Request("https://api.jup.ag/tokens/v2/tag?query=verified", headers={"x-api-key": key, "Accept": "application/json", "User-Agent": "Hermes trading agent"})
            with urllib.request.urlopen(req, timeout=25) as r: raw = json.loads(r.read())
            entries = raw if isinstance(raw, list) else raw.get("data", raw.get("tokens", []))
            out=[]
            for t in entries[:limit]:
                mint=t if isinstance(t,str) else t.get("id", t.get("address", t.get("mint", "")))
                if not mint: continue
                meta=t if isinstance(t,dict) else {}
                out.append(TerminalToken(mint=mint, symbol=meta.get("symbol", "UNKNOWN"), name=meta.get("name", meta.get("symbol", "UNKNOWN")), price=0.0, price_change_pct=0.0, market_cap=None, fdv=None, volume_24h=None, liquidity=None, age_days=None, holders=None, txns_24h=None, traders_24h=None, fees_paid_24h=None, is_verified=True, source="jupiter-verified-fallback"))
            return out
        except Exception:
            return []

    def fetch_cooking(self, limit: int = 50, sort_by: str = "listedTime") -> list[TerminalToken]:
        """Fetch newly cooking/meme tokens, sorted by listing time."""
        # cooking endpoint: sorted by listedTime desc = newest first
        data = _http_json(f"{self.api_base}/cooking?sortBy={sort_by}&sortDir=desc&limit={limit}")
        if not data:
            return []
        entries = data if isinstance(data, list) else data.get("data", data.get("tokens", []))
        tokens = []
        for t in entries:
            try:
                tokens.append(self._parse_token(t, source="cooking"))
            except Exception:
                continue
        return tokens

    def fetch_token_price(self, mint: str) -> float | None:
        """Fetch current USD price for a mint."""
        data = _http_json(f"{TERMINAL_PRICE}?ids={mint}")
        if not data:
            return None
        try:
            return float(data.get("data", {}).get(mint, {}).get("price", 0))
        except Exception:
            return None

    def _parse_token(self, t: dict, source: str) -> TerminalToken:
        """Parse a token dict into TerminalToken."""
        now = int(time.time())
        # listed_ts may be in various formats
        listed_ts = t.get("listedTs", t.get("createdAt", t.get("launchTimestamp", 0)))
        age_days = (now - listed_ts) / 86400 if listed_ts else None

        return TerminalToken(
            mint=t.get("mint", t.get("address", "")),
            symbol=t.get("symbol", t.get("name", "???")),
            name=t.get("name", t.get("symbol", "???")),
            price=float(t.get("priceUsd", t.get("price", 0) or 0)),
            price_change_pct=float(t.get("priceChange24h", t.get("priceChange", 0) or 0)),
            market_cap=self._float(t.get("marketCap", t.get("mc", t.get("cap", None)))),
            fdv=self._float(t.get("fdv", t.get("fdvUsd", None))),
            volume_24h=self._float(t.get("volume24h", t.get("volumeUsd24h", None))),
            liquidity=self._float(t.get("liquidity", t.get("liq", None))),
            age_days=int(age_days) if age_days is not None else None,
            holders=self._int(t.get("holders", t.get("numHolders", None))),
            txns_24h=self._int(t.get("txns24h", t.get("txCount24h", None))),
            traders_24h=self._int(t.get("traders24h", t.get("tradersCount24h", None))),
            fees_paid_24h=self._float(t.get("feesPaid24h", t.get("fees24h", None))),
            is_verified=bool(t.get("isVerified", t.get("verified", False))),
            is_new=age_days < 7 if age_days is not None else False,
            tags=t.get("tags", t.get("categories", [])),
            source=source,
        )

    def _float(self, v) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _int(self, v) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class MarketScanner:
    """Scans Jupiter Terminal feeds for trading opportunities — DORMANT by default."""

    def __init__(self):
        self.client = TerminalClient()
        self._enabled = False
        self._load_config()

    def _load_config(self) -> None:
        try:
            rules = json.loads(RULES.read_text())
            cfg = rules.get("global", {}).get("market_scanner", {})
            self._enabled = cfg.get("enabled", False)
            self.min_volume_usd = cfg.get("min_volume_usd", 5000)
            self.min_liquidity_usd = cfg.get("min_liquidity_usd", 1000)
            self.max_age_days = cfg.get("max_age_days", 365)
            self.max_position_pct_nav = cfg.get("max_position_pct_nav", 0.02)
            self.top_traded_limit = cfg.get("top_traded_limit", 50)
            self.cooking_limit = cfg.get("cooking_limit", 50)
            self.allowed_tags = set(cfg.get("allowed_tags", ["defi", "utility", "governance"]))
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> bool:
        self._enabled = True
        self._persist_enable()
        return True

    def disable(self) -> bool:
        self._enabled = False
        self._persist_enable()
        return True

    def _persist_enable(self) -> None:
        rules = json.loads(RULES.read_text())
        rules.setdefault("global", {}).setdefault("market_scanner", {})["enabled"] = self._enabled
        RULES.write_text(json.dumps(rules, indent=2) + "\n")

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "config": {
                "min_volume_usd": self.min_volume_usd,
                "min_liquidity_usd": self.min_liquidity_usd,
                "max_age_days": self.max_age_days,
                "max_position_pct_nav": self.max_position_pct_nav,
                "allowed_tags": list(self.allowed_tags),
            }
        }

    def scan_top_traded(self, limit: int | None = None) -> MarketScan:
        """Scan top-traded tokens for volume/momentum opportunities."""
        lim = limit or self.top_traded_limit
        tokens = self.client.fetch_top_traded(limit=lim)
        filtered, alerts = self._filter_and_analyze(tokens, source="top-traded")
        return MarketScan(
            scan_ts=datetime.now(timezone.utc).isoformat(),
            source="top-traded",
            sort_by="volume24h",
            total_tokens=len(tokens),
            tokens=filtered,
            alerts=alerts,
        )

    def scan_cooking(self, limit: int | None = None) -> MarketScan:
        """Scan newly cooking/meme tokens for early-stage opportunities."""
        lim = limit or self.cooking_limit
        tokens = self.client.fetch_cooking(limit=lim, sort_by="listedTime")
        filtered, alerts = self._filter_and_analyze(tokens, source="cooking")
        return MarketScan(
            scan_ts=datetime.now(timezone.utc).isoformat(),
            source="cooking",
            sort_by="listedTime",
            total_tokens=len(tokens),
            tokens=filtered,
            alerts=alerts,
        )

    def _filter_and_analyze(self, tokens: list[TerminalToken], source: str) -> tuple[list[TerminalToken], list[dict]]:
        """Apply filters and generate alerts."""
        alerts = []
        passed = []
        now = int(time.time())

        for t in tokens:
            # Age filter
            if t.age_days is not None and t.age_days > self.max_age_days:
                continue

            # Liquidity filter
            if t.liquidity is not None and t.liquidity < self.min_liquidity_usd:
                continue

            # Volume filter
            if t.volume_24h is not None and t.volume_24h < self.min_volume_usd:
                continue

            # Skip if no meaningful data
            if t.price <= 0 and t.volume_24h is None:
                continue

            # Tag filter (if tags present)
            if t.tags and self.allowed_tags:
                if not any(tag.lower() in [t.lower() for t in self.allowed_tags] for tag in t.tags):
                    continue

            # Alert: new listing
            if t.is_new and t.liquidity and t.liquidity >= self.min_liquidity_usd:
                alerts.append({
                    "type": "NEW_LISTING",
                    "symbol": t.symbol,
                    "mint": t.mint,
                    "age_days": round(t.age_days, 1),
                    "liquidity": t.liquidity,
                    "volume_24h": t.volume_24h,
                    "price": t.price,
                })

            # Alert: volume spike (> 3x avg, flag as notable)
            if t.volume_24h and t.liquidity and t.volume_24h / self._nz(t.liquidity) > 0.5:
                alerts.append({
                    "type": "VOLUME_SPIKE",
                    "symbol": t.symbol,
                    "mint": t.mint,
                    "volume_24h": t.volume_24h,
                    "liquidity": t.liquidity,
                    "vol_to_liq_ratio": round(t.volume_24h / self._nz(t.liquidity), 2),
                    "price_change_24h_pct": t.price_change_pct,
                })

            # Alert: price pump (> 20% in 24h)
            if abs(t.price_change_pct) > 20:
                alerts.append({
                    "type": "PRICE_PUMP" if t.price_change_pct > 0 else "PRICE_DUMP",
                    "symbol": t.symbol,
                    "mint": t.mint,
                    "price_change_24h_pct": t.price_change_pct,
                    "volume_24h": t.volume_24h,
                    "liquidity": t.liquidity,
                })

            passed.append(t)

        return passed, alerts

    def _nz(self, v: float | None) -> float:
        return v if v else 0.0001

    def format_scan(self, scan: MarketScan) -> str:
        """Format a scan result as readable text."""
        lines = [
            f"\n{'='*60}",
            f"JUPITER TERMINAL SCAN | {scan.source.upper()} | {scan.scan_ts}",
            f"Total fetched: {scan.total_tokens} | Passed filters: {len(scan.tokens)}",
            f"{'='*60}",
        ]
        if scan.alerts:
            lines.append(f"\n🚨 ALERTS ({len(scan.alerts)}):")
            for a in scan.alerts[:10]:
                lines.append(f"  [{a['type']}] {a.get('symbol','???')} | "
                             f"vol=${a.get('volume_24h','?'):,.0f} | "
                             f"liq=${a.get('liquidity','?'):,.0f} | "
                             f"%Δ={a.get('price_change_24h_pct','?')}")

        if scan.tokens:
            lines.append(f"\n📊 TOP TOKENS (filtered):")
            for t in scan.tokens[:15]:
                lines.append(
                    f"  {t.symbol:10s} | ${t.price:>12.6f} | "
                    f"%Δ={t.price_change_pct:+7.2f} | "
                    f"vol=${(t.volume_24h or 0):>10,.0f} | "
                    f"liq=${(t.liquidity or 0):>10,.0f} | "
                    f"{t.age_days}d old"
                )
        else:
            lines.append("\n(no tokens passed filters — try lowering min_volume_usd / min_liquidity_usd)")

        return "\n".join(lines)


_engine: MarketScanner | None = None


def get_engine() -> MarketScanner:
    global _engine
    if _engine is None:
        _engine = MarketScanner()
    return _engine


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Jupiter Terminal market scanner (DORMANT by default)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--top-traded", action="store_true", help="scan top-traded tokens")
    ap.add_argument("--cooking", action="store_true", help="scan cooking/new tokens")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--min-volume", type=float, default=5000)
    ap.add_argument("--min-liquidity", type=float, default=1000)
    args = ap.parse_args()

    eng = get_engine()

    if args.status:
        print(json.dumps(eng.status(), indent=2))
    elif args.enable:
        print("Enabled:", eng.enable())
    elif args.disable:
        print("Disabled:", eng.disable())
    elif args.top_traded:
        if not eng.enabled:
            print("Scanner disabled. Use --enable first.")
        else:
            scan = eng.scan_top_traded(limit=args.limit)
            print(eng.format_scan(scan))
    elif args.cooking:
        if not eng.enabled:
            print("Scanner disabled. Use --enable first.")
        else:
            scan = eng.scan_cooking(limit=args.limit)
            print(eng.format_scan(scan))
    else:
        ap.print_help()