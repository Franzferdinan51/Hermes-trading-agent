"""
TradingView lightweight-charts integration for the Hermes Trading Dashboard.

Uses dash_tvlwc when available, falls back to a pure HTML/JS CDN implementation.
Fetches OHLCV data from CoinPaprika API and renders a candlestick + volume chart.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COINPAPRIKA_BASE = "https://api.coinpaprika.com/v1/ohlcv"

# Map user-facing symbols to CoinPaprika coin IDs
COIN_IDS: Dict[str, str] = {
    "BTC": "btc-bitcoin",
    "ETH": "eth-ethereum",
    "SOL": "sol-solana",
}

# Map interval strings to CoinPaprika interval names
INTERVAL_MAP: Dict[str, str] = {
    "1":   "minute",
    "5":   "minute",
    "15":  "minute",
    "60":  "hour",
    "240": "hour",
    "1D":  "day",
}

INTERVAL_MINUTES: Dict[str, int] = {
    "1":   1,
    "5":   5,
    "15":  15,
    "60":  60,
    "240": 240,
    "1D":  1440,
}

VALID_SYMBOLS    = list(COIN_IDS.keys())
VALID_INTERVALS = list(INTERVAL_MAP.keys())

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_ohlcv(
    symbol: str,
    interval: str = "60",
    hours: int = 168,
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV data from CoinPaprika for the given symbol and interval.

    Args:
        symbol:   Trading symbol (BTC, ETH, SOL)
        interval: Candle interval ('1', '5', '15', '60', '240', '1D')
        hours:    Number of past hours to fetch (default 168 = 7 days)

    Returns:
        List of OHLCV candles in lightweight-charts format:
        [{time: unix_ts, open, high, low, close, value: volume}, ...]
    """
    coin_id = COIN_IDS.get(symbol.upper())
    if not coin_id:
        raise ValueError("Unknown symbol: {!r}. Valid: {}".format(symbol, VALID_SYMBOLS))

    paprika_interval = INTERVAL_MAP.get(interval, "hour")
    interval_min = INTERVAL_MINUTES.get(interval, 60)

    now_ts    = int(time.time())
    start_ts  = now_ts - (hours * 3600)

    url    = "{}/{}/historical".format(COINPAPRIKA_BASE, coin_id)
    params = {"start": start_ts, "end": now_ts, "interval": paprika_interval}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("CoinPaprika request failed for %s/%s: %s", symbol, interval, exc)
        raise RuntimeError("Failed to fetch OHLCV data for {}: {}".format(symbol, exc)) from exc

    raw: List[Dict[str, Any]] = response.json()

    if not isinstance(raw, list):
        logger.warning("Unexpected CoinPaprika response type for %s: %s", symbol, type(raw))
        return []

    candles: List[Dict[str, Any]] = []
    for candle in raw:
        try:
            ts = int(candle.get("timestamp", 0)) // 1000
            candles.append({
                "time":  ts,
                "open":  float(candle["open"]),
                "high":  float(candle["high"]),
                "low":   float(candle["low"]),
                "close": float(candle["close"]),
                "value": float(candle.get("volume", 0)),
            })
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed candle for %s: %s — %s", symbol, candle, exc)
            continue

    if interval_min > 1:
        candles = _resample_candles(candles, interval_min)

    if candles:
        logger.info(
            "Fetched %d candles for %s (%s interval) from %s to %s",
            len(candles), symbol, interval,
            datetime.fromtimestamp(candles[0]["time"], tz=timezone.utc).isoformat(),
            datetime.fromtimestamp(candles[-1]["time"], tz=timezone.utc).isoformat(),
        )
    return candles


def _resample_candles(candles: List[Dict[str, Any]], interval_min: int) -> List[Dict[str, Any]]:
    """
    Group consecutive lower-timeframe candles into higher-timeframe buckets.
    interval_min must be > 1.
    """
    if not candles:
        return []

    bucket_seconds = interval_min * 60
    buckets: Dict[int, Dict[str, float]] = {}

    for c in candles:
        bucket = (c["time"] // bucket_seconds) * bucket_seconds
        if bucket not in buckets:
            buckets[bucket] = {
                "time":  bucket,
                "open":  c["open"],
                "high":  c["high"],
                "low":   c["low"],
                "close": c["close"],
                "value": c["value"],
            }
        else:
            b = buckets[bucket]
            b["high"]   = max(b["high"],  c["high"])
            b["low"]    = min(b["low"],   c["low"])
            b["close"]  = c["close"]
            b["value"] += c["value"]

    return sorted(buckets.values(), key=lambda x: x["time"])


def _format_interval_label(interval: str) -> str:
    labels = {"1": "1M", "5": "5M", "15": "15M", "60": "1H", "240": "4H", "1D": "1D"}
    return labels.get(interval, interval)


def _safe_json_dumps(obj: Any) -> str:
    """Serialize to JSON, replacing non-serialisable values with null."""
    return json.dumps(obj, default=lambda x: None)


def _coinpaprika_interval_for(interval: str) -> str:
    """Return CoinPaprika interval name for the given interval code."""
    return INTERVAL_MAP.get(interval, "hour")


# ---------------------------------------------------------------------------
# HTML/JS renderer (CDN fallback)
# ---------------------------------------------------------------------------

def _build_cdn_js_component(
    symbol: str = "SOL",
    interval: str = "60",
    height: int = 420,
) -> str:
    """
    Build a self-contained HTML string that renders a TradingView lightweight chart
    using the CDN-hosted library.  All OHLCV data is injected server-side (no
    external API calls from the browser except the optional live-reload fetch to
    our own /dashboard/ohlcv proxy).
    """
    try:
        candles = fetch_ohlcv(symbol, interval)
    except Exception as exc:
        logger.error("Pre-fetch failed for %s/%s, using empty chart: %s", symbol, interval, exc)
        candles = []

    candles_json = _safe_json_dumps(candles)

    # Build option tags for symbol selector
    symbol_options = "".join(
        '<option value="{}"{}>{}</option>'.format(s, ' selected' if s == symbol else '', s)
        for s in VALID_SYMBOLS
    )

    # Build interval button markup
    interval_buttons = ""
    for iv in VALID_INTERVALS:
        is_active = iv == interval
        bg     = "#21262d" if is_active else "#161b22"
        border = "#58a6ff" if is_active else "#30363d"
        color  = "#e6edf3" if is_active else "#8b949e"
        label  = _format_interval_label(iv)
        interval_buttons += (
            '<button class="tv-iframe-btn" data-interval="{}" '
            'style="background:{};border:1px solid {};color:{};border-radius:4px;'
            'padding:2px 8px;cursor:pointer;font-size:12px;transition:all .15s;">'
            '{}</button>'.format(iv, bg, border, color, label)
        )

    return """
<div id="tv-chart-root" style="width:100%;max-width:100%;">
  <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>

  <!-- Controls bar -->
  <div style="display:flex;align-items:center;gap:8px;padding:8px 4px 6px;
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;">
    <label style="color:#8b949e;white-space:nowrap;">Symbol:</label>
    <select id="tv-symbol-select" style="
        background:#161b22;border:1px solid #30363d;color:#e6edf3;
        border-radius:4px;padding:2px 6px;cursor:pointer;font-size:13px;">
      {symbol_options}
    </select>

    <label style="color:#8b949e;white-space:nowrap;margin-left:12px;">Interval:</label>
    <div style="display:flex;gap:4px;">
      {interval_buttons}
    </div>
  </div>

  <!-- Chart container -->
  <div id="tv_chart" style="height:{height}px;width:100%;border-radius:6px;
       overflow:hidden;border:1px solid #30363d;box-sizing:border-box;"></div>

  <!-- Current price badge -->
  <div id="tv-price-badge" style="
      position:relative;margin-top:4px;text-align:right;
      font-family:'SF Mono',Monaco,monospace;font-size:12px;color:#8b949e;"></div>
</div>

<script>
(function() {{
  'use strict';

  /* ─── Static data injected server-side ─────────────────────────────── */
  var _candlesData = {candles_json};

  /* ─── Helpers ─────────────────────────────────────────────────────── */
  function _formatPrice(v) {{
    if (v == null || isNaN(v)) return '—';
    return v.toLocaleString('en-US', {{
      minimumFractionDigits: 2,
      maximumFractionDigits: 8
    }});
  }}

  function _buildVolumeData(candles) {{
    return candles.map(function(c) {{
      return {{
        time:  c.time,
        value: c.value || 0,
        color: (c.close >= c.open)
          ? 'rgba(63,185,80,0.4)'
          : 'rgba(248,81,73,0.4)'
      }};
    }});
  }}

  /* ─── Chart builder ────────────────────────────────────────────────── */
  function _buildChart(container, candles) {{
    if (!window.LightweightCharts) {{
      container.innerHTML = '<p style="color:#f85149;padding:16px;">' +
        'Chart library failed to load. Check your internet connection.</p>';
      return null;
    }}

    container.innerHTML = '';

    var chart = window.LightweightCharts.createChart(container, {{
      layout: {{
        background: {{ type: 'solid', color: '#0d1117' }},
        textColor: '#e6edf3',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      }},
      grid: {{
        vertLines: {{ color: '#30363d', style: 1 }},
        horzLines: {{ color: '#30363d', style: 1 }}
      }},
      crosshair: {{
        mode: window.LightweightCharts.CrosshairMode.Normal,
        vertLine: {{ color: '#58a6ff', labelBackgroundColor: '#1f6feb' }},
        horzLine: {{ color: '#58a6ff', labelBackgroundColor: '#1f6feb' }}
      }},
      rightPriceScale: {{
        borderColor: '#30363d',
        scaleMargins: {{ top: 0.1, bottom: 0.25 }}
      }},
      width:  container.clientWidth,
      height: container.clientHeight || {height},
      timeScale: {{
        borderColor: '#30363d',
        timeVisible: true,
        secondsVisible: false
      }}
    }});

    /* Candlestick series */
    var candleSeries = chart.addCandlestickSeries({{
      upColor:         '#3fb950',
      downColor:       '#f85149',
      borderUpColor:   '#3fb950',
      borderDownColor: '#f85149',
      wickUpColor:     '#3fb950',
      wickDownColor:   '#f85149'
    }});
    candleSeries.setData(candles);

    /* Volume histogram */
    var volumeSeries = chart.addHistogramSeries({{
      color:       '#388bfd',
      priceFormat: {{ type: 'volume' }},
      priceScaleId: 'volume'
    }});
    volumeSeries.priceScale().applyOptions({{
      scaleMargins: {{ top: 0.8, bottom: 0 }}
    }});
    volumeSeries.setData(_buildVolumeData(candles));

    /* Last-close price line */
    if (candles.length > 0) {{
      var last = candles[candles.length - 1];
      candleSeries.createPriceLine({{
        price:           last.close,
        color:           '#58a6ff',
        lineWidth:       1,
        lineStyle:       0,
        axisLabelVisible: true,
        title:           'PRICE'
      }});
    }}

    chart.timeScale().fitContent();

    /* Responsive resize */
    var ro = new ResizeObserver(function(entries) {{
      for (var i = 0; i < entries.length; i++) {{
        chart.resize(entries[i].contentRect.width,
                     entries[i].contentRect.height || {height});
      }}
    }});
    ro.observe(container);

    return {{ chart: chart, candleSeries: candleSeries, volumeSeries: volumeSeries }};
  }}

  /* ─── Price badge update ──────────────────────────────────────────── */
  function _updatePriceBadge(candles) {{
    var el = document.getElementById('tv-price-badge');
    if (!el || !candles || candles.length === 0) return;
    var last = candles[candles.length - 1];
    var prev = candles.length >= 2 ? candles[candles.length - 2] : last;
    var pct  = ((last.close - prev.close) / prev.close * 100).toFixed(2);
    var sign = pct >= 0 ? '+' : '';
    el.innerHTML =
      '<span style="color:#e6edf3;font-weight:600;">' + _formatPrice(last.close) + '</span>'
      + ' <span style="color:' + (pct >= 0 ? '#3fb950' : '#f85149') + ';">' + sign + pct + '%</span>'
      + ' <span style="color:#8b949e;">24h</span>';
  }}

  /* ─── Button active-state helper ─────────────────────────────────── */
  function _applyButtonStyles(activeInterval) {{
    var btns = document.querySelectorAll('.tv-iframe-btn');
    for (var i = 0; i < btns.length; i++) {{
      var isActive = btns[i].getAttribute('data-interval') === activeInterval;
      btns[i].style.background  = isActive ? '#21262d' : '#161b22';
      btns[i].style.borderColor = isActive ? '#58a6ff' : '#30363d';
      btns[i].style.color       = isActive ? '#e6edf3' : '#8b949e';
    }}
  }}

  /* ─── Live data reload via our Flask proxy ───────────────────────── */
  var _chartHandle = null;

  function _reloadChart(symbol, interval) {{
    var container = document.getElementById('tv_chart');
    if (!container) return;

    if (_chartHandle) {{
      _chartHandle.chart.remove();
      _chartHandle = null;
    }}

    _chartHandle = _buildChart(container, _candlesData);
    _updatePriceBadge(_candlesData);
    _applyButtonStyles(interval);

    /* Fetch from our own /dashboard/ohlcv proxy (keeps API key server-side) */
    var intMap = {{'1':'minute','5':'minute','15':'minute','60':'hour','240':'hour','1D':'day'}};
    var intMin = {{'1':1,'5':5,'15':15,'60':60,'240':240,'1D':1440}};
    var nowTs   = Math.floor(Date.now() / 1000);
    var startTs = nowTs - (168 * 3600);
    var paprikaInt = intMap[interval] || 'hour';
    var coinId = {{'BTC':'btc-bitcoin','ETH':'eth-ethereum','SOL':'sol-solana'}}[symbol] || 'sol-solana';
    var url = '/dashboard/ohlcv?symbol=' + symbol + '&interval=' + interval
            + '&_ts=' + nowTs;

    fetch(url)
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        if (!Array.isArray(data) || data.length === 0) return;
        _candlesData = data;
        if (_chartHandle) {{
          _chartHandle.candleSeries.setData(data);
          _chartHandle.volumeSeries.setData(_buildVolumeData(data));
          _chartHandle.chart.timeScale().fitContent();
          _updatePriceBadge(data);
        }}
      }})
      .catch(function(err) {{
        if (err.name !== 'AbortError') console.error('OHLCV reload failed:', err);
      }});
  }}

  /* ─── Symbol dropdown ─────────────────────────────────────────────── */
  var symbolSel = document.getElementById('tv-symbol-select');
  if (symbolSel) {{
    symbolSel.addEventListener('change', function(e) {{
      _reloadChart(e.target.value, _currentInterval);
    }});
  }}

  /* ─── Interval buttons ───────────────────────────────────────────── */
  var _currentInterval = '{interval}';
  var btns = document.querySelectorAll('.tv-iframe-btn');
  for (var i = 0; i < btns.length; i++) {{
    btns[i].addEventListener('click', function() {{
      _currentInterval = this.getAttribute('data-interval');
      var sym = (document.getElementById('tv-symbol-select') || {{}}).value || '{symbol}';
      _reloadChart(sym, _currentInterval);
    }});
  }}

  /* ─── Initial render ──────────────────────────────────────────────── */
  var container = document.getElementById('tv_chart');
  if (container) {{
    _chartHandle = _buildChart(container, _candlesData);
    _updatePriceBadge(_candlesData);
    _applyButtonStyles(_currentInterval);
  }}
}})();
</script>
""".format(
    candles_json=candles_json,
    symbol_options=symbol_options,
    interval_buttons=interval_buttons,
    height=height,
    symbol=symbol,
    interval=interval,
)


# ---------------------------------------------------------------------------
# dash_tvlwc detection
# ---------------------------------------------------------------------------

def _try_import_dash_tvlwc() -> bool:
    try:
        import dash_tvlwc  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Flask OHLCV proxy (shared by both paths)
# ---------------------------------------------------------------------------

def _register_ohlcv_proxy(flask_app) -> None:
    """
    Register a ``/dashboard/ohlcv`` route on the given Flask app that proxies
    CoinPaprika OHLCV requests server-side (avoids CORS, hides keys).
    """
    from flask import Blueprint, request, jsonify

    bp = Blueprint("dashboard_ohlcv", __name__, url_prefix="/dashboard")

    @bp.route("/ohlcv", methods=["GET"])
    def ohlcv_proxy():
        symbol   = request.args.get("symbol", "SOL").upper()
        interval = request.args.get("interval", "60")

        if symbol not in VALID_SYMBOLS:
            return jsonify({"error": "Invalid symbol. Valid: {}".format(VALID_SYMBOLS)}), 400
        if interval not in VALID_INTERVALS:
            return jsonify({"error": "Invalid interval. Valid: {}".format(VALID_INTERVALS)}), 400

        try:
            data = fetch_ohlcv(symbol, interval)
        except Exception as exc:
            logger.error("OHLCV proxy error: %s", exc)
            return jsonify({"error": str(exc)}), 502

        return jsonify(data)

    flask_app.register_blueprint(bp)
    logger.info("Registered /dashboard/ohlcv proxy blueprint on Flask app")


# ---------------------------------------------------------------------------
# dash_tvlwc component path
# ---------------------------------------------------------------------------

def _create_tvlwc_component(dash_app) -> Any:
    """
    Dash component using the ``dash_tvlwc`` package (pip install dash_tvlwc).
    The chart state (symbol / interval) is managed via Dash callbacks.
    """
    import dash
    from dash import html, dcc, Input, Output, callback

    try:
        import dash_tvlwc
    except ImportError:
        logger.warning("dash_tvlwc not available at runtime — falling back to CDN")
        return _create_cdn_fallback_component(dash_app)

    _register_ohlcv_proxy(dash_app.server)

    cid = "tv-chart-tvlwc"

    layout = html.Div(
        [
            # Controls bar
            html.Div(
                [
                    html.Label("Symbol:", style={"color": "#8b949e", "fontSize": "13px"}),
                    dcc.Dropdown(
                        id="{}-sym".format(cid),
                        options=[{"label": s, "value": s} for s in VALID_SYMBOLS],
                        value="SOL",
                        clearable=False,
                        style={
                            "width": "120px",
                            "backgroundColor": "#161b22",
                            "border": "1px solid #30363d",
                            "color": "#e6edf3",
                        },
                    ),
                    html.Label("Interval:", style={
                        "color": "#8b949e",
                        "fontSize": "13px",
                        "marginLeft": "16px",
                    }),
                    dcc.Dropdown(
                        id="{}-int".format(cid),
                        options=[
                            {"label": _format_interval_label(iv), "value": iv}
                            for iv in VALID_INTERVALS
                        ],
                        value="60",
                        clearable=False,
                        style={
                            "width": "100px",
                            "backgroundColor": "#161b22",
                            "border": "1px solid #30363d",
                            "color": "#e6edf3",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "8px",
                    "padding": "8px 4px",
                    "marginBottom": "4px",
                },
            ),
            # Chart area
            html.Div(
                dash_tvlwc.TVChart(
                    id=cid,
                    symbol="SOL",
                    interval="60",
                ),
                id="{}-wrap".format(cid),
                style={
                    "border-radius": "6px",
                    "overflow": "hidden",
                    "border": "1px solid #30363d",
                },
            ),
            # Price badge
            html.Div(
                id="{}-price".format(cid),
                style={
                    "textAlign": "right",
                    "fontFamily": "'SF Mono',Monaco,monospace",
                    "fontSize": "12px",
                    "color": "#8b949e",
                    "marginTop": "4px",
                },
            ),
        ],
        style={"fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"},
    )

    @callback(
        Output(cid, "symbol"),
        Output(cid, "interval"),
        Output("{}-price".format(cid), "children"),
        Input("{}-sym".format(cid), "value"),
        Input("{}-int".format(cid), "value"),
    )
    def _update_tvlwc(symbol, interval):
        try:
            candles = fetch_ohlcv(symbol, interval)
        except Exception as exc:
            logger.error("OHLCV fetch error in TVChart callback: %s", exc)
            candles = []

        if candles:
            last = candles[-1]
            prev = candles[-2] if len(candles) >= 2 else last
            pct  = (last["close"] - prev["close"]) / prev["close"] * 100
            sign = "+" if pct >= 0 else ""
            price_html = (
                '<span style="color:#e6edf3;font-weight:600;">'
                '{:,.2f}</span> '
                '<span style="color:{};">{}</span>'
            ).format(
                last["close"],
                "#3fb950" if pct >= 0 else "#f85149",
                "{}{:.2f}%".format(sign, pct),
            )
        else:
            price_html = '<span style="color:#8b949e;">No data</span>'

        return symbol, interval, price_html

    return lambda **kw: layout


# ---------------------------------------------------------------------------
# CDN fallback component path
# ---------------------------------------------------------------------------

def _create_cdn_fallback_component(dash_app) -> Any:
    """
    Dash component that embeds the pure HTML/JS CDN TradingView chart.
    All chart interaction (symbol / interval changes) is handled client-side
    in JavaScript; no extra Dash callback round-trips after initial render.
    """
    from dash import html, dcc

    cid = "tv-chart-cdn"

    # Register the Flask proxy so client-side JS can call it
    _register_ohlcv_proxy(dash_app.server)

    def _component(symbol: str = "SOL", interval: str = "60", height: int = 420, **kwargs) -> html.Div:
        return html.Div(
            [
                # Hidden input to satisfy Dash Input requirement (no-op trigger)
                dcc.Input(id="{}-dummy".format(cid), value="init", type="hidden"),
                html.Div(
                    _build_cdn_js_component(symbol=symbol, interval=interval, height=height),
                ),
            ],
            style={
                "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
            },
        )

    return _component


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_chart_component(dash_app) -> Any:
    """
    Create and register the TradingView chart Dash component with the app.

    Strategy:
      1. If ``dash_tvlwc`` is importable → use the package (better Dash integration).
      2. Otherwise → use the pure HTML/JS CDN implementation.

    Also registers ``/dashboard/ohlcv`` on ``dash_app.server`` as a CoinPaprika
    proxy endpoint (used by the CDN component's client-side JS reload).

    Args:
        dash_app:  The ``dash.Dash`` application instance.

    Returns:
        A callable (component factory) accepting ``symbol``, ``interval``, and
        ``height`` kwargs and returning a Dash ``html.Div``.
    """
    if _try_import_dash_tvlwc():
        logger.info("dash_tvlwc detected — using package-based chart component")
        return _create_tvlwc_component(dash_app)
    else:
        logger.info("dash_tvlwc not found — using CDN fallback chart component")
        return _create_cdn_fallback_component(dash_app)
