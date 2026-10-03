"""Tests cho verify_credential: VERIFIED, REVOKED, NOT_FOUND.

Chạy trọn luồng end-to-end với Network + mining rồi kiểm tra
kết quả xác minh credential.
"""

import time
from dataclasses import asdict

from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network


def _wait(net, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(n.inbox.empty() for n in net.nodes.values()):
            time.sleep(0.15)
            return
        time.sleep(0.05)


def _setup():
    """Tạo network + wallet + submit ISSUE tx + mine."""
    net = Network()
    net.create_node("Node-1", "127.0.0.1", 5001)
    net.create_node("Node-2", "127.0.0.1", 5002)
    net.create_node("Node-3", "127.0.0.1", 5003)

    wallet = generate_wallet()

    cred = Credential("CRED-V-001", "Trường Đại học A", "Người học DEMO-001", "BSc CS", "2026-01-01", {})
    tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
    tx.sign(wallet)

    net.nodes["Node-1"].submit_transaction(tx)
    _wait(net)
    net.nodes["Node-1"].mine_pending(difficulty=2)
    _wait(net)

    return net, wallet


# ── Test 1: credential hợp lệ → VERIFIED ──

def test_credential_verified():
    """Credential ISSUE đã mine → verify trả VERIFIED, 12 bước pass."""
    net, _ = _setup()
    bc = net.nodes["Node-1"].blockchain

    steps, status, info = bc.verify_credential("CRED-V-001")

    assert status == "VERIFIED"
    assert all(ok for _, ok, _ in steps), f"Some step failed: {steps}"
    assert info["holder_name"] == "Người học DEMO-001"
    assert info["credential_id"] == "CRED-V-001"
    assert info["issue_block_height"] >= 1

    for n in net.nodes.values():
        n._running = False


# ── Test 2: sau REVOKE → REVOKED ──

def test_credential_revoked():
    """ISSUE rồi REVOKE → verify trả REVOKED, 11 bước pass + bước 12 fail."""
    net, wallet = _setup()

    # Gửi REVOKE
    revoke_payload = {"credential_id": "CRED-V-001", "reason": "Expired"}
    revoke_tx = Transaction("REVOKE", wallet.public_key_hex, revoke_payload)
    revoke_tx.sign(wallet)

    net.nodes["Node-1"].submit_transaction(revoke_tx)
    _wait(net)
    net.nodes["Node-1"].mine_pending(difficulty=2)
    _wait(net)

    bc = net.nodes["Node-1"].blockchain
    steps, status, info = bc.verify_credential("CRED-V-001")

    assert status == "REVOKED"
    # 11 bước đầu pass, bước 12 (Trạng thái) fail (REVOKED)
    assert len(steps) == 12
    for name, ok, _ in steps[:-1]:
        assert ok, f"Step '{name}' should pass"
    assert steps[-1][1] is False  # Trạng thái = REVOKED → "failed"
    assert "REVOKED" in steps[-1][2]

    # Info phải có lịch sử revoke
    assert "revoke_block_height" in info
    assert info["revoke_reason"] == "Expired"

    for n in net.nodes.values():
        n._running = False


# ── Test 3: credential không tồn tại → NOT_FOUND ──

def test_credential_not_found():
    """Credential chưa từng ISSUE → verify trả NOT_FOUND, bước 1 fail."""
    net = Network()
    net.create_node("Node-1", "127.0.0.1", 5001)

    bc = net.nodes["Node-1"].blockchain
    steps, status, info = bc.verify_credential("CRED-NONEXISTENT")

    assert status == "NOT_FOUND"
    assert len(steps) == 1
    assert steps[0][1] is False  # bước 1 fail
    assert "không tìm thấy" in steps[0][2].lower()

    for n in net.nodes.values():
        n._running = False
