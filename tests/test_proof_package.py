"""Tests cho proof_package — xuất/nhập gói Selective Disclosure Proof.

Kiểm tra:
- Proof đúng → đạt.
- Sửa claim_value, salt, proof, credential_id → thất bại.
- Thu hồi credential → proof cũ bị từ chối.
- Gói xuất không chứa claim không được chọn.
- Parse lỗi cấu trúc / file quá lớn / JSON sai.
"""

import json
import copy
import pytest

from blockchain.wallet import generate_wallet
from blockchain.transaction import Transaction, Credential
from blockchain.blockchain import Blockchain
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.claim_merkle import build_claims_merkle_tree
from blockchain.proof_package import (
    build_proof_package,
    export_proof_json,
    parse_proof_package,
    FORMAT_VERSION,
    MAX_PROOF_FILE_SIZE,
)
from dataclasses import asdict


# ── Fixtures ──

def _setup_chain_with_credential():
    """Tạo chain có 1 credential với claims, trả về mọi thông tin cần thiết."""
    wallet = generate_wallet()
    bc = Blockchain()

    claims = {"gpa": "3.85", "grade": "A", "major": "Computer Science"}
    claims_root, salts, proofs, tree_levels, claim_items = build_claims_merkle_tree(claims)

    cred = Credential(
        credential_id="CRED-PROOF-001",
        issuer_name="Trường Đại học A",
        holder_name="Người học DEMO-001",
        title="BSc Demo",
        issue_date="2026-01-01",
        claims=claims,
        claims_root=claims_root,
    )
    tx = Transaction("ISSUE", wallet.public_key_hex, cred.to_onchain_payload())
    tx.sign(wallet)

    prev = bc.get_latest_block().compute_hash()
    block = Block(transactions=[tx], height=1, previous_hash=prev, difficulty=2)
    mine_block(block)
    bc.add_block(block)

    return bc, wallet, claims, salts, proofs, claims_root


# ── Test build & parse proof package ──

class TestProofPackage:
    """Test xây dựng, xuất và phân tích gói proof."""

    def test_build_and_parse_roundtrip(self):
        """Build → export → parse → verify fields match."""
        pkg = build_proof_package(
            credential_id="CRED-001",
            claim_name="grade",
            claim_value="A",
            salt="abc123",
            merkle_proof=[("hash1", "left"), ("hash2", "right")],
        )
        json_str = export_proof_json(pkg)
        ok, err, parsed = parse_proof_package(json_str)

        assert ok, f"Parse failed: {err}"
        assert parsed["credential_id"] == "CRED-001"
        assert parsed["claim_name"] == "grade"
        assert parsed["claim_value"] == "A"
        assert parsed["salt"] == "abc123"
        assert parsed["merkle_proof"] == [("hash1", "left"), ("hash2", "right")]

    def test_package_does_not_contain_other_claims(self):
        """Gói xuất chỉ chứa đúng 1 claim, không chứa claim khác."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        # Export chỉ claim "grade"
        pkg = build_proof_package(
            credential_id="CRED-PROOF-001",
            claim_name="grade",
            claim_value="A",
            salt=salts["grade"],
            merkle_proof=proofs["grade"],
        )
        json_str = export_proof_json(pkg)

        # Kiểm tra không chứa claim khác
        assert "gpa" not in json_str.lower().split('"claim_name"')[0]  # not in other fields
        assert salts["gpa"] not in json_str
        assert salts["major"] not in json_str
        assert "3.85" not in json_str
        assert "Computer Science" not in json_str

    def test_format_version_present(self):
        """Gói có format_version đúng."""
        pkg = build_proof_package("C1", "k", "v", "s", [])
        assert pkg["format_version"] == FORMAT_VERSION

    def test_note_mentions_not_zkp(self):
        """Ghi chú rõ không phải ZKP."""
        pkg = build_proof_package("C1", "k", "v", "s", [])
        assert "ZKP" in pkg.get("note", "") or "Zero-Knowledge" in pkg.get("note", "")

    def test_no_private_key_in_package(self):
        """Gói không chứa private key."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()
        pkg = build_proof_package("CRED-PROOF-001", "grade", "A", salts["grade"], proofs["grade"])
        json_str = export_proof_json(pkg)
        assert "PRIVATE" not in json_str.upper()
        assert wallet.private_key_pem not in json_str


class TestParseValidation:
    """Test parse kiểm tra cấu trúc và giới hạn."""

    def test_empty_file(self):
        ok, err, _ = parse_proof_package("")
        assert not ok
        assert "rỗng" in err.lower()

    def test_invalid_json(self):
        ok, err, _ = parse_proof_package("{not valid json")
        assert not ok
        assert "json" in err.lower()

    def test_wrong_version(self):
        data = {"format_version": "WRONG-v99", "credential_id": "X", "claim_name": "k",
                "claim_value": "v", "salt": "s", "merkle_proof": []}
        ok, err, _ = parse_proof_package(json.dumps(data))
        assert not ok
        assert "phiên bản" in err.lower()

    def test_missing_field(self):
        data = {"format_version": FORMAT_VERSION, "credential_id": "X"}
        ok, err, _ = parse_proof_package(json.dumps(data))
        assert not ok
        assert "thiếu" in err.lower()

    def test_bad_proof_direction(self):
        data = {"format_version": FORMAT_VERSION, "credential_id": "X", "claim_name": "k",
                "claim_value": "v", "salt": "s", "merkle_proof": [["hash", "up"]]}
        ok, err, _ = parse_proof_package(json.dumps(data))
        assert not ok
        assert "direction" in err.lower() or "left" in err.lower()

    def test_file_too_large(self):
        big = "x" * (MAX_PROOF_FILE_SIZE + 100)
        ok, err, _ = parse_proof_package(big)
        assert not ok
        assert "lớn" in err.lower()


class TestVerifyWithChain:
    """Test xác minh proof trên chain thật."""

    def test_valid_proof_accepted(self):
        """Proof đúng → verify thành công."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        pkg = build_proof_package("CRED-PROOF-001", "grade", "A", salts["grade"], proofs["grade"])
        json_str = export_proof_json(pkg)
        ok, err, parsed = parse_proof_package(json_str)
        assert ok

        vok, reason, info = bc.verify_selective_claim(
            credential_id=parsed["credential_id"],
            claim_name=parsed["claim_name"],
            claim_value=parsed["claim_value"],
            salt=parsed["salt"],
            proof=parsed["merkle_proof"],
        )
        assert vok, f"Verify failed: {reason}"
        assert info["claims_root"] == root

    def test_tampered_claim_value_rejected(self):
        """Sửa claim_value → thất bại."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        pkg = build_proof_package("CRED-PROOF-001", "grade", "A", salts["grade"], proofs["grade"])
        pkg["claim_value"] = "F"  # Giả mạo
        json_str = export_proof_json(pkg)
        _, _, parsed = parse_proof_package(json_str)

        vok, reason, _ = bc.verify_selective_claim(
            parsed["credential_id"], parsed["claim_name"], parsed["claim_value"],
            parsed["salt"], parsed["merkle_proof"],
        )
        assert not vok
        assert "Merkle" in reason or "không khớp" in reason

    def test_tampered_salt_rejected(self):
        """Sửa salt → thất bại."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        pkg = build_proof_package("CRED-PROOF-001", "grade", "A", "wrong_salt_value", proofs["grade"])
        json_str = export_proof_json(pkg)
        _, _, parsed = parse_proof_package(json_str)

        vok, reason, _ = bc.verify_selective_claim(
            parsed["credential_id"], parsed["claim_name"], parsed["claim_value"],
            parsed["salt"], parsed["merkle_proof"],
        )
        assert not vok

    def test_tampered_proof_rejected(self):
        """Sửa merkle_proof → thất bại."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        bad_proof = [("0000000000000000000000000000000000000000000000000000000000000000", "left")]
        pkg = build_proof_package("CRED-PROOF-001", "grade", "A", salts["grade"], bad_proof)
        json_str = export_proof_json(pkg)
        _, _, parsed = parse_proof_package(json_str)

        vok, reason, _ = bc.verify_selective_claim(
            parsed["credential_id"], parsed["claim_name"], parsed["claim_value"],
            parsed["salt"], parsed["merkle_proof"],
        )
        assert not vok

    def test_wrong_credential_id_rejected(self):
        """Credential ID sai → thất bại."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        pkg = build_proof_package("CRED-NONEXIST", "grade", "A", salts["grade"], proofs["grade"])
        json_str = export_proof_json(pkg)
        _, _, parsed = parse_proof_package(json_str)

        vok, reason, _ = bc.verify_selective_claim(
            parsed["credential_id"], parsed["claim_name"], parsed["claim_value"],
            parsed["salt"], parsed["merkle_proof"],
        )
        assert not vok
        assert "NOT_FOUND" in reason or "không" in reason

    def test_revoked_credential_rejected(self):
        """Thu hồi credential → proof cũ bị từ chối."""
        bc, wallet, claims, salts, proofs, root = _setup_chain_with_credential()

        # Proof hợp lệ trước khi thu hồi
        vok, _, _ = bc.verify_selective_claim(
            "CRED-PROOF-001", "grade", "A", salts["grade"], proofs["grade"],
        )
        assert vok, "Proof should be valid before revocation"

        # Thu hồi
        revoke_tx = Transaction("REVOKE", wallet.public_key_hex, {
            "credential_id": "CRED-PROOF-001",
            "reason": "Test revocation",
        })
        revoke_tx.sign(wallet)

        prev = bc.get_latest_block().compute_hash()
        revoke_block = Block(transactions=[revoke_tx], height=len(bc.chain),
                             previous_hash=prev, difficulty=2)
        mine_block(revoke_block)
        bc.add_block(revoke_block)

        # Proof cũ phải bị từ chối
        vok, reason, _ = bc.verify_selective_claim(
            "CRED-PROOF-001", "grade", "A", salts["grade"], proofs["grade"],
        )
        assert not vok
        assert "REVOKED" in reason or "ACTIVE" in reason
