"""Integration tests for PoS consensus in multi-node network and flexible data presets."""

import time
from dataclasses import asdict

from blockchain.wallet import generate_wallet, Wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.claim_merkle import build_claims_merkle_tree, verify_claim_inclusion_proof


def _wait(net, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(n.inbox.empty() for n in net.nodes.values()):
            time.sleep(0.15)
            return
        time.sleep(0.05)


def test_pos_block_network_propagation():
    """Node tạo block PoS với TX thật, broadcast cho các peer và đạt đồng thuận."""
    net = Network()
    n1 = net.create_node("Node-1", "127.0.0.1", 5001)
    n2 = net.create_node("Node-2", "127.0.0.1", 5002)
    n3 = net.create_node("Node-3", "127.0.0.1", 5003)

    w = generate_wallet()
    cred = Credential("CRED-POS-001", "ĐH-A", "Alice Nguyen", "BSc Computer Science", "2026-06-01", {})
    tx = Transaction("ISSUE", w.public_key_hex, asdict(cred))
    tx.sign(w)

    n1.submit_transaction(tx)
    _wait(net)

    # Chọn validator chính danh từ consortium
    val = net.pos_registry.select_validator(height=1, seed=42, previous_hash=n1.blockchain.get_latest_block().compute_hash())
    assert val is not None

    block, res = n1.forge_pos_pending(validator=val, seed=42)
    assert block is not None
    assert block.header.consensus_type == "PoS"
    assert res["validator_name"] == val.name

    _wait(net)

    # Cả 3 node phải chấp nhận block PoS và đạt cùng chiều cao
    for nid, node in net.nodes.items():
        assert node.height == 1
        assert node.blockchain.get_latest_block().compute_hash() == block.compute_hash()
        assert node.blockchain.credential_status("CRED-POS-001") == "ACTIVE"

    for n in net.nodes.values():
        n._running = False


def test_chain_valid_with_mixed_pow_pos_blocks():
    """Chuỗi chứa kết hợp cả block PoW và block PoS vẫn hợp lệ theo is_chain_valid()."""
    net = Network()
    n1 = net.create_node("Node-1", "127.0.0.1", 5001)

    w = generate_wallet()

    # Block 1: PoW
    cred1 = Credential("CRED-POW-01", "Uni", "Bob", "MBA", "2026-01-01", {})
    tx1 = Transaction("ISSUE", w.public_key_hex, asdict(cred1))
    tx1.sign(w)
    n1.submit_transaction(tx1)
    _wait(net)
    n1.mine_pending(difficulty=2)
    _wait(net)

    # Block 2: PoS
    cred2 = Credential("CRED-POS-02", "Uni", "Carol", "MSc", "2026-02-01", {})
    tx2 = Transaction("ISSUE", w.public_key_hex, asdict(cred2))
    tx2.sign(w)
    n1.submit_transaction(tx2)
    _wait(net)
    val = net.pos_registry.select_validator(height=2, seed=42, previous_hash=n1.blockchain.get_latest_block().compute_hash())
    n1.forge_pos_pending(validator=val, seed=42)
    _wait(net)

    ok, bad_idx, reason = n1.blockchain.is_chain_valid(pos_registry=net.pos_registry)
    assert ok is True
    assert bad_idx is None
    assert len(n1.blockchain.chain) == 3

    for n in net.nodes.values():
        n._running = False


def test_verify_credential_minted_via_pos():
    """Quy trình 12 bước verify_credential xác minh thành công cho credential đóng gói bằng PoS."""
    net = Network()
    n1 = net.create_node("Node-1", "127.0.0.1", 5001)

    w = generate_wallet()
    claims = {"role": "Senior Dev", "years": "5", "performance": "A"}
    root, salts, proofs, _, _ = build_claims_merkle_tree(claims)

    cred = Credential("CRED-POS-VERIFY", "ĐH-A", "Dave", "Software Engineer", "2026-03-01", claims, root)
    tx = Transaction("ISSUE", w.public_key_hex, cred.to_onchain_payload())
    tx.sign(w)

    n1.submit_transaction(tx)
    _wait(net)

    val = net.pos_registry.select_validator(height=1, seed=42, previous_hash=n1.blockchain.get_latest_block().compute_hash())
    n1.forge_pos_pending(validator=val, seed=42)
    _wait(net)

    steps, status, info = n1.blockchain.verify_credential("CRED-POS-VERIFY", pos_registry=net.pos_registry)
    assert status == "VERIFIED"
    assert all(ok for _, ok, _ in steps), f"Some step failed: {steps}"

    # Bước 10 phải xác nhận PoS hợp lệ
    step10 = steps[9]
    assert "PoS" in step10[0]
    assert step10[1] is True

    for n in net.nodes.values():
        n._running = False


def test_flexible_data_presets_merkle_proof():
    """Kiểm tra tạo Salted Merkle Tree và Selective Disclosure cho nhiều miền hồ sơ khác nhau."""
    domains = [
        {"position": "Backend Architect", "years": "7", "status": "Permanent"},
        {"certificate": "AWS Solutions Architect", "score": "950", "level": "Professional"},
        {"blood_type": "O+", "vaccine_doses": "3", "allergy": "None"},
    ]

    for data in domains:
        root, salts, proofs, _, _ = build_claims_merkle_tree(data)
        assert len(root) == 64

        # Chọn 1 claim bất kỳ và verify Proof of Inclusion
        first_key = list(data.keys())[0]
        claim_val = data[first_key]
        salt = salts[first_key]
        proof = proofs[first_key]

        ok = verify_claim_inclusion_proof(first_key, claim_val, salt, proof, root)
        assert ok is True


