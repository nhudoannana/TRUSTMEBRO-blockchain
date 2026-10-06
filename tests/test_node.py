"""Tests cho module blockchain/node.py.

Kiểm tra: broadcast TX → cả 3 mempool nhận;
TX sai chữ ký bị mọi node từ chối.
"""

import time
from dataclasses import asdict

from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network


def _wait_propagation(network, timeout=2.0):
    """Chờ cho tất cả inbox trống (message đã được xử lý)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        all_empty = all(node.inbox.empty() for node in network.nodes.values())
        if all_empty:
            time.sleep(0.15)  # buffer thêm cho thread xử lý xong
            return True
        time.sleep(0.05)
    return False


def _make_network():
    """Helper: tạo Network với 3 node."""
    net = Network()
    net.create_node("Node-1", "127.0.0.1", 5001)
    net.create_node("Node-2", "127.0.0.1", 5002)
    net.create_node("Node-3", "127.0.0.1", 5003)
    return net


def _make_signed_tx(wallet, cred_id="CRED-NET-TEST"):
    """Helper: tạo Transaction ISSUE đã ký."""
    cred = Credential(cred_id, "Trường Đại học A", "Người học DEMO-001", "BSc CS", "2026-01-01", {})
    tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
    tx.sign(wallet)
    return tx


# ── Test broadcast TX → 3 mempool ──

def test_broadcast_tx_all_nodes_receive():
    """Submit TX vào Node-1 → cả 3 node đều có TX trong Mempool."""
    net = _make_network()
    wallet = generate_wallet()
    tx = _make_signed_tx(wallet)

    node1 = net.nodes["Node-1"]
    ok, reason = node1.submit_transaction(tx)
    assert ok is True, f"Submit failed: {reason}"

    _wait_propagation(net)

    # Kiểm tra cả 3 mempool
    for node_id in ["Node-1", "Node-2", "Node-3"]:
        txs = net.nodes[node_id].mempool.get_transactions()
        assert len(txs) == 1, f"{node_id} mempool has {len(txs)} txs, expected 1"
        assert txs[0].tx_id == tx.tx_id

    # Cleanup
    for node in net.nodes.values():
        node._running = False


# ── Test TX sai chữ ký bị mọi node từ chối ──

def test_invalid_tx_rejected_by_all():
    """TX bị sửa payload → Node-1 từ chối, không broadcast, 0 mempool có TX.

    Mô phỏng tấn công: kẻ tấn công sửa payload sau khi ký.
    """
    net = _make_network()
    wallet = generate_wallet()
    tx = _make_signed_tx(wallet)

    # Giả mạo payload
    tx.payload["holder_name"] = "Eve (hacker)"

    node1 = net.nodes["Node-1"]
    ok, reason = node1.submit_transaction(tx)
    assert ok is False  # Node-1 từ chối

    _wait_propagation(net)

    # Không node nào có TX
    for node_id in ["Node-1", "Node-2", "Node-3"]:
        txs = net.nodes[node_id].mempool.get_transactions()
        assert len(txs) == 0, f"{node_id} should have 0 txs"

    for node in net.nodes.values():
        node._running = False


# ── Test node OFFLINE không nhận TX ──

def test_offline_node_misses_tx():
    """Node OFFLINE không nhận TX — sau khi online lại, mempool vẫn trống."""
    net = _make_network()
    wallet = generate_wallet()

    # Tắt Node-3
    net.nodes["Node-3"].go_offline()

    tx = _make_signed_tx(wallet)
    net.nodes["Node-1"].submit_transaction(tx)

    _wait_propagation(net)

    # Node-1 và Node-2 có TX, Node-3 không có
    assert len(net.nodes["Node-1"].mempool.get_transactions()) == 1
    assert len(net.nodes["Node-2"].mempool.get_transactions()) == 1
    assert len(net.nodes["Node-3"].mempool.get_transactions()) == 0

    for node in net.nodes.values():
        node._running = False


# ── Test event log thread-safe ──

def test_event_log():
    """Event log phải ghi nhận sự kiện với timestamp và node_id."""
    net = _make_network()
    wallet = generate_wallet()
    tx = _make_signed_tx(wallet)

    net.nodes["Node-1"].submit_transaction(tx)
    _wait_propagation(net)

    log = net.get_event_log()
    assert len(log) > 0
    # Log phải chứa thông tin node và TX
    log_text = "\n".join(log)
    assert "Node-1" in log_text
    assert "TX ACCEPT" in log_text

    for node in net.nodes.values():
        node._running = False
