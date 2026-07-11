#!/usr/bin/env python3
"""Macro intelligence monitor — DORMANT by default.

Monitors the broader market environment that affects crypto:
- BTC price, dominance, correlation to equities
- Fear & Greed index (alternative.me free API)
- US macro: DXY, 10Y yield, S&P 500, VIX
- Crypto news headlines (CoinGecko news free API)
- Upcoming macro events (FED, CPI, NFP dates)
- Solana network health (TPS,活跃验证器)

Each pass returns an `EnvironmentReport` with all signals and any alerts.
Enable by setting `macro_monitor.enabled = true` in state/position_rules.json.
"""
from __future__ import annotations

import calendar
import json
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
RULES = STATE / "position_rules.json"

# ─── Free API endpoints ────────────────────────────────────────────────────

COINGECKO_API = "https://api.coingecko.com/api/v3"
COINPAPRIKA_API = "https://api.coinpaprika.com/v1"
FRED_API = "https://api.stlouisfed.org/fred"
ALTERNATIVES_ME = "https://api.alternative.me"


def _http_json(url: str, timeout: int = 15) -> dict | list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Hermes trading agent)",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _http_text(url: str, timeout: int = 15) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Hermes trading agent)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()
    except Exception:
        return ""


# ─── Data models ─────────────────────────────────────────────────────────────

@dataclass
class BTCSignal:
    price_usd: float
    change_24h_pct: float
    dominance_pct: float          # BTC dominance by market cap
    eth_btc_ratio: float          # ETH/BTC price ratio (correlation proxy)
    volume_24h_usd: float | None


@dataclass
class EquityBondSignal:
    sp500_price: float | None
    sp500_change_24h_pct: float | None
    dxy_index: float | None        # US Dollar Index
    dxy_change_24h_pct: float | None
    us10y_yield_pct: float | None
    yield_change_24h_bps: float | None
    vix_index: float | None


@dataclass
class FearGreedSignal:
    value: int                     # 0-100
    label: str                    # "Extreme Fear" / "Fear" / "Neutral" / "Greed" / "Extreme Greed"
    prev_value: int
    timestamp: str


@dataclass
class NetworkHealth:
    solana_tps: float | None
    solana_validator_count: int | None
    solana_slot: int | None


@dataclass
class NewsItem:
    headline: str
    source: str
    url: str
    published_ts: int
    related: list[str]             # tickers mentioned e.g. ["BTC", "SOL"]


@dataclass
class MacroCalendarEvent:
    name: str                      # "FOMC Meeting", "CPI Release", "NFP"
    date_ts: int
    impact: str                    # "high" / "medium" / "low"
    prior: str | None
    forecast: str | None


@dataclass
class EnvironmentAlert:
    type: str                      # "FEAR_GREED_EXTREME" / "BTC_CORRELATION_SHIFT" / "DOLLAR_SPIKE" / etc.
    severity: str                  # "warning" / "critical" / "info"
    message: str
    data: dict


@dataclass
class EnvironmentReport:
    ts: str
    btc: BTCSignal | None
    equity_bond: EquityBondSignal | None
    fear_greed: FearGreedSignal | None
    network: NetworkHealth | None
    news: list[NewsItem]
    calendar: list[MacroCalendarEvent]
    alerts: list[EnvironmentAlert]


# ─── Source clients ────────────────────────────────────────────────────────────

class CoinGeckoClient:
    """Free CoinGecko API — no auth required, rate-limited."""

    RATE_LIMITED = False           # track to avoid hammering

    def get_btc(self) -> BTCSignal | None:
        try:
            data = _http_json(
                f"{COINGECKO_API}/coins/markets"
                f"?vs_currency=usd&ids=bitcoin,ethereum&order=market_cap_desc"
                f"&per_page=2&page=1&sparkline=false&price_change_percentage=24h"
            )
            if not data or len(data) < 2:
                return None
            btc = data[0]
            eth = data[1]
            return BTCSignal(
                price_usd=float(btc.get("current_price", 0)),
                change_24h_pct=float(btc.get("price_change_percentage_24h", 0)),
                dominance_pct=float(btc.get("market_cap_percentage", 0)),
                eth_btc_ratio=float(eth.get("current_price", 0)) / max(float(btc.get("current_price", 1)), 1),
                volume_24h_usd=float(btc.get("total_volume", 0)),
            )
        except Exception:
            return None

    def get_news(self, limit: int = 10) -> list[NewsItem]:
        try:
            data = _http_json(f"{COINGECKO_API}/news?per_page={limit}")
            items = data.get("data", []) if isinstance(data, dict) else data
            news = []
            for item in (items if isinstance(items, list) else [])[:limit]:
                news.append(NewsItem(
                    headline=item.get("title", ""),
                    source=item.get("news_base_url", item.get("feed_id", "unknown")),
                    url=item.get("url", ""),
                    published_ts=int(item.get("published_at", 0) or 0),
                    related=[t.get("name", "") for t in item.get("tiles", []) if isinstance(item.get("tiles"), list)],
                ))
            return news
        except Exception:
            return []


class FearGreedClient:
    """Alternative.me Fear & Greed Index — free, no auth."""

    def get(self) -> FearGreedSignal | None:
        try:
            data = _http_json(f"{ALTERNATIVES_ME}/fng?limit=2")
            items = data.get("data", []) if isinstance(data, dict) else data
            if not items or len(items) < 2:
                return None
            latest = items[0]
            prev = items[1]
            v = int(latest.get("value", 50))
            return FearGreedSignal(
                value=v,
                label=self._label(v),
                prev_value=int(prev.get("value", v)),
                timestamp=latest.get("timestamp", ""),
            )
        except Exception:
            return None

    @staticmethod
    def _label(v: int) -> str:
        if v <= 20:  return "Extreme Fear"
        if v <= 40:  return "Fear"
        if v <= 60:  return "Neutral"
        if v <= 80:  return "Greed"
        return "Extreme Greed"


class CoinPaprikaClient:
    """CoinPaprika free API — no auth, good for multi-timeframe BTC/ETH/SOL data."""

    # Coin IDs for our holdings
    COIN_IDS = {
        "BTC":  "btc-bitcoin",
        "ETH":  "eth-ethereum",
        "SOL":  "sol-solana",
        "JUP":  "jup-jupiter",
        "cbBTC": "cbbetc-coinbase-wrapped-btc",
        "ANSEM": "ansem-neural-frankenstein",
    }

    def get_ticker(self, coin_id: str) -> dict | None:
        try:
            return _http_json(f"{COINPAPRIKA_API}/tickers/{coin_id}")
        except Exception:
            return None

    def get_multi_ticker(self, ids: list[str]) -> dict[str, dict]:
        """Fetch tickers for multiple coins. Returns {symbol: ticker_data}."""
        results = {}
        for cid in ids:
            data = self.get_ticker(cid)
            if data:
                results[cid] = data
        return results

    def btc_multi_timeframe(self) -> dict:
        """Get BTC price changes across multiple timeframes."""
        ticker = self.get_ticker(self.COIN_IDS["BTC"])
        if not ticker:
            return {}
        q = ticker.get("quotes", {}).get("USD", {})
        return {
            "price": q.get("price"),
            "change_15m_pct":  q.get("percent_change_15m"),
            "change_30m_pct":  q.get("percent_change_30m"),
            "change_1h_pct":   q.get("percent_change_1h"),
            "change_6h_pct":    q.get("percent_change_6h"),
            "change_12h_pct":   q.get("percent_change_12h"),
            "change_24h_pct":   q.get("percent_change_24h"),
            "change_7d_pct":    q.get("percent_change_7d"),
            "change_30d_pct":   q.get("percent_change_30d"),
            "change_1y_pct":    q.get("percent_change_1y"),
            "ath_price":        q.get("ath_price"),
            "ath_date":         q.get("ath_date"),
            "from_ath_pct":     q.get("percent_from_price_ath"),
            "volume_24h":       q.get("volume_24h"),
            "market_cap":       q.get("market_cap"),
        }

    def portfolio_tickers(self) -> dict[str, dict]:
        """Fetch all our holdings' tickers from CoinPaprika."""
        results = {}
        for symbol, coin_id in self.COIN_IDS.items():
            data = self.get_ticker(coin_id)
            if data:
                q = data.get("quotes", {}).get("USD", {})
                results[symbol] = {
                    "name":      data.get("name", symbol),
                    "symbol":    data.get("symbol", symbol),
                    "rank":      data.get("rank"),
                    "price":     q.get("price"),
                    "change_1h":  q.get("percent_change_1h"),
                    "change_24h":  q.get("percent_change_24h"),
                    "change_7d":   q.get("percent_change_7d"),
                    "change_30d":  q.get("percent_change_30d"),
                    "volume_24h":  q.get("volume_24h"),
                    "market_cap":  q.get("market_cap"),
                    "ath_price":   q.get("ath_price"),
                    "from_ath_pct": q.get("percent_from_price_ath"),
                }
        return results


class MacroClient:
    """Public macro data — FRED (treasuries, DXY) + Yahoo Finance (S&P 500)."""

    def get_equity_bond(self) -> EquityBondSignal | None:
        signals = EquityBondSignal(
            sp500_price=None, sp500_change_24h_pct=None,
            dxy_index=None, dxy_change_24h_pct=None,
            us10y_yield_pct=None, yield_change_24h_bps=None,
            vix_index=None,
        )
        # Try Yahoo Finance for S&P 500 and VIX (no API key needed for basic quotes)
        try:
            yahoo = _http_json("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=2d")
            qo = yahoo.get("chart", {}).get("result", [{}])[0]
            meta = qo.get("meta", {})
            sp500 = meta.get("regularMarketPrice")
            sp500_prev = qo.get("indicators", {}).get("quote", [{}])[0].get("close", [sp500])
            if sp500 and len(sp500_prev) >= 2:
                signals.sp500_price = float(sp500)
                signals.sp500_change_24h_pct = (float(sp500) - float(sp500_prev[-2])) / float(sp500_prev[-2]) * 100 if sp500_prev[-2] else 0
        except Exception:
            pass

        # DXY via FRED (free account, no key for some endpoints)
        try:
            fred_data = _http_json("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DXY&vintage_date=2026-07-11")
            if fred_data and isinstance(fred_data, str):
                lines = fred_data.strip().split("\n")
                if len(lines) >= 2:
                    last = lines[-1].split(",")
                    prev = lines[-2].split(",")
                    if len(last) >= 2:
                        signals.dxy_index = float(last[-1])
                        if len(prev) >= 2:
                            signals.dxy_change_24h_pct = float(last[-1]) - float(prev[-1])
        except Exception:
            pass

        return signals


class MacroCalendarClient:
    """Known macro event dates (2026) — hard-coded, no API needed."""

    # (name, naive_date, impact)
    EVENTS_2026 = [
        ("FOMC Meeting",          datetime(2026, 1, 28),  "high"),
        ("CPI Release",           datetime(2026, 2, 10),  "high"),
        ("NFP Release",          datetime(2026, 2, 6),   "high"),
        ("FOMC Meeting",          datetime(2026, 3, 17),  "high"),
        ("CPI Release",           datetime(2026, 3, 10),  "high"),
        ("NFP Release",          datetime(2026, 3, 6),   "medium"),
        ("FOMC Meeting",          datetime(2026, 4, 28),  "high"),
        ("CPI Release",           datetime(2026, 5, 12),  "high"),
        ("NFP Release",          datetime(2026, 5, 8),   "medium"),
        ("FOMC Meeting",          datetime(2026, 6, 16),  "high"),
        ("CPI Release",           datetime(2026, 6, 9),   "high"),
        ("NFP Release",          datetime(2026, 6, 5),   "medium"),
        ("FOMC Meeting",          datetime(2026, 7, 28),  "high"),
        ("CPI Release",           datetime(2026, 7, 14),  "high"),
        ("NFP Release",          datetime(2026, 7, 10),  "medium"),
        ("FOMC Meeting",          datetime(2026, 9, 15),  "high"),
        ("CPI Release",           datetime(2026, 9, 10),  "high"),
        ("NFP Release",          datetime(2026, 9, 4),   "medium"),
        ("FOMC Meeting",          datetime(2026, 10, 27), "high"),
        ("CPI Release",           datetime(2026, 10, 13), "high"),
        ("NFP Release",          datetime(2026, 10, 3),  "medium"),
        ("US Election",           datetime(2026, 11, 3),  "high"),
        ("FOMC Meeting",          datetime(2026, 11, 4),  "high"),
        ("CPI Release",           datetime(2026, 11, 10), "high"),
        ("NFP Release",          datetime(2026, 11, 6),  "medium"),
        ("FOMC Meeting",          datetime(2026, 12, 15), "high"),
        ("CPI Release",           datetime(2026, 12, 10), "high"),
        ("NFP Release",          datetime(2026, 12, 4),  "medium"),
    ]

    def upcoming(self, days: int = 14) -> list[MacroCalendarEvent]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        events = []
        for name, dt, impact in self.EVENTS_2026:
            aware = dt.replace(tzinfo=timezone.utc)
            if now <= aware <= cutoff:
                events.append(MacroCalendarEvent(
                    name=name,
                    date_ts=int(aware.timestamp()),
                    impact=impact,
                    prior=None,
                    forecast=None,
                ))
        return events


class SolanaHealthClient:
    """Solana network health via public RPC."""

    def get(self) -> NetworkHealth | None:
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getHealth"}).encode()
            req = urllib.request.Request(
                "https://api.mainnet-beta.solana.com",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                result = json.loads(r.read()).get("result", {})
            return NetworkHealth(
                solana_tps=float(result.get("tps", 0)),
                solana_validator_count=result.get("validatorCount"),
                solana_slot=result.get("slot"),
            )
        except Exception:
            return None


# ─── Engine ───────────────────────────────────────────────────────────────────

class MacroMonitor:
    """Macro intelligence engine — DORMANT by default."""

    def __init__(self):
        self.cg = CoinGeckoClient()
        self.cp = CoinPaprikaClient()
        self.fg = FearGreedClient()
        self.macro = MacroClient()
        self.calendar = MacroCalendarClient()
        self.sol = SolanaHealthClient()
        self._enabled = False
        self._load_config()

    def _load_config(self) -> None:
        try:
            rules = json.loads(RULES.read_text())
            cfg = rules.get("global", {}).get("macro_monitor", {})
            self._enabled = cfg.get("enabled", False)
            self.min_volume_usd = cfg.get("min_volume_usd", 5000)
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
        rules.setdefault("global", {}).setdefault("macro_monitor", {})["enabled"] = self._enabled
        RULES.write_text(json.dumps(rules, indent=2) + "\n")

    def status(self) -> dict:
        return {"enabled": self._enabled}

    def scan(self) -> EnvironmentReport:
        """Full macro environment scan."""
        alerts: list[EnvironmentAlert] = []

        btc = self.cg.get_btc()

        # CoinPaprika multi-timeframe BTC data
        cp_btc = self.cp.btc_multi_timeframe()
        if cp_btc and cp_btc.get("price"):
            # Alert: BTC ATH proximity
            from_ath = cp_btc.get("from_ath_pct", 0)
            if from_ath and from_ath > -5:  # within 5% of ATH
                alerts.append(EnvironmentAlert(
                    type="BTC_NEAR_ATH", severity="info",
                    message=f"BTC {abs(from_ath):.1f}% from ATH — {cp_btc.get('ath_date', '?')} was ${cp_btc.get('ath_price', 0):,.0f}",
                    data={"from_ath_pct": from_ath, "ath_price": cp_btc.get("ath_price")},
                ))
            # Alert: BTC momentum shift — short timeframes diverging from longer
            change_1h = cp_btc.get("change_1h_pct", 0)
            change_24h = cp_btc.get("change_24h_pct", 0)
            if change_1h and change_24h and change_1h > 2 and change_24h < -1:
                alerts.append(EnvironmentAlert(
                    type="BTC_MOMENTUM_SHIFT", severity="warning",
                    message=f"BTC 1h: {change_1h:+.2f}% vs 24h: {change_24h:+.2f}% — short-term reversal signal",
                    data={"change_1h": change_1h, "change_24h": change_24h},
                ))

        # Portfolio tickers for all our holdings
        portfolio = self.cp.portfolio_tickers()
        for symbol, ticker in portfolio.items():
            change_24h = ticker.get("change_24h", 0) or 0
            change_7d  = ticker.get("change_7d", 0) or 0
            price = ticker.get("price")
            # Alert: large daily move
            if abs(change_24h) > 15:
                alerts.append(EnvironmentAlert(
                    type=f"{symbol}_BIG_MOVE",
                    severity="warning" if change_24h > 0 else "critical",
                    message=f"{symbol}: {change_24h:+.2f}% today — {'pumping' if change_24h > 0 else 'dumping'}",
                    data={"symbol": symbol, "change_24h": change_24h, "price": price},
                ))
            # Alert: 7-day trend
            if change_7d and abs(change_7d) > 20:
                alerts.append(EnvironmentAlert(
                    type=f"{symbol}_WEEKLY_TREND",
                    severity="info",
                    message=f"{symbol}: {change_7d:+.2f}% this week",
                    data={"symbol": symbol, "change_7d": change_7d, "price": price},
                ))

        if btc:
            if btc.change_24h_pct < -10:
                alerts.append(EnvironmentAlert(
                    type="BTC_DUMP", severity="critical",
                    message=f"BTC down {btc.change_24h_pct:.1f}% in 24h — risk-off environment",
                    data={"price": btc.price_usd, "change_pct": btc.change_24h_pct},
                ))
            elif btc.change_24h_pct > 10:
                alerts.append(EnvironmentAlert(
                    type="BTC_PUMP", severity="warning",
                    message=f"BTC up {btc.change_24h_pct:.1f}% in 24h — momentum",
                    data={"price": btc.price_usd, "change_pct": btc.change_24h_pct},
                ))

        fear_greed = self.fg.get()
        if fear_greed:
            if fear_greed.value <= 20:
                alerts.append(EnvironmentAlert(
                    type="FEAR_GREED_EXTREME_FEAR", severity="warning",
                    message=f"Fear & Greed: {fear_greed.value} ({fear_greed.label}) — potential mean-reversion opportunity",
                    data={"value": fear_greed.value, "label": fear_greed.label},
                ))
            elif fear_greed.value >= 85:
                alerts.append(EnvironmentAlert(
                    type="FEAR_GREED_EXTREME_GREED", severity="warning",
                    message=f"Fear & Greed: {fear_greed.value} ({fear_greed.label}) — caution, market may be topped",
                    data={"value": fear_greed.value, "label": fear_greed.label},
                ))

        equity_bond = self.macro.get_equity_bond()
        if equity_bond and equity_bond.dxy_index:
            if equity_bond.dxy_change_24h_pct and abs(equity_bond.dxy_change_24h_pct) > 0.5:
                alerts.append(EnvironmentAlert(
                    type="DXY_SPIKE" if equity_bond.dxy_change_24h_pct > 0 else "DXY_DROP",
                    severity="info",
                    message=f"DXY moved {equity_bond.dxy_change_24h_pct:+.2f} — {'dollar strength' if equity_bond.dxy_change_24h_pct > 0 else 'weakness'} may pressure crypto",
                    data={"dxy": equity_bond.dxy_index, "change": equity_bond.dxy_change_24h_pct},
                ))

        news = self.cg.get_news(limit=10)
        for n in news:
            # Flag bad news about BTC/SOL major holdings
            hl = n.headline.lower()
            if any(k in hl for k in ["hack", "exploit", "SEC", "ban", "regulation", "liquidat", "collapse"]):
                alerts.append(EnvironmentAlert(
                    type="NEGATIVE_NEWS", severity="info",
                    message=f"News: {n.headline[:100]}",
                    data={"source": n.source, "url": n.url},
                ))

        calendar_events = self.calendar.upcoming(days=14)
        for ev in calendar_events:
            if ev.impact == "high":
                alerts.append(EnvironmentAlert(
                    type="MACRO_CALENDAR",
                    severity="info",
                    message=f"High-impact macro: {ev.name} in {(datetime.fromtimestamp(ev.date_ts, tz=timezone.utc) - datetime.now(timezone.utc)).days} days",
                    data={"name": ev.name, "date_ts": ev.date_ts, "impact": ev.impact},
                ))

        network = self.sol.get()

        return EnvironmentReport(
            ts=datetime.now(timezone.utc).isoformat(),
            btc=btc,
            equity_bond=equity_bond,
            fear_greed=fear_greed,
            network=network,
            news=news,
            calendar=calendar_events,
            alerts=alerts,
        )

    def format_report(self, r: EnvironmentReport) -> str:
        lines = [
            f"\n{'='*60}",
            f"MACRO ENVIRONMENT REPORT | {r.ts}",
            f"{'='*60}",
        ]

        if r.btc:
            b = r.btc
            lines.append(f"\n📈 BTC: ${b.price_usd:,.2f} ({b.change_24h_pct:+.2f}%) | "
                         f"DOM: {b.dominance_pct:.1f}% | ETH/BTC: {b.eth_btc_ratio:.4f}")

        # CoinPaprika multi-timeframe data
        cp_btc = self.cp.btc_multi_timeframe()
        if cp_btc and cp_btc.get("price"):
            p = cp_btc["price"]
            lines.append(f"\n📊 BTC MULTI-TIMEFRAME:")
            tf_lines = []
            for tf, key in [("15m","change_15m_pct"),("30m","change_30m_pct"),
                              ("1h","change_1h_pct"),("6h","change_6h_pct"),
                              ("12h","change_12h_pct"),("24h","change_24h_pct"),
                              ("7d","change_7d_pct"),("30d","change_30d_pct"),("1y","change_1y_pct")]:
                v = cp_btc.get(key)
                if v is not None:
                    tf_lines.append(f"{tf}: {v:+.2f}%")
            if tf_lines:
                lines.append("  " + " | ".join(tf_lines))
            from_ath = cp_btc.get("from_ath_pct")
            ath_price = cp_btc.get("ath_price")
            if from_ath is not None and ath_price:
                lines.append(f"  ATH: ${ath_price:,.0f} ({from_ath:+.2f}% from ATH)")

        # Full portfolio tickers from CoinPaprika
        portfolio = self.cp.portfolio_tickers()
        if portfolio:
            lines.append(f"\n🪙 PORTFOLIO TICKERS ({len(portfolio)} coins):")
            lines.append(f"  {'SYMBOL':<8} {'PRICE':>12} {'24h':>8} {'7d':>8} {'30d':>8} {'MC Rank':>8} {'ATH %':>8}")
            lines.append(f"  {'-'*8} {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
            for symbol in ["BTC", "ETH", "SOL", "JUP", "cbBTC", "ANSEM"]:
                t = portfolio.get(symbol)
                if not t:
                    continue
                price = t.get("price")
                c24 = t.get("change_24h")
                c7  = t.get("change_7d")
                c30 = t.get("change_30d")
                rank = t.get("rank")
                from_ath = t.get("from_ath_pct")
                price_s = f"${price:,.6f}" if price and price < 1 else f"${price:,.2f}" if price else "N/A"
                c24_s = f"{c24:+.2f}%" if c24 is not None else "N/A"
                c7_s  = f"{c7:+.2f}%"  if c7 is not None  else "N/A"
                c30_s = f"{c30:+.2f}%" if c30 is not None else "N/A"
                rank_s = f"#{rank}" if rank else "N/A"
                ath_s = f"{from_ath:+.1f}%" if from_ath is not None else "N/A"
                lines.append(f"  {symbol:<8} {price_s:>12} {c24_s:>8} {c7_s:>8} {c30_s:>8} {rank_s:>8} {ath_s:>8}")

        if r.fear_greed:
            fg = r.fear_greed
            emoji = "😱" if fg.value <= 20 else "😨" if fg.value <= 40 else "😐" if fg.value <= 60 else "😁" if fg.value <= 80 else "🤑"
            lines.append(f"{emoji} FEAR & GREED: {fg.value} — {fg.label} (prev: {fg.prev_value})")

        if r.equity_bond:
            eb = r.equity_bond
            parts = []
            if eb.sp500_price:
                parts.append(f"S&P 500: {eb.sp500_price:,.2f} ({eb.sp500_change_24h_pct:+.2f}%)")
            if eb.dxy_index:
                parts.append(f"DXY: {eb.dxy_index:.3f} ({eb.dxy_change_24h_pct:+.2f})")
            if eb.us10y_yield_pct:
                parts.append(f"10Y: {eb.us10y_yield_pct:.3f}% ({eb.yield_change_24h_bps:+.1f}bps)")
            if parts:
                lines.append(f"📉 MACRO: {' | '.join(parts)}")

        if r.network:
            n = r.network
            parts = []
            if n.solana_tps:
                parts.append(f"TPS: {n.solana_tps:,.0f}")
            if n.solana_slot:
                parts.append(f"Slot: {n.solana_slot:,}")
            if parts:
                lines.append(f"🔗 SOLANA: {' | '.join(parts)}")

        if r.calendar:
            lines.append(f"\n📅 UPCOMING ({len(r.calendar)} events):")
            for ev in r.calendar[:5]:
                dt = datetime.fromtimestamp(ev.date_ts, tz=timezone.utc).strftime("%b %d")
                lines.append(f"  [{ev.impact.upper():7s}] {ev.name} — {dt}")

        if r.alerts:
            lines.append(f"\n🚨 ALERTS ({len(r.alerts)}):")
            for a in r.alerts:
                lines.append(f"  [{a.severity.upper():8s}] {a.type}: {a.message}")

        if r.news:
            lines.append(f"\n📰 CRYPTO NEWS ({len(r.news)} headlines):")
            for n in r.news[:5]:
                lines.append(f"  • {n.headline[:90]}")

        return "\n".join(lines)


_engine: MacroMonitor | None = None


def get_engine() -> MacroMonitor:
    global _engine
    if _engine is None:
        _engine = MacroMonitor()
    return _engine


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Macro intelligence monitor (DORMANT by default)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--scan", action="store_true", help="run full macro scan")
    args = ap.parse_args()

    eng = get_engine()

    if args.status:
        print(json.dumps(eng.status(), indent=2))
    elif args.enable:
        print("Enabled:", eng.enable())
    elif args.disable:
        print("Disabled:", eng.disable())
    elif args.scan:
        if not eng.enabled:
            print("Macro monitor disabled. Use --enable first.")
        else:
            report = eng.scan()
            print(eng.format_report(report))
    else:
        ap.print_help()