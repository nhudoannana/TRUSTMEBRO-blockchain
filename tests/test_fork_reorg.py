"""Tests cho Fork, Most-Work Chain (sum 16^difficulty) và Chain Reorganization (Reorg).

Kiểm tra:
- Tính toán tổng công việc PoW chính xác theo công thức sum(16^difficulty).
- Chuỗi có tổng PoW cao hơn chiến thắng chuỗi dài hơn nhưng độ khó thấp.
- Node lưu trữ cả hai nhánh khi xảy ra phân nhánh ở cùng height.
- Khi nhánh phụ có tổng PoW lớn hơn, node tự động thực hiện Chain Reorganization.
- Các giao dịch ở nhánh bị bỏ rơi được hoàn trả lại chính xác vào Mempool.
"""

import time
from dataclasses import asdict
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.wallet import generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network, Message
from blockchain.blockchain import Blockchain, calculate_chain_work, block_work
from blockchain.fork_simulator import create_fork_blocks, deliver_block_to_nodes


def _wait(net, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(n.inbox.empty() for n in net.nodes.values()):
            time.sleep(0.15)
            return True
        time.sleep(0.05)
    return False


def _make_tx(wallet, cred_id, holder_name="Student"):
    cred = Credential(cred_id, "University", holder_name, "BSc", "2026-01-01", {})
    tx = Transaction("ISSUE", wallet.public_key_hex, cred.to_onchain_payload())
    tx.sign(wallet)
    return tx


def test_pow_work_calculation():
    """Kiểm tra công thức 16^difficulty và tính tổng công việc của chuỗi."""
    assert block_work(1) == 16
    assert block_work(2) == 256
    assert block_work(3) == 4096
    assert block_work(4) == 65536

    bc = Blockchain()
    assert bc.total_work() == 0  # Genesis work = 0

    # Giả lập thêm 2 block difficulty 2
    b1 = Block([], height=1, previous_hash=bc.get_latest_block().compute_hash(), difficulty=2)
    b2 = Block([], height=2, previous_hash=b1.compute_hash(), difficulty=2)
    chain = [bc.chain[0], b1, b2]

    assert calculate_chain_work(chain) == 256 + 256 == 512


def test_higher_pow_work_wins_over_longer_chain():
    """Chuỗi ngắn nhưng độ khó cao (PoW lớn hơn) phải thắng chuỗi dài độ khó thấp.

    Ví dụ:
    - Chuỗi A: 3 block difficulty=2 -> work = 3 * 256 = 768
    - Chuỗi B: 1 block difficulty=3 -> work = 1 * 4096 = 4096
    Theo Most-Work Chain rule: Chuỗi B thắng!
    """
    bc = Blockchain()
    gen = bc.chain[0]

    # Chuỗi A: 3 blocks diff=2
    b1_a = Block([], height=1, previous_hash=gen.compute_hash(), difficulty=2)
    b2_a = Block([], height=2, previous_hash=b1_a.compute_hash(), difficulty=2)
    b3_a = Block([], height=3, previous_hash=b2_a.compute_hash(), difficulty=2)
    chain_a = [gen, b1_a, b2_a, b3_a]

    # Chuỗi B: 1 block diff=3
    b1_b = Block([], height=1, previous_hash=gen.compute_hash(), difficulty=3)
    chain_b = [gen, b1_b]

    work_a = calculate_chain_work(chain_a)
    work_b = calculate_chain_work(chain_b)

    assert len(chain_a) > len(chain_b)  # Chuỗi A dài hơn (4 vs 2)
    assert work_b > work_a              # Nhưng Chuỗi B có tổng PoW lớn hơn (4096 > 768)


def test_node_stores_both_branches_on_fork():
    """2 miner tạo 2 block cùng height -> Node nhận cả 2 và lưu trữ cả hai nhánh."""
    net = Network()
    node = net.create_node("Node-1", "127.0.0.1", 5001)
    wallet = generate_wallet()

    tx_a = _make_tx(wallet, "CRED-FORK-A", "Alice")
    tx_b = _make_tx(wallet, "CRED-FORK-B", "Bob")

    gen_block = node.blockchain.chain[0]
    block_a, block_b = create_fork_blocks(gen_block, [tx_a], [tx_b], diff_a=2, diff_b=2)

    # Gửi Block A trước -> Node chấp nhận làm chuỗi chính
    deliver_block_to_nodes(net, block_a, ["Node-1"])
    _wait(net)

    assert node.height == 1
    assert node.blockchain.get_latest_block().compute_hash() == block_a.compute_hash()
    assert len(node.blockchain.side_branches) == 0

    # Gửi Block B (cùng height=1, cùng parent=genesis)
    deliver_block_to_nodes(net, block_b, ["Node-1"])
    _wait(net)

    # Node vẫn giữ Block A làm chuỗi chính (do work bằng nhau 256 == 256),
    # nhưng ĐÃ LƯU Block B vào side_branches!
    assert node.height == 1
    assert node.blockchain.get_latest_block().compute_hash() == block_a.compute_hash()
    assert len(node.blockchain.side_branches) == 1
    assert node.blockchain.side_branches[0][-1].compute_hash() == block_b.compute_hash()

    for n in net.nodes.values():
        n._running = False


def test_chain_reorg_and_mempool_rollback():
    """Khi nhánh B nhận thêm block (PoW lớn hơn) -> Node-1 reorg sang nhánh B và hoàn trả TX của A về Mempool."""
    net = Network()
    node1 = net.create_node("Node-1", "127.0.0.1", 5001)
    wallet = generate_wallet()

    tx_alice = _make_tx(wallet, "CRED-ALICE", "Alice")
    tx_bob = _make_tx(wallet, "CRED-BOB", "Bob")
    tx_carol = _make_tx(wallet, "CRED-CAROL", "Carol")

    # Giả sử Node-1 ban đầu có tx_alice trong mempool
    node1.mempool.add_transaction(tx_alice, node1.blockchain)
    assert len(node1.mempool.get_transactions()) == 1

    gen = node1.blockchain.chain[0]
    # Tạo Block 1A (chứa tx_alice) và Block 1B (chứa tx_bob)
    block_1a, block_1b = create_fork_blocks(gen, [tx_alice], [tx_bob], diff_a=2, diff_b=2)

    # Node-1 nhận Block 1A -> tx_alice bị xoá khỏi mempool
    deliver_block_to_nodes(net, block_1a, ["Node-1"])
    _wait(net)
    assert len(node1.mempool.get_transactions()) == 0
    assert node1.blockchain.get_latest_block().compute_hash() == block_1a.compute_hash()

    # Node-1 nhận Block 1B -> lưu vào side branch
    deliver_block_to_nodes(net, block_1b, ["Node-1"])
    _wait(net)
    assert len(node1.blockchain.side_branches) == 1

    # Bây giờ nhánh B nhận thêm Block 2B (chứa tx_carol)
    block_2b = Block(
        transactions=[tx_carol],
        height=2,
        previous_hash=block_1b.compute_hash(),
        difficulty=2,
    )
    mine_block(block_2b)

    # Gửi Block 2B tới Node-1 -> Nhánh B có work = 256 + 256 = 512 > Nhánh A (256)
    deliver_block_to_nodes(net, block_2b, ["Node-1"])
    _wait(net)

    # 1. Node-1 phải REORG sang Nhánh B (height = 2)
    assert node1.height == 2
    assert node1.blockchain.get_latest_block().compute_hash() == block_2b.compute_hash()

    # 2. tx_alice (ở Block 1A bị bỏ rơi) phải được HOÀN TRẢ VỀ MEMPOOL!
    mempool_tx_ids = [tx.tx_id for tx in node1.mempool.get_transactions()]
    assert tx_alice.tx_id in mempool_tx_ids, "tx_alice was not returned to mempool after reorg!"

    # 3. tx_bob và tx_carol (ở nhánh mới) không nằm trong mempool
    assert tx_bob.tx_id not in mempool_tx_ids
    assert tx_carol.tx_id not in mempool_tx_ids

    # 4. Nhánh cũ 1A được chuyển vào side_branches
    assert len(node1.blockchain.side_branches) >= 1

    for n in net.nodes.values():
        n._running = False

