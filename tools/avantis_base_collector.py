#!/usr/bin/env python3
"""
Avantis Base perpetuals read-only collector.
Queries market data, funding rates, and open interest from Avantis on Base.

Never signs, broadcasts, or executes. Returns structured JSON.
"""
import sys, json, urllib.request

AVANTIS_API = "https://api.avantisfi.com"
AVANTIS_CORE = "https://core.avantisfi.com"
AVANTIS_DATA = "https://data.avantisfi.com"
AVANTIS_GRAPHQL = "https://api.thegraph.com/subgraphs/name/avantisfi/base-v1"

GRAPHQL_HEADERS = {"Content-Type": "application/json", "User-Agent": "Hermes/1.0"}

def fetch_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Hermes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def gql_query(url: str, query: str, variables: dict = None, timeout: int = 15) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=GRAPHQL_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def get_markets_graph(limit: int = 20):
    query = """
    {
      markets(first: %d) {
        id
        asset
        isLong
        indexToken { id symbol }
        currentFundingRate
        openInterest
        totalVolume
        markPrice
        indexPrice
        fundingRate
      }
    }
    """ % limit
    return gql_query(AVANTIS_GRAPHQL, query)

def get_markets_api():
    """Try Avantis REST API for markets."""
    endpoints = [
        f"{AVANTIS_API}/v1/markets",
        f"{AVANTIS_CORE}/v1/markets",
        f"{AVANTIS_DATA}/v1/markets",
    ]
    for url in endpoints:
        r = fetch_json(url)
        if "error" not in r:
            return r
    return {"error": "all Avantis REST endpoints failed"}

def get_funding_rates():
    """Get current funding rates across all markets."""
    endpoints = [
        f"{AVANTIS_API}/v1/funding-rates",
        f"{AVANTIS_CORE}/v1/funding-rates",
    ]
    for url in endpoints:
        r = fetch_json(url)
        if "error" not in r:
            return r
    return {"error": "all funding rate endpoints failed"}

def reconcile() -> dict:
    result = {
        "platform": "avantis_base",
        "chain": "base",
        "chain_id": 8453,
        "status": "read_only_collected",
        "markets": None,
        "funding_rates": None,
        "open_interest": None,
        "errors": []
    }

    # Try GraphQL first
    markets = get_markets_graph(20)
    if "errors" in markets:
        result["errors"].append(f"markets_graph: {markets['errors']}")
    elif "data" in markets:
        result["markets"] = markets["data"]["markets"]
    else:
        # Fall back to REST
        rest = get_markets_api()
        if "error" in rest:
            result["errors"].append(f"markets: {rest['error']}")
        else:
            result["markets"] = rest

    fr = get_funding_rates()
    if "error" in fr:
        result["errors"].append(f"funding_rates: {fr['error']}")
    else:
        result["funding_rates"] = fr

    return result

if __name__ == "__main__":
    out = reconcile()
    print(json.dumps(out, indent=2, default=str))
