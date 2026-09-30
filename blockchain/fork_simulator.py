"""Module fork_simulator — Mô phỏng phân nhánh (Fork) và Tái tổ chức chuỗi (Reorg).

Mục đích:
- Mô phỏng 2 miner tạo 2 block cùng height gần như đồng thời trên cùng 1 block cha.
- Phân vùng mạng mô phỏng: một số node nhận nhánh A trước, số khác nhận nhánh B trước.
- Cả hai nhánh được lưu trữ trong block_pool / side_branches của các node.
- Lựa chọn chuỗi theo quy tắc Most-Work Chain: chuỗi có tổng công việc PoW (sum 16^difficulty)
  lớn nhất sẽ được chọn làm canonical chain, không chỉ đơn thuần là chuỗi dài hơn.
- Khi một nhánh nhận thêm block hoặc có tổng PoW vượt trội: các node tự động thực hiện
  Chain Reorganization (Reorg), các giao dịch ở nhánh bị bỏ rơi được hoàn trả lại Mempool.
- Cung cấp hàm sinh mã Graphviz DOT trực quan hóa cây phân nhánh.
"""

import time
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.node import Network, Message
from blockchain.blockchain import calculate_chain_work, block_work


def create_fork_blocks(
    base_block: Block,
    txs_a: list,
    txs_b: list,
    diff_a: int = 2,
    diff_b: int = 2,
) -> tuple[Block, Block]:
    """Tạo 2 block cạnh tranh nhau cùng height trên cùng 1 base_block.

    Returns:
        (block_a, block_b) đã được đào (PoW) hợp lệ.
    """
    height = base_block.height + 1
    prev_hash = base_block.compute_hash()

    block_a = Block(
        transactions=list(txs_a),
        height=height,
        previous_hash=prev_hash,
        difficulty=diff_a,
    )
    mine_block(block_a)

    block_b = Block(
        transactions=list(txs_b),
        height=height,
        previous_hash=prev_hash,
        difficulty=diff_b,
    )
    mine_block(block_b)

    return block_a, block_b


def deliver_block_to_nodes(
    network: Network,
    block: Block,
    target_node_ids: list[str],
    sender_id: str = "Miner",
) -> None:
    """Gửi block trực tiếp vào inbox của các node chỉ định."""
    msg = Message("BLOCK", sender_id, block)
    for nid in target_node_ids:
        if nid in network.nodes and network.nodes[nid].status == "ONLINE":
            network.nodes[nid].inbox.put(msg)


def generate_fork_dot(node) -> str:
    """Sinh chuỗi Graphviz DOT trực quan hóa các nhánh blockchain của một node.

    Tô màu:
    - Xanh lá (#90EE90): Block thuộc chuỗi chính (Active / Canonical Chain).
    - Cam vàng (#FFCC80): Block thuộc nhánh phụ (Side Branch / Orphaned).
    - Vàng (#FFD700): Genesis Block.
    """
    bc = node.blockchain
    active_hashes = set(b.compute_hash() for b in bc.chain)

    # Thu thập tất cả các block (chuỗi chính + tất cả nhánh phụ)
    all_blocks_dict = dict(bc.block_pool)
    for b in bc.chain:
        all_blocks_dict[b.compute_hash()] = b
    for branch in bc.side_branches:
        for b in branch:
            all_blocks_dict[b.compute_hash()] = b

    lines = [
        "digraph ForkTree {",
        "  rankdir=LR;",
        '  node [shape=box, fontname="Courier", fontsize=10, style=filled];',
        "  edge [arrowsize=0.7];",
    ]

    for bh, b in all_blocks_dict.items():
        is_genesis = b.height == 0
        is_active = bh in active_hashes
        short_hash = bh[:8] + "…"
        work = block_work(b.header.difficulty) if not is_genesis else 0

        label_parts = [
            f"Block {b.height}",
            f"{short_hash}",
            f"diff={b.header.difficulty} (work={work:,})",
            f"{b.transaction_count} TXs",
        ]

        if is_genesis:
            color = "#FFD700"
            label_parts[0] = "Genesis Block"
        elif is_active:
            color = "#90EE90"
            label_parts.append("[ACTIVE CHAIN]")
        else:
            color = "#FFB347"
            label_parts.append("[SIDE / ORPHAN]")

        full_label = "\\n".join(label_parts)
        nid = f"b_{bh[:12]}"
        lines.append(f'  {nid} [label="{full_label}", fillcolor="{color}"];')

    # Vẽ các cạnh kết nối (prev_hash -> block)
    for bh, b in all_blocks_dict.items():
        if b.height > 0 and b.header.previous_hash in all_blocks_dict:
            parent_id = f"b_{b.header.previous_hash[:12]}"
            child_id = f"b_{bh[:12]}"
            is_active_edge = (bh in active_hashes and b.header.previous_hash in active_hashes)
            edge_style = 'color="#2E7D32", penwidth=2.0' if is_active_edge else 'color="#E65100", stroke="dashed"'
            lines.append(f"  {parent_id} -> {child_id} [{edge_style}];")

    lines.append("}")
    return "\n".join(lines)

