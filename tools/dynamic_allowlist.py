#!/usr/bin/env python3
"""Dynamic per-mint allowlist managed by the autonomous supervisor.

State lives in ``state/active_allowlist.json`` and is read by the executor
at execution time. Only the supervisor prompt flow is allowed to mutate
the file (see ``write_entry`` / ``consume_entry``). Hard-coded safety rules
(approved programs, fee-payer check, Jupiter-router requirement) remain
in :mod:`privy_jupiter_executor` and are not relaxed by anything here.

Each entry is single-use: ``consume_entry`` deletes it after the trade
records finality, so a mint is never silently re-tradeable.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "active_allowlist.json"

DEFAULT_TTL_SECONDS = 6 * 60 * 60
MAX_TTL_SECONDS = 24 * 60 * 60
HALT_FLAG_FILE = STATE_DIR / "DYNAMIC_ALLOWLIST_HALT"

REQUIRED_FIELDS = (
    "mint",
    "thesis_id",
    "max_notional_usd",
    "expires_at",
    "created_at",
    "intent",
    "extensions_report",
    "liquidity_evidence",
    "created_by",
    "rationale",
)

FORBIDDEN_INTENTS = {"drain", "withdraw", "transfer", "treasury", "leverage"}
ALLOWED_INTENTS = {"core", "speculation_exit", "speculation_buy"}


def _now() -> float:
    return time.time()


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def read_entries(state_dir: Path | None = None) -> dict[str, dict]:
    """Return the current allowlist mapping mint -> entry.

    Tests can pass an isolated ``state_dir`` to keep the production
    state file untouched.
    """
    target_dir = state_dir or STATE_DIR
    target_file = target_dir / STATE_FILE.name
    target_dir.mkdir(parents=True, exist_ok=True)
    if not target_file.exists():
        return {}
    try:
        data = json.loads(target_file.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def is_halted(state_dir: Path | None = None) -> bool:
    target_dir = state_dir or STATE_DIR
    return (target_dir / HALT_FLAG_FILE.name).exists()


def halt(reason: str, state_dir: Path | None = None) -> None:
    target_dir = state_dir or STATE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / HALT_FLAG_FILE.name).write_text(json.dumps({"reason": reason, "ts": _now()}))


def resume(state_dir: Path | None = None) -> None:
    target_dir = state_dir or STATE_DIR
    try:
        (target_dir / HALT_FLAG_FILE.name).unlink()
    except FileNotFoundError:
        pass


def _validate_entry(entry: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in entry]
    if missing:
        raise ValueError(f"allowlist entry missing required fields: {missing}")
    intent = entry["intent"]
    if intent in FORBIDDEN_INTENTS:
        raise ValueError(f"intent {intent!r} is forbidden")
    if intent not in ALLOWED_INTENTS:
        raise ValueError(f"intent {intent!r} not in {ALLOWED_INTENTS}")
    if not isinstance(entry["max_notional_usd"], (int, float)) or entry["max_notional_usd"] <= 0:
        raise ValueError("max_notional_usd must be a positive number")
    ttl = entry["expires_at"] - entry["created_at"]
    if ttl <= 0 or ttl > MAX_TTL_SECONDS:
        raise ValueError(f"entry TTL must be in (0, {MAX_TTL_SECONDS}] seconds")


def write_entry(entry: dict, state_dir: Path | None = None) -> None:
    """Atomically replace the allowlist with the supplied entry merged in.

    Only the supervisor prompt flow should call this. ``mint`` is the key.
    Raises if dynamic additions are halted, the entry is invalid, or
    remaining TTL would exceed the cap.
    """
    target_dir = state_dir or STATE_DIR
    if is_halted(state_dir=target_dir):
        raise PermissionError("dynamic allowlist is halted; resume() to re-enable")
    _validate_entry(entry)
    current = read_entries(state_dir=target_dir)
    current[entry["mint"]] = entry
    _atomic_write(current, state_dir=target_dir)


def consume_entry(mint: str, state_dir: Path | None = None) -> dict | None:
    """Remove and return the entry after a successful trade records finality."""
    target_dir = state_dir or STATE_DIR
    current = read_entries(state_dir=target_dir)
    entry = current.pop(mint, None)
    _atomic_write(current, state_dir=target_dir)
    return entry


def revoke_entry(mint: str, reason: str, state_dir: Path | None = None) -> None:
    target_dir = state_dir or STATE_DIR
    current = read_entries(state_dir=target_dir)
    entry = current.pop(mint, None)
    if entry is None:
        return
    entry["revoked_at"] = _now()
    entry["revoked_reason"] = reason
    history_file = target_dir / "active_allowlist_history.json"
    history_entries = []
    if history_file.exists():
        try:
            history_entries = json.loads(history_file.read_text())
        except json.JSONDecodeError:
            history_entries = []
    history_entries.append(entry)
    _atomic_write(current, state_dir=target_dir)
    _atomic_write_history(history_entries, state_dir=target_dir)


def purge_expired(state_dir: Path | None = None) -> list[str]:
    target_dir = state_dir or STATE_DIR
    now = _now()
    current = read_entries(state_dir=target_dir)
    expired = [m for m, e in current.items() if e["expires_at"] <= now]
    for m in expired:
        current.pop(m, None)
    if expired:
        _atomic_write(current, state_dir=target_dir)
    return expired


def entry_for(mint: str, state_dir: Path | None = None) -> dict | None:
    target_dir = state_dir or STATE_DIR
    entry = read_entries(state_dir=target_dir).get(mint)
    if entry is None:
        return None
    if entry["expires_at"] <= _now():
        return None
    return entry


def _atomic_write(data: dict, state_dir: Path | None = None, file: Path | None = None) -> None:
    target_dir = state_dir or STATE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = file or (target_dir / STATE_FILE.name)
    fd, tmp = tempfile.mkstemp(prefix=".allowlist-", dir=str(target_dir))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, sort_keys=True, indent=2)
        os.replace(tmp, target_file)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_history(entries: list, state_dir: Path | None = None) -> None:
    target_dir = state_dir or STATE_DIR
    target_file = target_dir / "active_allowlist_history.json"
    _atomic_write({i: e for i, e in enumerate(entries)}, state_dir=target_dir, file=target_file)


def build_supervisor_entry(
    *,
    mint: str,
    thesis_id: str,
    max_notional_usd: float,
    intent: str,
    extensions_report: dict,
    liquidity_evidence: dict,
    rationale: str,
    created_by: str = "supervisor",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict:
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be in (0, {MAX_TTL_SECONDS}]")
    now = _now()
    return {
        "mint": mint,
        "thesis_id": thesis_id,
        "max_notional_usd": max_notional_usd,
        "intent": intent,
        "extensions_report": extensions_report,
        "liquidity_evidence": liquidity_evidence,
        "rationale": rationale,
        "created_at": now,
        "expires_at": now + ttl_seconds,
        "created_by": created_by,
    }