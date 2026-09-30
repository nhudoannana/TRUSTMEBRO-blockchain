"""Tests cho module blockchain/claim_merkle.py và tính năng Selective Disclosure.

Kiểm tra:
- Sinh salt ngẫu nhiên bảo mật 128-bit.
- Băm lá Merkle: hash(claim_name + claim_value + salt).
- Xây dựng Merkle Tree từ claims, tính claims_root.
- Sinh và xác minh Merkle Proof (Proof of Inclusion) cho từng claim riêng lẻ.
- Phát hiện giả mạo khi sai giá trị claim hoặc sai salt.
- Mô phỏng tấn công vét cạn / từ điển (Dictionary attack):
  không salt bị băm thử đoán ra ngay, có salt an toàn tuyệt đối.
- Chỉ claims_root được lưu trên payload on-chain, không lưu plaintext claims.
- Xác minh selective claim end-to-end qua Blockchain.
"""

from dataclasses import asdict
from blockchain.hash import sha256_hex
from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.blockchain import Blockchain
from blockchain.claim_merkle import (
    generate_salt,
    compute_claim_leaf_hash,
    build_claims_merkle_tree,
    verify_claim_inclusion_proof,
    simulate_dictionary_attack,
)


def test_claim_leaf_hash_with_salt():
    """Hash lá Merkle phải phụ thuộc vào claim_name, claim_value và salt."""
    salt1 = generate_salt()
    salt2 = generate_salt()

    h1 = compute_claim_leaf_hash("grade", "A", salt1)
    h2 = compute_claim_leaf_hash("grade", "A", salt2)
    h3 = compute_claim_leaf_hash("grade", "B", salt1)

    assert len(h1) == 64
    # Hai salt khác nhau phải sinh ra hai hash hoàn toàn khác nhau (chống băm thử)
    assert h1 != h2
    # Giá trị khác nhau cũng phải khác hash
    assert h1 != h3


def test_build_claims_merkle_tree_and_proof():
    """Xây cây Merkle từ các claims và xác minh Proof of Inclusion cho từng claim."""
    claims = {
        "full_name": "Alice Nguyen",
        "major": "Computer Science",
        "gpa": "3.85",
        "grade": "A",
        "honors": "Summa Cum Laude",
    }

    claims_root, salts, proofs, tree, items = build_claims_merkle_tree(claims)

    assert len(claims_root) == 64
    assert len(salts) == len(claims)
    assert len(proofs) == len(claims)

    # Xác minh từng claim riêng lẻ với root mà không cần biết các claim khác
    for key, val in claims.items():
        salt = salts[key]
        proof = proofs[key]
        is_valid = verify_claim_inclusion_proof(key, val, salt, proof, claims_root)
        assert is_valid is True, f"Proof of inclusion failed for claim '{key}'"


def test_tampered_claim_fails_verification():
    """Sửa giá trị claim hoặc salt làm xác minh thất bại."""
    claims = {"degree": "BSc", "grade": "A", "gpa": "3.9"}
    claims_root, salts, proofs, _, _ = build_claims_merkle_tree(claims)

    # Kẻ tấn công hoặc người xác minh đổi grade từ A sang A+
    fake_val_ok = verify_claim_inclusion_proof(
        "grade", "A+", salts["grade"], proofs["grade"], claims_root
    )
    assert fake_val_ok is False

    # Dùng sai salt
    wrong_salt = generate_salt()
    wrong_salt_ok = verify_claim_inclusion_proof(
        "grade", "A", wrong_salt, proofs["grade"], claims_root
    )
    assert wrong_salt_ok is False


def test_dictionary_attack_mitigation():
    """Mô phỏng tấn công từ điển: không salt bị lộ, có salt được bảo vệ."""
    claim_name = "grade"
    true_value = "A"
    domain = ["A", "B", "C", "D", "F"]

    # TH1: KHÔNG có salt (hoặc salt rỗng)
    unsalted_hash = compute_claim_leaf_hash(claim_name, true_value, salt="")
    cracked, cracked_val, attempts = simulate_dictionary_attack(
        claim_name, unsalted_hash, domain, salt=""
    )
    assert cracked is True
    assert cracked_val == "A"
    assert attempts <= len(domain)

    # TH2: CÓ salt ngẫu nhiên 128-bit
    secret_salt = generate_salt()
    salted_hash = compute_claim_leaf_hash(claim_name, true_value, salt=secret_salt)

    # Kẻ tấn công thử dò trong domain hẹp mà không biết salt
    cracked_salted, _, _ = simulate_dictionary_attack(
        claim_name, salted_hash, domain, salt=""
    )
    assert cracked_salted is False


def test_onchain_payload_only_contains_claims_root():
    """Payload đưa lên blockchain chỉ chứa claims_root, không lưu claims hay salts."""
    claims = {"major": "AI & Blockchain", "gpa": "4.0", "grade": "A"}
    claims_root, salts, proofs, _, _ = build_claims_merkle_tree(claims)

    cred = Credential(
        credential_id="CRED-ROOT-ONLY",
        issuer_name="National University",
        holder_name="Bob Smith",
        title="BSc Software Engineering",
        issue_date="2026-06-30",
        claims=claims,
        claims_root=claims_root,
    )

    onchain_payload = cred.to_onchain_payload()

    # Kiểm tra payload on-chain
    assert "claims_root" in onchain_payload
    assert onchain_payload["claims_root"] == claims_root
    assert "claims" not in onchain_payload
    assert "salts" not in onchain_payload


def test_selective_claim_verification_on_blockchain():
    """Luồng end-to-end: Issue cred lên chain -> Holder gửi 1 claim -> Verifier đối soát với chain."""
    wallet = generate_wallet()
    claims = {"grade": "A", "gpa": "3.8", "status": "Graduated"}
    claims_root, salts, proofs, _, _ = build_claims_merkle_tree(claims)

    cred = Credential(
        credential_id="CRED-SEL-001",
        issuer_name="Tech University",
        holder_name="Alice",
        title="BSc Computer Science",
        issue_date="2026-06-15",
        claims_root=claims_root,
    )

    tx = Transaction("ISSUE", wallet.public_key_hex, cred.to_onchain_payload())
    tx.sign(wallet)

    bc = Blockchain()
    from blockchain.block import Block
    from blockchain.mining import mine_block

    block = Block(
        transactions=[tx],
        height=1,
        previous_hash=bc.get_latest_block().compute_hash(),
        difficulty=2,
    )
    mine_block(block)
    bc.add_block(block)

    # Verifier kiểm chứng claim 'grade = A'
    ok, reason, info = bc.verify_selective_claim(
        credential_id="CRED-SEL-001",
        claim_name="grade",
        claim_value="A",
        salt=salts["grade"],
        proof=proofs["grade"],
    )

    assert ok is True
    assert "Proof of Inclusion" in reason
    assert info["claims_root"] == claims_root

    # Verifier thử kiểm chứng với giá trị sai 'grade = B'
    ok_fake, reason_fake, _ = bc.verify_selective_claim(
        credential_id="CRED-SEL-001",
        claim_name="grade",
        claim_value="B",
        salt=salts["grade"],
        proof=proofs["grade"],
    )
    assert ok_fake is False

