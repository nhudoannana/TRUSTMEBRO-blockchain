"""Regression tests cho vòng review thứ 2 (sau khi PR #1 đã vá 4 lỗi vòng 1).

  #5 verify_selective_claim tin claims_root của transaction dù transaction
     đã bị sửa sau khi tạo (không verify chữ ký/tx_id trước khi đọc payload).
  #6 compute_claim_leaf_hash nối chuỗi "name:value:salt" bằng dấu ':' —
     nhập nhằng ranh giới nếu value chứa ':'.
"""

from dataclasses import asdict

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.claim_merkle import build_claims_merkle_tree, compute_claim_leaf_hash
from blockchain.mining import mine_block
from blockchain.transaction import Credential, Transaction
from blockchain.wallet import generate_wallet


def _issue_with_claims(claims: dict[str, str], cred_id="CRED-RF2-001"):
    w = generate_wallet()
    cred = Credential(cred_id, "ĐH-A", "Alice", "BSc CS", "2026-06-01", {})
    claims_root, salts, proofs, _, _ = build_claims_merkle_tree(claims)
    tx = Transaction("ISSUE", w.public_key_hex, {**asdict(cred), "claims_root": claims_root})
    tx.sign(w)

    bc = Blockchain()
    blk = Block(transactions=[tx], height=1, previous_hash=bc.get_latest_block().compute_hash(), difficulty=1)
    mine_block(blk)
    bc.add_block(blk)
    return bc, tx, salts, proofs


# ── #5: verify_selective_claim phải bác transaction đã bị sửa ───────────

def test_verify_selective_claim_rejects_tampered_transaction():
    bc, tx, salts, proofs = _issue_with_claims({"gpa": "3.8", "grade": "A"})

    # Kẻ tấn công đổi claims_root sau khi transaction đã lên chain, tự tạo
    # proof khớp với root giả do họ kiểm soát.
    forged_root, forged_salts, forged_proofs, _, _ = build_claims_merkle_tree(
        {"gpa": "4.0", "grade": "A+"}
    )
    tx.payload["claims_root"] = forged_root

    ok, reason, _ = bc.verify_selective_claim(
        "CRED-RF2-001", "gpa", "4.0", forged_salts["gpa"], forged_proofs["gpa"]
    )
    assert ok is False
    assert "giả mạo" in reason


def test_verify_selective_claim_accepts_genuine_untampered_claim():
    bc, tx, salts, proofs = _issue_with_claims({"gpa": "3.8", "grade": "A"})

    ok, reason, info = bc.verify_selective_claim(
        "CRED-RF2-001", "gpa", "3.8", salts["gpa"], proofs["gpa"]
    )
    assert ok is True
    assert info["claims_root"] == tx.payload["claims_root"]


def test_verify_selective_claim_rejects_when_chain_invalid():
    bc, tx, salts, proofs = _issue_with_claims({"gpa": "3.8"})
    # Phá vỡ tính hợp lệ của chain (giả lập chain bị tấn công ở chỗ khác)
    bc.chain[1].header.previous_hash = "0" * 64

    ok, reason, _ = bc.verify_selective_claim(
        "CRED-RF2-001", "gpa", "3.8", salts["gpa"], proofs["gpa"]
    )
    assert ok is False
    assert "Blockchain không hợp lệ" in reason


# ── #6: leaf hash không còn nhập nhằng khi value chứa ':' ───────────────

def test_leaf_hash_no_longer_ambiguous_with_colon_in_value():
    # Trước đây: "a" + ":" + "b:c" + ":" + "s"  ==  "a:b" + ":" + "c" + ":" + "s"
    # (khi nối chuỗi thô, hai bộ (name, value) khác nhau cho cùng raw string)
    h1 = compute_claim_leaf_hash("a", "b:c", "s")
    h2 = compute_claim_leaf_hash("a:b", "c", "s")
    assert h1 != h2


def test_leaf_hash_deterministic():
    assert compute_claim_leaf_hash("grade", "A", "salt1") == compute_claim_leaf_hash("grade", "A", "salt1")
