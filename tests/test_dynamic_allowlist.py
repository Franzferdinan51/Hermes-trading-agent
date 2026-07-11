#!/usr/bin/env python3
"""Tests for the dynamic per-mint allowlist."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_allowlist as dyn  # noqa: E402


def setup_function(_func):
    dyn.STATE_DIR = Path(tempfile.mkdtemp(prefix="dyn-allowlist-"))
    dyn.STATE_FILE = dyn.STATE_DIR / "active_allowlist.json"
    dyn.HALT_FLAG_FILE = dyn.STATE_DIR / "DYNAMIC_ALLOWLIST_HALT"


def make_entry(mint: str = "TestMint1111111111111111111111111111111111", ttl: int = 600, intent: str = "speculation_buy", notional: float = 1.0):
    return dyn.build_supervisor_entry(
        mint=mint,
        thesis_id="t-test-1",
        max_notional_usd=notional,
        intent=intent,
        extensions_report={"transfer_hook": False, "permanent_delegate": False, "transfer_fee_bps": 0},
        liquidity_evidence={"usd_depth": 50000},
        rationale="test",
        ttl_seconds=ttl,
    )


def test_round_trip() -> None:
    assert dyn.read_entries() == {}
    entry = make_entry()
    dyn.write_entry(entry)
    assert "TestMint1111111111111111111111111111111111" in dyn.read_entries()
    assert dyn.entry_for("TestMint1111111111111111111111111111111111") is not None
    consumed = dyn.consume_entry("TestMint1111111111111111111111111111111111")
    assert consumed is not None
    assert dyn.read_entries() == {}


def test_expiry_purges() -> None:
    entry = make_entry(ttl=1)
    dyn.write_entry(entry)
    import time
    time.sleep(2)
    assert dyn.entry_for("TestMint1111111111111111111111111111111111") is None
    purged = dyn.purge_expired()
    assert "TestMint1111111111111111111111111111111111" in purged


def test_halt_blocks_writes_but_keeps_existing() -> None:
    dyn.write_entry(make_entry())
    dyn.halt("test")
    import pytest
    with pytest.raises(PermissionError):
        dyn.write_entry(make_entry(mint="OtherMint11111111111111111111111111111111"))
    assert dyn.entry_for("TestMint1111111111111111111111111111111111") is not None
    dyn.resume()


def test_invalid_intent_rejected() -> None:
    import pytest
    with pytest.raises(ValueError):
        dyn.write_entry(make_entry(intent="drain"))


def test_required_fields_enforced() -> None:
    import pytest
    with pytest.raises(ValueError):
        dyn.write_entry({"mint": "x", "thesis_id": "t"})


def test_ttl_cap_enforced() -> None:
    import pytest
    with pytest.raises(ValueError):
        dyn.write_entry(make_entry(ttl=dyn.MAX_TTL_SECONDS + 1))
    with pytest.raises(ValueError):
        dyn.write_entry(make_entry(ttl=0))


def test_revocation_writes_history() -> None:
    dyn.write_entry(make_entry())
    dyn.revoke_entry("TestMint1111111111111111111111111111111111", reason="rug detected")
    assert dyn.read_entries() == {}
    history = dyn.STATE_DIR / "active_allowlist_history.json"
    assert history.exists()
    entries = list(__import__("json").loads(history.read_text()).values())
    assert entries[0]["mint"] == "TestMint1111111111111111111111111111111111"
    assert entries[0]["revoked_reason"] == "rug detected"