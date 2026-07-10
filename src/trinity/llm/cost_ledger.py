"""Cost-ledger hash-chain helpers shared by the writer and verifiers.

The OpenRouter client appends one JSONL line per API call when
``TRINITY_COST_LEDGER`` is set. Integrity depends on hashing the *exact* same
payload string the writer used — not a re-serialized ``json.dumps`` of the
parsed object (key order / spacing differ and break every honest chain).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

__all__ = [
    "entry_payload",
    "link_hash",
    "verify_ledger_chain",
]


def entry_payload(model: str, prompt_tokens: int, completion_tokens: int) -> str:
    """Canonical hash payload for one ledger entry (must match the writer)."""
    short = model.rsplit("/", 1)[-1]
    pt = int(prompt_tokens)
    ct = int(completion_tokens)
    return f'{{"m":"{short}","p":{pt},"c":{ct}}}'


def link_hash(prev_hash: str, payload: str) -> str:
    """sha256(prev_hash + payload) hex digest."""
    return hashlib.sha256((prev_hash + payload).encode()).hexdigest()


def verify_ledger_chain(path: str | Path) -> tuple[bool, int, str]:
    """Verify the hash-chain integrity of a cost ledger.

    Each entry's ``h`` field must equal ``link_hash(prev_h, entry_payload(...))``.
    The first entry's previous hash is the empty string.

    Returns:
        ``(valid, num_entries, error_message)``. If valid, ``error_message`` is empty.
    """
    prev_hash = ""
    entries = 0
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                return False, entries, f"line {lineno}: invalid JSON"
            expected_h = r.pop("h", None)
            if expected_h is None:
                return False, entries, (
                    f"line {lineno}: missing hash field 'h' "
                    f"(ledger entries must be written by OpenRouterPool with hash-chain enabled)"
                )
            try:
                payload = entry_payload(r["m"], r["p"], r["c"])
            except (KeyError, TypeError, ValueError) as exc:
                return False, entries, f"line {lineno}: malformed entry ({exc})"
            computed_h = link_hash(prev_hash, payload)
            if computed_h != expected_h:
                return False, entries, (
                    f"line {lineno}: hash mismatch — expected {computed_h[:16]}..., "
                    f"got {expected_h[:16]}... (chain broken or entry tampered)"
                )
            prev_hash = computed_h
            entries += 1
    return True, entries, ""
