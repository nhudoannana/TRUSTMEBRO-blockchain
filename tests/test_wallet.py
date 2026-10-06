"""Tests cho module blockchain/wallet.py.

Kiểm tra tạo ví, ký/xác minh đúng, phát hiện message bị sửa,
và phát hiện dùng sai khoá công khai.
"""

from blockchain.wallet import generate_wallet, sign_message, verify_signature


# ── Test generate_wallet ──

def test_wallet_fields():
    """Wallet phải có đủ 3 trường, address dài 40 ký tự."""
    w = generate_wallet()
    assert w.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert len(w.public_key_hex) == 130  # uncompressed point: 04 + 32x + 32y = 65 bytes = 130 hex
    assert len(w.address) == 40


# ── Test sign & verify đúng ──

def test_sign_verify_valid():
    """Ký rồi xác minh cùng message, cùng khoá → True."""
    w = generate_wallet()
    msg = "Credential for Holder A"
    sig = sign_message(msg, w.private_key_pem)
    assert verify_signature(msg, sig, w.public_key_hex) is True


# ── Test tấn công: sửa message ──

def test_tampered_message():
    """Sửa message sau khi ký → chữ ký INVALID.

    Mô phỏng: kẻ tấn công đổi '10 BTC' thành '100 BTC'.
    """
    w = generate_wallet()
    original = "Transfer 10 BTC to Bob"
    sig = sign_message(original, w.private_key_pem)

    tampered = "Transfer 100 BTC to Bob"
    assert verify_signature(tampered, sig, w.public_key_hex) is False


# ── Test tấn công: dùng public key khác ──

def test_wrong_public_key():
    """Verify bằng public key của người khác → INVALID.

    Mô phỏng: kẻ tấn công ký bằng khoá riêng của mình
    nhưng claim là chữ ký của nạn nhân.
    """
    alice = generate_wallet()
    eve = generate_wallet()

    msg = "Legitimate credential"
    sig = sign_message(msg, eve.private_key_pem)  # Eve ký

    # Verify bằng public key Alice → phải thất bại
    assert verify_signature(msg, sig, alice.public_key_hex) is False
