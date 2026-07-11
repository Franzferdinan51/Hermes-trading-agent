#!/usr/bin/env python3
"""
app.py — Hermes Trading Dashboard Flask server.

Routes:
  GET  /              — dashboard HTML
  GET  /api/portfolio — portfolio summary
  GET  /api/macro     — full macro intelligence scan
  GET  /api/market    — Jupiter top-traded + cooking tokens
  GET  /api/chart/<s> — OHLCV data for TradingView chart
  GET  /api/alerts    — active alerts
  GET  /health        — liveness probe
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Add parent (crypto-trading-setup/) to path so data_fetcher imports tools ──
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, Response
from flask_cors import CORS

from dashboard.data_fetcher import (
    get_alerts_response,
    get_chart_response,
    get_macro_response,
    get_market_response,
    get_news_response,
    get_portfolio_response,
)

REFRESH_SECS = int(os.getenv("DASHBOARD_REFRESH_SECS", "60"))

app = Flask(__name__,
            template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))
CORS(app)                                   # allow cross-origin for local dev


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/portfolio")
def api_portfolio():
    resp = jsonify(get_portfolio_response())
    resp.headers["X-Refresh-After"] = f"{REFRESH_SECS} seconds"
    return resp


@app.route("/api/macro")
def api_macro():
    resp = jsonify(get_macro_response())
    resp.headers["X-Refresh-After"] = f"{REFRESH_SECS} seconds"
    return resp


@app.route("/api/market")
def api_market():
    resp = jsonify(get_market_response())
    resp.headers["X-Refresh-After"] = f"{REFRESH_SECS} seconds"
    return resp


@app.route("/api/chart/<symbol>")
def api_chart(symbol: str):
    from flask import request
    interval = request.args.get("interval", "240")
    return jsonify(get_chart_response(symbol.upper(), interval))


@app.route("/api/news")
def api_news():
    resp = jsonify(get_news_response())
    resp.headers["X-Refresh-After"] = f"{REFRESH_SECS} seconds"
    return resp


@app.route("/api/alerts")
def api_alerts():
    resp = jsonify(get_alerts_response())
    resp.headers["X-Refresh-After"] = f"{REFRESH_SECS} seconds"
    return resp


@app.route("/health")
def health():
    return Response("OK", mimetype="text/plain")


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return {"error": "Not found"}, 404


@app.errorhandler(500)
def server_error(e):
    return {"error": "Internal server error"}, 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8050")),
        debug=os.getenv("FLASK_ENV") == "development",
    )
