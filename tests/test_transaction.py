"""Tests cho module blockchain/transaction.py.

Kiểm tra tạo credential, ký transaction, xác minh hợp lệ,
và phát hiện giả mạo khi payload bị sửa sau khi ký.
"""

from dataclasses import asdict

from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction, verify_transaction


def _make_signed_tx():
    """Helper: tạo transaction ISSUE đã ký, dùng chung cho nhiều test."""
    wallet = generate_wallet()
    cred = Credential(
        credential_id="CRED-001",
        issuer_name="Trường Đại học A",
        holder_name="Người học DEMO-001",
        title="BSc Computer Science",
        issue_date="2026-06-01",
        claims={"gpa": "3.8"},
    )
    tx = Transaction(
        tx_type="ISSUE",
        sender_public_key=wallet.public_key_hex,
        payload=asdict(cred),
    )
    tx.sign(wallet)
    return tx, wallet


# ── Test transaction hợp lệ ──

def test_verify_valid_transaction():
    """Transaction ký đúng cách phải verify thành công."""
    tx, _ = _make_signed_tx()
    ok, reason = verify_transaction(tx)
    assert ok is True
    assert reason == "Hợp lệ"


def test_tx_id_matches_hash():
    """tx_id phải bằng compute_hash() sau khi ký."""
    tx, _ = _make_signed_tx()
    assert tx.tx_id == tx.compute_hash()


# ── Test tấn công: sửa payload sau khi ký ──

def test_tampered_payload():
    """Sửa payload sau khi ký → verify thất bại, reason nói rõ lý do.

    Mô phỏng: kẻ tấn công đổi holder_name từ 'Alice' sang 'Eve'.
    """
    tx, _ = _make_signed_tx()

    # Giả mạo payload
    tx.payload["holder_name"] = "Eve"
    # Giữ nguyên tx_id cũ và signature cũ

    ok, reason = verify_transaction(tx)
    assert ok is False
    assert "tx_id không khớp hash" in reason


def test_tampered_payload_rehash():
    """Kẻ tấn công sửa payload VÀ cập nhật tx_id → chữ ký vẫn sai.

    Mô phỏng: kẻ tấn công thông minh hơn, tính lại hash sau khi sửa,
    nhưng không có private key nên chữ ký cũ không khớp hash mới.
    """
    tx, _ = _make_signed_tx()

    # Sửa payload và cập nhật tx_id
    tx.payload["holder_name"] = "Eve"
    tx.tx_id = tx.compute_hash()  # tính lại hash

    ok, reason = verify_transaction(tx)
    assert ok is False
    assert "Chữ ký không khớp" in reason


# ── Test thiếu chữ ký ──

def test_unsigned_transaction():
    """Transaction chưa ký → verify thất bại."""
    wallet = generate_wallet()
    tx = Transaction(
        tx_type="ISSUE",
        sender_public_key=wallet.public_key_hex,
        payload={"credential_id": "CRED-X"},
    )
    # Không gọi tx.sign()
    ok, reason = verify_transaction(tx)
    assert ok is False
    assert "chưa được ký" in reason


# ── Test tx_type sai ──

def test_invalid_tx_type():
    """tx_type không phải ISSUE/REVOKE → verify thất bại."""
    wallet = generate_wallet()
    tx = Transaction(
        tx_type="TRANSFER",
        sender_public_key=wallet.public_key_hex,
        payload={"credential_id": "CRED-X"},
    )
    tx.sign(wallet)
    ok, reason = verify_transaction(tx)
    assert ok is False
    assert "tx_type không hợp lệ" in reason
