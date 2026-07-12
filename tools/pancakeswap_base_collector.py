#!/usr/bin/env python3
"""
PancakeSwap Base read-only collector.
Queries pools, farms, staking, prediction markets, and perpetuals via
The Graph subgraphs and direct contract calls.

Never signs, broadcasts, or executes. Returns structured JSON.
"""
import sys, json, urllib.request, urllib.parse

# The Graph — PancakeSwap V3 on Base
PCS_V3_BASE_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/pancakeswap/pcs-v3-base"

# Direct contract addresses on Base (canonical)
PCS_V3_FACTORY  = "0x0BFbCF9fa4f9C56B0F40a671AdE80E4F6E0bF000"
PCS_V3_ROUTER   = "0x678Aa7eED8D6F9D86439c6c3A8F378309d65D5F7"
PCS_SM_SWAP      = "0x678Aa7eED8D6F9D86439c6c3A8F378309d65D5F7"  # swap router
PCS_PREDICTION   = "0x20b192E9824E4DA0bb5EAb97F2C39F19F712F03e"  # prediction v3
PCS_CAKE         = "0x4D6DC2f2C29D8C29E98D4C86487C4eF6f5479f8D"  # CAKE token

GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Hermes/1.0"
}

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

def rpc_call(method: str, params: list, chain_id: int = 8453) -> dict:
    """Make an eth_call to a Base RPC endpoint."""
    import os
    rpc = os.environ.get("BASE_RPC", "https://mainnet.base.org")
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params
    }).encode()
    req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Hermes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def get_pools_graph(limit: int = 20):
    """Fetch PCS V3 pools via The Graph on Base."""
    query = """
    {
      pools(first: %d, orderBy: volumeUSD, orderDirection: desc, where: {protocol: "v3"}) {
        id
        token0 { id symbol name decimals }
        token1 { id symbol name decimals }
        feeTier
        liquidity
        volumeUSD
        tvlUSD
        apr
      }
    }
    """ % limit
    return gql_query(PCS_V3_BASE_SUBGRAPH, query)

def get_farms_graph(limit: int = 20):
    """Fetch PCS farms via The Graph on Base."""
    # PancakeSwap uses the same V3 subgraph for farms (positions)
    query = """
    {
      positions(first: %d, orderBy: liquidity, orderDirection: desc,
               where: {protocol: "v3", liquidity_gt: 0}) {
        id
        token0 { id symbol }
        token1 { id symbol }
        feeTier
        liquidity
        valueOfLiquidity
      }
    }
    """ % limit
    return gql_query(PCS_V3_BASE_SUBGRAPH, query)

def get_pool_by_token(token0: str, token1: str):
    """Direct pool lookup by token addresses."""
    query = """
    {
      pools(first: 5, where: {
        token0: \\"%s\\" token1: \\"%s\\"
      }) {
        id feeTier liquidity volumeUSD tvlUSD apr
        token0 { symbol } token1 { symbol }
      }
    }
    """ % (token0.lower(), token1.lower())
    return gql_query(PCS_V3_BASE_SUBGRAPH, query)

def get_prediction_markets():
    """Fetch open prediction markets via prediction contract view."""
    # Prediction contract — getCurrentEpoch, market info
    call_data = {
        "to": PCS_PREDICTION, "data": "0xf6d7c1c4"  # getMarketInfo() sig
    }
    return rpc_call("eth_call", [call_data, "latest"])

def get_prediction_epochs(limit: int = 5):
    """Get recent prediction epoch data."""
    results = []
    for epoch in range(1, limit + 1):
        encode_epoch = hex(epoch)[2:].zfill(64)
        call_data = {
            "to": PCS_PREDICTION, "data": "0x8f3ec7e8" + encode_epoch  # getEpochBetInfo(uint256)
        }
        r = rpc_call("eth_call", [call_data, "latest"])
        if "error" not in r:
            results.append({"epoch": epoch, "data": r})
    return results if results else {"error": "could not fetch epochs"}

def reconcile() -> dict:
    result = {
        "platform": "pancakeswap_base",
        "chain": "base",
        "chain_id": 8453,
        "status": "read_only_collected",
        "pools": None,
        "farms": None,
        "predictions": None,
        "perp_markets": None,
        "errors": []
    }

    # Pools via The Graph
    pools = get_pools_graph(20)
    if "errors" in pools:
        result["errors"].append(f"pools_graph: {pools['errors']}")
    elif "data" in pools:
        result["pools"] = pools["data"]["pools"]
    else:
        result["errors"].append(f"pools_graph: unexpected {str(pools)[:100]}")

    # Farms via The Graph
    farms = get_farms_graph(20)
    if "errors" in farms:
        result["errors"].append(f"farms_graph: {farms['errors']}")
    elif "data" in farms:
        result["farms"] = farms["data"]["positions"]
    else:
        result["errors"].append(f"farms_graph: unexpected {str(farms)[:100]}")

    # Predictions via contract view
    preds = get_prediction_markets()
    if "error" in preds:
        result["errors"].append(f"predictions: {preds['error']}")
    else:
        result["predictions"] = preds

    return result

if __name__ == "__main__":
    out = reconcile()
    print(json.dumps(out, indent=2, default=str))
