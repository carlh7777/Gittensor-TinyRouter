"""Cost-ledger hash-chain: writer and verifier must use the same payload string."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from trinity.llm.cost_ledger import entry_payload, link_hash, verify_ledger_chain


def _append_writer_line(path: Path, model: str, pt: int, ct: int, prev_hash: str = "") -> str:
    """Write one ledger line in the same format as OpenRouterPool._ledger_append."""
    short = model.rsplit("/", 1)[-1]
    payload = entry_payload(short, pt, ct)
    h = link_hash(prev_hash, payload)
    with open(path, "a") as f:
        f.write(f'{{"m":"{short}","p":{int(pt)},"c":{int(ct)},"h":"{h}"}}\n')
    return h


def test_entry_payload_is_not_json_dumps_sort_keys():
    """Regression: json.dumps(sort_keys=True) used to break every honest chain."""
    payload = entry_payload("qwen/qwen3.5-35b-a3b", 10, 20)
    assert payload == '{"m":"qwen3.5-35b-a3b","p":10,"c":20}'
    wrong = json.dumps({"m": "qwen3.5-35b-a3b", "p": 10, "c": 20}, sort_keys=True)
    assert payload != wrong


def test_verify_accepts_writer_format(tmp_path):
    ledger = tmp_path / "cost_ledger.jsonl"
    h0 = _append_writer_line(ledger, "qwen/qwen3.5-35b-a3b", 100, 50)
    _append_writer_line(ledger, "minimax/minimax-m3", 200, 80, prev_hash=h0)
    valid, n, err = verify_ledger_chain(ledger)
    assert valid and n == 2 and err == ""


def test_old_json_dumps_verifier_would_reject_honest_ledger(tmp_path):
    """Pin the bug: re-serializing with json.dumps(sort_keys=True) mismatches."""
    ledger = tmp_path / "cost_ledger.jsonl"
    _append_writer_line(ledger, "qwen/qwen3.5-35b-a3b", 100, 50)
    line = ledger.read_text().strip()
    r = json.loads(line)
    expected_h = r.pop("h")
    wrong_payload = json.dumps(r, sort_keys=True)
    wrong_h = hashlib.sha256(wrong_payload.encode()).hexdigest()
    assert wrong_h != expected_h
    # Fixed verifier still accepts the same line.
    valid, n, err = verify_ledger_chain(ledger)
    assert valid and n == 1 and err == ""


def test_verify_rejects_tampered_entry(tmp_path):
    ledger = tmp_path / "cost_ledger.jsonl"
    _append_writer_line(ledger, "qwen/qwen3.5-35b-a3b", 100, 50)
    line = ledger.read_text().strip()
    rec = json.loads(line)
    rec["p"] = 999_999  # keep stale hash
    # Keep writer-like formatting for the tampered body so only the value changes.
    ledger.write_text(
        f'{{"m":"{rec["m"]}","p":{rec["p"]},"c":{rec["c"]},"h":"{rec["h"]}"}}\n'
    )
    valid, _n, err = verify_ledger_chain(ledger)
    assert not valid
    assert "hash mismatch" in err


def test_link_hash_matches_sha256():
    payload = entry_payload("m", 1, 2)
    assert link_hash("", payload) == hashlib.sha256(payload.encode()).hexdigest()


if __name__ == "__main__":
    import tempfile

    test_entry_payload_is_not_json_dumps_sort_keys()
    test_link_hash_matches_sha256()
    for fn in (
        test_verify_accepts_writer_format,
        test_old_json_dumps_verifier_would_reject_honest_ledger,
        test_verify_rejects_tampered_entry,
    ):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("ALL PASS")
