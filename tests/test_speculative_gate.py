"""Negative tests for the speculative-direction gate.

These tests require a live Solana RPC. They skip automatically when
the configured ``WALLET`` is a placeholder rather than a real address.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "tools" / "privy_jupiter_executor.py"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ANSEM = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"


def run(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(EXECUTOR), *args],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


# Replace with your real wallet for live testing. The placeholder skips
# these tests since they require a live Solana RPC.
WALLET = "<YOUR_PRIVY_SOLANA_WALLET>"  # noqa: F811


def test_buy_attempt_is_rejected() -> None:
    if "<" in WALLET:
        import pytest
        pytest.skip("WALLET is a placeholder; set a real address to run live tests")
    code, _out, err = run([
        "--wallet", WALLET, "--thesis-id", "negtest-buy",
        "--input-mint", USDC, "--output-mint", ANSEM,
        "--amount", "100000", "--notional-usd", "0.10",
        "--wallet-value-usd", "62.88", "--max-loss-usd", "0.05",
        "--slippage-bps", "100",
    ])
    assert code != 0, "expected rejection of speculative buy"
    assert "exit only" in err, f"unexpected stderr: {err}"


def test_exit_attempt_proceeds() -> None:
    if "<" in WALLET:
        import pytest
        pytest.skip("WALLET is a placeholder; set a real address to run live tests")
    code, out, err = run([
        "--wallet", WALLET, "--thesis-id", "negtest-exit",
        "--input-mint", ANSEM, "--output-mint", USDC,
        "--amount", "6449815", "--notional-usd", "0.05",
        "--wallet-value-usd", "62.88", "--max-loss-usd", "0.05",
        "--slippage-bps", "100",
    ])
    if code != 0 and ("too large" in err or "simulateTransaction" in err):
        import pytest
        pytest.skip(f"Jupiter returned an oversized route this run: {err[-200:]}")
    assert code == 0, f"exit attempt should run dry-run; got {code}; stderr={err[-200:] if err else ''}"
    assert '"mode": "dry_run"' in out, f"expected dry-run output; got: {out[:300]}"