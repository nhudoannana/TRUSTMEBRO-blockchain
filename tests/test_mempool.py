"""Tests cho module blockchain/mempool.py.

Kiểm tra thêm transaction hợp lệ, và ba trường hợp bị từ chối:
sửa payload, Issuer không được phép, nộp trùng.
"""

from dataclasses import asdict

from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.mempool import Mempool, DummyLedger


def _make_credential(cred_id="CRED-TEST"):
    """Helper: tạo một Credential mẫu."""
    return Credential(
        credential_id=cred_id,
        issuer_name="Trường Đại học A",
        holder_name="Người học DEMO-001",
        title="BSc CS",
        issue_date="2026-01-01",
        claims={"gpa": "3.5"},
    )


def _make_signed_tx(wallet, cred_id="CRED-TEST"):
    """Helper: tạo Transaction ISSUE đã ký."""
    cred = _make_credential(cred_id)
    tx = Transaction(
        tx_type="ISSUE",
        sender_public_key=wallet.public_key_hex,
        payload=asdict(cred),
    )
    tx.sign(wallet)
    return tx


# ── Test thêm transaction hợp lệ ──

def test_add_valid_transaction():
    """Transaction hợp lệ, Issuer được phép → thêm thành công."""
    wallet = generate_wallet()
    mempool = Mempool(authorized_issuers={wallet.public_key_hex})
    tx = _make_signed_tx(wallet)

    ok, reason = mempool.add_transaction(tx, DummyLedger())
    assert ok is True
    assert "Đã thêm" in reason
    assert len(mempool.get_transactions()) == 1


# ── Test từ chối: sửa payload sau khi ký ──

def test_reject_tampered_payload():
    """Sửa payload sau khi ký → từ chối, reason nói rõ lý do.

    Mô phỏng tấn công: kẻ tấn công đổi holder_name sau khi Issuer ký.
    """
    wallet = generate_wallet()
    mempool = Mempool(authorized_issuers={wallet.public_key_hex})
    tx = _make_signed_tx(wallet)

    # Giả mạo payload
    tx.payload["holder_name"] = "Eve"

    ok, reason = mempool.add_transaction(tx, DummyLedger())
    assert ok is False
    assert "tx_id không khớp hash" in reason or "Chữ ký không khớp" in reason


# ── Test từ chối: Issuer không trong registry ──

def test_reject_unauthorized_issuer():
    """Issuer không nằm trong danh sách được phép → từ chối.

    Mô phỏng: tổ chức giả mạo cố phát hành credential.
    """
    legit_wallet = generate_wallet()
    rogue_wallet = generate_wallet()

    # Chỉ cho phép legit_wallet
    mempool = Mempool(authorized_issuers={legit_wallet.public_key_hex})
    tx = _make_signed_tx(rogue_wallet)

    ok, reason = mempool.add_transaction(tx, DummyLedger())
    assert ok is False
    assert "không nằm trong danh sách được phép" in reason


# ── Test từ chối: nộp trùng tx_id ──

def test_reject_duplicate_tx():
    """Nộp cùng transaction lần 2 → từ chối (chống replay).

    Mô phỏng: kẻ tấn công bắt transaction hợp lệ rồi phát lại.
    """
    wallet = generate_wallet()
    mempool = Mempool(authorized_issuers={wallet.public_key_hex})
    tx = _make_signed_tx(wallet)

    ok1, _ = mempool.add_transaction(tx, DummyLedger())
    assert ok1 is True

    ok2, reason2 = mempool.add_transaction(tx, DummyLedger())
    assert ok2 is False
    assert "đã tồn tại" in reason2


# ── Test remove_transactions ──

def test_remove_transactions():
    """Sau khi đóng block, transaction phải bị xoá khỏi Mempool."""
    wallet = generate_wallet()
    mempool = Mempool(authorized_issuers={wallet.public_key_hex})

    tx1 = _make_signed_tx(wallet, "CRED-A")
    tx2 = _make_signed_tx(wallet, "CRED-B")
    mempool.add_transaction(tx1, DummyLedger())
    mempool.add_transaction(tx2, DummyLedger())
    assert len(mempool.get_transactions()) == 2

    mempool.remove_transactions([tx1.tx_id])
    assert len(mempool.get_transactions()) == 1
    assert mempool.get_transactions()[0].tx_id == tx2.tx_id
