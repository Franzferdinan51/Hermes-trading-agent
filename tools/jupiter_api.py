#!/usr/bin/env python3
"""Jupiter API helper. Reads the API key from macOS Keychain at runtime only."""
from __future__ import annotations
import json, os, subprocess, urllib.parse, urllib.request

SERVICE = "jupiter-api-key"
BASE = "https://api.jup.ag"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15"
)


def api_key() -> str:
    env = os.environ.get("JUPITER_API_KEY")
    if env:
        return env
    p = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", SERVICE, "-w"],
        capture_output=True, text=True, check=True,
    )
    return p.stdout.strip()


def _request(path: str):
    url = BASE + path
    headers = {
        "x-api-key": api_key(),
        "Accept": "application/json",
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener()
    opener.addheaders = list(headers.items())
    with opener.open(req, timeout=25) as r:
        raw = r.read()
        try:
            return r.status, raw.decode("utf-8")
        except UnicodeDecodeError:
            import gzip
            return r.status, gzip.decompress(raw).decode("utf-8")


def get(path: str, params: dict | None = None):
    if params:
        path += "?" + urllib.parse.urlencode(params)
    status, body = _request(path)
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="/prediction/v1/events")
    args = ap.parse_args()
    params = {"filter": "live"} if args.path.endswith("/events") else None
    status, data = get(args.path, params)
    if isinstance(data, dict):
        summary = {"ok": True, "status": status, "path": args.path, "top_level_keys": list(data.keys()), "count": len(data.get("data", [])) if isinstance(data.get("data"), list) else None}
    elif isinstance(data, list):
        summary = {"ok": True, "status": status, "path": args.path, "count": len(data)}
    else:
        summary = {"ok": False, "status": status, "path": args.path, "preview": str(data)[:400]}
    print(json.dumps(summary, indent=2))