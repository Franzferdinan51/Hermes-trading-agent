#!/usr/bin/env python3
"""
data_fetcher.py — Hermes Trading Dashboard data layer.

Wraps macro_monitor.py + market_scanner.py and provides clean JSON endpoints
for the Flask dashboard. All calls return {} on failure (graceful degradation).
Stdlib only (urllib.request + json); data_fetcher.py itself needs no extra deps.
"""
from __future__ import annotations

import functools
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ───────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).resolve().parent.parent          # crypto-trading-setup/
TOOLS_DIR = ROOT / "tools"
STATE_DIR = ROOT / "state"
RULES     = STATE_DIR / "position_rules.json"
THESES    = STATE_DIR / "position_theses.json"

# Prepend tools so existing modules import cleanly
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# ── Free API constants ──────────────────────────────────────────────────────

COINGECKO_API    = "https://api.coingecko.com/api/v3"
COINPAPRIKA_API  = "https://api.coinpaprika.com/v1"

# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _get_json(url: str, timeout: int = 15) -> dict | list | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Hermes trading dashboard)",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ── CoinGecko price helper ───────────────────────────────────────────────────

def cg_simple_price(ids: str = "bitcoin,ethereum,solana",
                    vs: str = "usd") -> dict[str, dict]:
    """Returns {coin_id: {usd, usd_24h_change, ...}} or {} on failure."""
    url = f"{COINGECKO_API}/simple/price?ids={ids}&vs_currencies={vs}&include_24hr_change=true"
    result = _get_json(url) or {}
    return result if isinstance(result, dict) else {}


# ── CoinPaprika OHLCV ────────────────────────────────────────────────────────

COINPAPRIKA_IDS = {
    "BTC": "btc-bitcoin",
    "ETH": "eth-ethereum",
    "SOL": "sol-solana",
}


def paprika_ohlcv(symbol: str, interval: str = "hour") -> list[dict]:
    """
    Fetch OHLCV data from CoinGecko (free tier, no API key required).

    CoinGecko /ohlc endpoint returns [timestamp_ms, open, high, low, close]
    arrays. We map 'hour' → 1 day, 'day' → 7 days, 'week' → 30 days.

    Args:
        symbol:   BTC | ETH | SOL
        interval: hour | day | week

    Returns:
        List of {timestamp, open, high, low, close, volume} dicts,
        or [] on failure.
    """
    cg_ids = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    coin_id = cg_ids.get(symbol.upper())
    if not coin_id:
        return []

    days_map = {"hour": 1, "day": 7, "week": 30}
    days = days_map.get(interval, 7)

    url = f"{COINGECKO_API}/coins/{coin_id}/ohlc?vs_currency=usd&days={days}"
    data = _get_json(url)
    if not isinstance(data, list):
        return []

    out = []
    for candle in data:
        if not isinstance(candle, list) or len(candle) < 5:
            continue
        try:
            out.append({
                "timestamp": candle[0],       # milliseconds unix
                "open":     float(candle[1]),
                "high":     float(candle[2]),
                "low":      float(candle[3]),
                "close":    float(candle[4]),
                "volume":    0.0,              # CoinGecko OHLC endpoint doesn't return volume
            })
        except (TypeError, ValueError):
            continue
    return out


# ── MacroMonitor wrapper ──────────────────────────────────────────────────────

def _load_macro_monitor():
    """Lazy-import to avoid circular deps at module load time."""
    try:
        from macro_monitor import MacroMonitor
        return MacroMonitor()
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def cached_macro_scan() -> dict:
    """Scan macro environment, cached for 60 s."""
    monitor = _load_macro_monitor()
    if not monitor:
        return {}
    try:
        return monitor.scan().__dict__
    except Exception:
        return {}


# ── MarketScanner wrapper ─────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def cached_market_scan() -> dict:
    """Scan Jupiter market, cached for 60 s."""
    try:
        from market_scanner import MarketScanner
        scanner = MarketScanner()
        top_traded_scan = scanner.scan_top_traded()
        cooking_scan    = scanner.scan_cooking()
        return {
            "top_traded": getattr(top_traded_scan, "tokens", []),
            "cooking":    getattr(cooking_scan,    "tokens", []),
        }
    except Exception:
        return {"top_traded": [], "cooking": []}


# ── Portfolio ─────────────────────────────────────────────────────────────────

# Loaded from the latest reconciled position_theses.json snapshot.
def load_holdings_amounts() -> dict[str, float]:
    try:
        data = json.loads(THESES.read_text())
        balances = data.get("wallet_snapshot", {}).get("balances", {})
        return {str(k): float(v) for k, v in balances.items() if float(v) > 0}
    except Exception:
        return {}

# CoinGecko ids for price lookup
CG_IDS = {
    "SOL":    "solana",
    "ETH":    "ethereum",
    "BTC":    "bitcoin",
    "JUP":    "jupiter-exchange-solana",   # best-effort Jupiter id
    "USDC":   "usd-coin",
    "cbBTC":  "coinbase-wrapped-btc",
}


@functools.lru_cache(maxsize=1)
def cached_portfolio() -> dict:
    """
    Returns portfolio summary:
    {
      holdings: [{symbol, amount, price_usd, value_usd, change_24h, pnl_usd}, ...],
      total_nav, total_cost, pnl_usd
    }
    """
    # Load cost basis from position_rules if available
    cost_basis = {}
    try:
        rules = json.loads(RULES.read_text())
        pos   = rules.get("positions", {})
        for k, v in pos.items():
            if isinstance(v, dict):
                cost_basis[k] = float(v.get("total_cost_usd", 0))
    except Exception:
        pass

    # Fetch prices from CoinGecko
    cg_ids_list = ",".join(CG_IDS.values())
    prices = cg_simple_price(ids=cg_ids_list)   # {id: {usd, usd_24h_change}}

    holdings = []
    total_nav = 0.0
    total_cost = 0.0

    for sym, amount in load_holdings_amounts().items():
        cg_id = CG_IDS.get(sym, "")
        price_info = prices.get(cg_id, {})
        price_usd  = price_info.get("usd", 0.0)
        change_24h = price_info.get("usd_24h_change", 0.0)
        value_usd  = amount * price_usd
        cost       = cost_basis.get(sym, value_usd * 0.9)   # fallback: assume 10% cost
        pnl        = value_usd - cost

        holdings.append({
            "symbol":      sym,
            "amount":      amount,
            "price_usd":  price_usd,
            "value_usd":  round(value_usd, 4),
            "change_24h": round(change_24h, 4),
            "pnl_usd":    round(pnl, 4),
        })
        total_nav  += value_usd
        total_cost += cost

    return {
        "holdings":   holdings,
        "total_nav":   round(total_nav, 4),
        "total_cost":  round(total_cost, 4),
        "pnl_usd":     round(total_nav - total_cost, 4),
    }


# ── Aggregated API responses ──────────────────────────────────────────────────

def _serialize_env_report(obj):
    """Recursively convert dataclasses/lists to JSON-serializable dicts."""
    if isinstance(obj, dict):
        return {k: _serialize_env_report(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_env_report(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {f: _serialize_env_report(getattr(obj, f)) for f in obj.__dataclass_fields__}
    return obj


def _fetch_coindesk_news(limit: int = 5) -> list[dict]:
    """Fetch latest news from CoinDesk RSS feed. Returns list of {headline, url, source}."""
    import xml.etree.ElementTree as ET
    try:
        req = urllib.request.Request(
            "https://feeds.feedburner.com/CoinDesk",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            return []
        items = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title and link:
                items.append({
                    "headline": title[:120],
                    "url": link,
                    "source": "CoinDesk",
                })
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


def _fetch_cpi_data() -> dict | None:
    """
    Fetch latest US CPI data from Bureau of Labor Statistics (BLS Public API).
    Returns {yoy_pct, prior_pct, month, year} or None on failure.
    """
    import json as json_lib
    try:
        req = urllib.request.Request(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            data=json_lib.dumps({
                "seriesid": ["CUUR0000SA0"],
                "startyear": "2023",
                "endyear": "2026",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json_lib.loads(resp.read())
        series = (data.get("Results") or {}).get("series", [])
        if not series:
            return None
        observations = sorted(
            series[0].get("data", []),
            key=lambda x: (x.get("year", "0"), x.get("period", "M00")),
            reverse=True,
        )
        if len(observations) < 2:
            return None
        latest = observations[0]
        prior  = observations[1]
        def pct(v): return round((float(v) - 100) * 100 / 100, 1)
        return {
            "yoy_pct":   round((float(latest["value"]) - float(prior["value"])) / float(prior["value"]) * 100, 1),
            "level":     round(float(latest["value"]), 2),
            "prior":     round(float(prior["value"]), 2),
            "month":     latest.get("period", "").replace("M", ""),
            "year":      latest.get("year", ""),
            "periodName": f"{latest.get('periodName', latest.get('period',''))} {latest.get('year','')}",
        }
    except Exception:
        return None


def _fetch_fear_greed_direct() -> dict | None:
    """Direct Fear & Greed fetch as fallback."""
    try:
        data = _get_json("https://api.alternative.me/fng/?limit=1")
        items = data.get("data", []) if isinstance(data, dict) else []
        if not items:
            return None
        latest = items[0]
        v = int(latest.get("value", 50))
        return {
            "value": v,
            "label": "Extreme Fear" if v <= 20 else "Fear" if v <= 40 else "Neutral" if v <= 60 else "Greed" if v <= 80 else "Extreme Greed",
            "timestamp": latest.get("timestamp", ""),
        }
    except Exception:
        return None


def get_news_response() -> dict:
    """Returns {news: [...]} from CoinDesk RSS."""
    return {"news": _fetch_coindesk_news(limit=5)}


def get_macro_response() -> dict:
    """
    Returns the full macro data dict for /api/macro, including
    parsed cp_btc multi-timeframe BTC data alongside the scan result.
    """
    scan  = _serialize_env_report(cached_macro_scan())
    cp    = _get_json(
        f"{COINPAPRIKA_API}/tickers/{COINPAPRIKA_IDS['BTC']}"
    ) or {}
    q     = (cp.get("quotes") or {}).get("USD", {})
    cp_btc = {
        "price":             q.get("price"),
        "change_15m_pct":   q.get("percent_change_15m"),
        "change_30m_pct":   q.get("percent_change_30m"),
        "change_1h_pct":    q.get("percent_change_1h"),
        "change_6h_pct":    q.get("percent_change_6h"),
        "change_12h_pct":   q.get("percent_change_12h"),
        "change_24h_pct":   q.get("percent_change_24h"),
        "change_7d_pct":    q.get("percent_change_7d"),
        "change_30d_pct":   q.get("percent_change_30d"),
        "ath_price":        q.get("ath_price"),
        "ath_date":         q.get("ath_date"),
        "from_ath_pct":    q.get("percent_from_price_ath"),
        "volume_24h":       q.get("volume_24h"),
    }
    scan["cp_btc"] = cp_btc
    # Inject direct F&G if macro scan missed it
    if not scan.get("fear_greed"):
        scan["fear_greed"] = _fetch_fear_greed_direct()
    # Inject CPI data
    cpi = _fetch_cpi_data()
    if cpi:
        scan["cpi"] = cpi
    return scan


def get_alerts_response() -> dict:
    """Returns {alerts: [...]} from the macro scan."""
    scan = cached_macro_scan()
    return {"alerts": scan.get("alerts") or []}


def get_portfolio_response() -> dict:
    return cached_portfolio()


def get_chart_response(symbol: str, interval: str = "240") -> dict:
    """
    Returns OHLCV candles for TradingView chart.

    Args:
        symbol:   BTC | ETH | SOL
        interval: 60 | 240 | 1440 | 10080  (minutes)
    """
    intr_map = {"60": "hour", "240": "hour", "1440": "day", "10080": "week"}
    candles = paprika_ohlcv(symbol.upper(), interval=intr_map.get(interval, "hour"))
    return {"symbol": symbol.upper(), "interval": interval, "candles": candles}


def get_market_response() -> dict:
    """
    Returns top-traded + cooking tokens enriched with alert flags.
    """
    scan  = cached_market_scan()
    top   = getattr(scan, "tokens", [])   # MarketScan dataclass
    cook_raw = getattr(scan, "cooking", []) if hasattr(scan, "cooking") else []
    cook  = cook_raw if isinstance(cook_raw, list) else []

    # Flag volume spikes (>50% of liquidity = anomalous)
    volume_spikes = []
    for t in top:
        if isinstance(t, dict):
            vol  = float(t.get("volume") or 0)
            liq  = float(t.get("liquidity") or 0)
            if liq > 0 and vol / liq > 0.5:
                volume_spikes.append({
                    "symbol":      t.get("symbol") or str(t.get("mint", ""))[:6],
                    "volume_ratio": round(vol / liq, 2),
                    "volume":      vol,
                    "liquidity":   liq,
                })

    return {
        "top_traded":    top[:20] if isinstance(top, list) else [],
        "cooking":      cook[:10] if isinstance(cook, list) else [],
        "volume_spikes": volume_spikes[:5],
    }


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint
    print("=== PORTFOLIO ===")
    pprint.pprint(get_portfolio_response())
    print("\n=== MACRO ===")
    pprint.pprint(get_macro_response())
    print("\n=== MARKET ===")
    pprint.pprint(get_market_response())
    print("\n=== ALERTS ===")
    pprint.pprint(get_alerts_response())
    print("\n=== OHLCV SOL ===")
    pprint.pprint(paprika_ohlcv("SOL")[:2])
