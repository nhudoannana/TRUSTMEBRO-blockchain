"""Trang Merkle Tree — trực quan hoá cây hash, tamper demo, Merkle Proof.

Mục đích: giúp sinh viên thấy cách Merkle Tree phát hiện giả mạo
và cho phép xác minh giao dịch chỉ với O(log n) hash.
"""

import math
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state
from blockchain.hash import sha256_hex
from blockchain.merkle import (
    build_merkle_tree,
    calculate_merkle_root,
    generate_merkle_proof,
    verify_merkle_proof,
)

init_state()



st.header("5️⃣ Merkle Tree")


# ── Helper: vẽ sơ đồ cây bằng Graphviz DOT ──

def _merkle_dot(tree, highlight_indices=None, leaf_labels=None):
    """Tạo chuỗi DOT cho Graphviz, tô màu node bị thay đổi."""
    highlight = highlight_indices or set()
    lines = [
        "digraph MerkleTree {",
        "  rankdir=TB;",
        '  node [shape=box, fontname="Courier", fontsize=10, style=filled];',
        "  edge [arrowsize=0.7];",
    ]

    # Tạo node
    for lvl, level in enumerate(tree):
        for pos, h in enumerate(level):
            nid = f"n{lvl}_{pos}"
            short = h[:8] + "…"
            is_highlight = (lvl, pos) in highlight

            if lvl == len(tree) - 1:
                color = "#FF6B6B" if is_highlight else "#FFD700"
                lines.append(f'  {nid} [label="Root\\n{short}", fillcolor="{color}"];')
            elif lvl == 0:
                lbl = leaf_labels[pos] if leaf_labels and pos < len(leaf_labels) else f"TX{pos}"
                color = "#FF6B6B" if is_highlight else "#90EE90"
                lines.append(f'  {nid} [label="{lbl}\\n{short}", fillcolor="{color}"];')
            else:
                color = "#FF6B6B" if is_highlight else "#E8F4FD"
                lines.append(f'  {nid} [label="{short}", fillcolor="{color}"];')

    # Tạo cạnh (parent → children)
    for lvl in range(1, len(tree)):
        for p_pos in range(len(tree[lvl])):
            pid = f"n{lvl}_{p_pos}"
            child_level = tree[lvl - 1]
            left_idx = p_pos * 2
            right_idx = p_pos * 2 + 1

            lines.append(f"  {pid} -> n{lvl - 1}_{left_idx};")

            if right_idx < len(child_level):
                lines.append(f"  {pid} -> n{lvl - 1}_{right_idx};")
            else:
                # Nhân đôi lá cuối — vẽ nét đứt quay về chính nó
                lines.append(
                    f"  {pid} -> n{lvl - 1}_{left_idx} "
                    f'[style=dashed, label="dup", color=gray];'
                )

    lines.append("}")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# PHẦN 1: Xây Merkle Tree
# ══════════════════════════════════════════════
st.subheader("🔹 Xây dựng Merkle Tree")

# Nguồn dữ liệu: nhập tay hoặc lấy từ mempool
source = st.radio(
    "Nguồn dữ liệu:",
    ["Nhập tay", "Lấy từ Mempool (nếu có)"],
    horizontal=True, key="mk_source",
)

if source == "Nhập tay":
    default_txs = "tx_demo001_bsc\ntx_demo002_mba\ntx_demo003_phd\ntx_demo004_cert"
    raw = st.text_area(
        "Nhập dữ liệu giao dịch (mỗi dòng một TX):",
        value=default_txs, height=120, key="mk_raw",
    )
    tx_labels = [line.strip() for line in raw.strip().split("\n") if line.strip()]
    leaf_hashes = [sha256_hex(lbl) for lbl in tx_labels]
else:
    pending = st.session_state.get("transactions", [])
    if not pending:
        st.warning("Chưa có transaction. Vào trang **Transaction** tạo trước hoặc chọn Nhập tay.")
        st.stop()
    tx_labels = [t.get("payload", {}).get("credential_id", t["tx_id"][:12]) for t in pending]
    leaf_hashes = [t["tx_id"] for t in pending]

if len(leaf_hashes) < 2:
    st.warning("Cần ít nhất 2 transaction để xây Merkle Tree.")
    st.stop()

# Xây tree và hiển thị
tree = build_merkle_tree(leaf_hashes)
root = tree[-1][0]

st.markdown(f"**Merkle Root:** `{root}`")
st.caption(f"Số lá: {len(leaf_hashes)} — Số tầng: {len(tree)}")

# Sơ đồ Graphviz
try:
    st.graphviz_chart(_merkle_dot(tree, leaf_labels=tx_labels))
except Exception:
    pass

# Bảng các tầng
with st.expander("📋 Xem hash từng tầng"):
    for lvl_idx, level in enumerate(tree):
        if lvl_idx == len(tree) - 1:
            label = "Root"
        elif lvl_idx == 0:
            label = "Lá (Leaves)"
        else:
            label = f"Tầng {lvl_idx}"
        st.markdown(f"**{label}** ({len(level)} node)")
        for pos, h in enumerate(level):
            st.code(f"[{pos}] {h}", language="text")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Tamper Demo
# ══════════════════════════════════════════════
st.subheader("🔹 Tamper Demo — Sửa TX và xem Root thay đổi")

tamper_idx = st.selectbox(
    "Chọn TX để sửa:",
    range(len(tx_labels)),
    format_func=lambda i: f"TX{i}: {tx_labels[i]}",
    key="tamper_idx",
)

if st.button("🔴 Giả mạo TX được chọn", key="btn_tamper_mk"):
    # Tạo hash giả
    tampered_hashes = list(leaf_hashes)
    tampered_hashes[tamper_idx] = sha256_hex("TAMPERED_DATA")

    tree_tampered = build_merkle_tree(tampered_hashes)
    root_tampered = tree_tampered[-1][0]

    # Tìm các node bị ảnh hưởng
    changed = set()
    for lvl in range(len(tree)):
        for pos in range(min(len(tree[lvl]), len(tree_tampered[lvl]))):
            if tree[lvl][pos] != tree_tampered[lvl][pos]:
                changed.add((lvl, pos))

    col_orig, col_tamp = st.columns(2)
    with col_orig:
        st.markdown("**🟢 Cây gốc**")
        st.markdown(f"Root: `{root[:24]}…`")
        try:
            st.graphviz_chart(_merkle_dot(tree, leaf_labels=tx_labels))
        except Exception:
            pass

    with col_tamp:
        st.markdown("**🔴 Cây bị sửa**")
        st.markdown(f"Root: `{root_tampered[:24]}…`")
        tamper_labels = list(tx_labels)
        tamper_labels[tamper_idx] = f"❌{tx_labels[tamper_idx]}"
        try:
            st.graphviz_chart(
                _merkle_dot(tree_tampered, highlight_indices=changed, leaf_labels=tamper_labels)
            )
        except Exception:
            pass

    st.info(
        f"📊 Sửa 1 lá → **{len(changed)} node** thay đổi (toàn bộ đường từ lá lên root). "
        f"Block Header lưu Root, nên phát hiện ngay."
    )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Merkle Proof
# ══════════════════════════════════════════════
st.subheader("🔹 Merkle Proof — Xác minh giao dịch")
st.caption("Chọn 1 TX, sinh proof (danh sách hash anh em), verify chỉ với Root.")

proof_idx = st.selectbox(
    "Chọn TX cần chứng minh:",
    range(len(tx_labels)),
    format_func=lambda i: f"TX{i}: {tx_labels[i]}",
    key="proof_idx",
)

if st.button("🔍 Sinh Merkle Proof", key="btn_proof"):
    proof = generate_merkle_proof(leaf_hashes, proof_idx)
    leaf = leaf_hashes[proof_idx]

    # Hiển thị proof
    st.markdown(f"**Leaf hash:** `{leaf[:32]}…`")
    st.markdown(f"**Root:** `{root[:32]}…`")
    st.markdown(f"**Proof gồm {len(proof)} hash anh em:**")

    for step, (sibling, pos) in enumerate(proof):
        arrow = "⬅️" if pos == "left" else "➡️"
        st.code(f"Bước {step}: {arrow} {pos:>5}  {sibling[:24]}…", language="text")

    # Verify
    ok = verify_merkle_proof(leaf, proof, root)
    if ok:
        st.success("✅ **VALID** — Giao dịch thuộc cây với Merkle Root này.")
    else:
        st.error("❌ **INVALID** — Proof không khớp Root.")

    # So sánh hiệu quả
    total_txs = len(leaf_hashes)
    proof_size = len(proof)
    st.markdown(
        f"📊 **Hiệu quả:** Chỉ cần **{proof_size} hash** "
        f"(thay vì {total_txs} giao dịch) "
        f"= O(log₂ {total_txs}) = O({math.ceil(math.log2(max(total_txs, 2)))})"
    )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. Vì sao Block Header chỉ lưu Merkle Root mà không lưu hết giao dịch?**

        - Root (32 byte) đại diện cho toàn bộ danh sách giao dịch.
        - Nếu bất kỳ TX nào bị sửa → Root thay đổi → phát hiện ngay.
        - Header nhỏ gọn giúp đồng bộ nhanh giữa các node,
          đặc biệt quan trọng khi block chứa hàng nghìn giao dịch.

        ---

        **2. Merkle Proof verify nhanh hơn thế nào?**

        | Phương pháp | Dữ liệu cần gửi | Thao tác hash |
        |---|---|---|
        | Gửi toàn bộ TX | n giao dịch | n lần hash |
        | Merkle Proof | log₂(n) hash | log₂(n) lần hash |

        Với 1.000.000 giao dịch: chỉ cần **20 hash** thay vì 1 triệu.
        Đây là lý do Bitcoin SPV (Simplified Payment Verification) hoạt động
        trên thiết bị di động mà không cần tải toàn bộ blockchain.

        ---

        **3. Cây Merkle cho Claims (Selective Disclosure) khác gì Merkle Tree của Block?**

        - **Merkle Tree của Block:** Gom các Transaction thành Merkle Root lưu trong Block Header.
        - **Merkle Tree cho Claims (trong Credential):** Mỗi lá là một claim được băm kèm **Salt ngẫu nhiên 128-bit**:
          `leaf_hash = SHA256(JSON([claim_name, claim_value, salt]))`.
        - **Vì sao cần Salt?** Ngăn chặn tấn công từ điển / dò băm đối với các claim có ít khả năng như `Grade A`.
        - Chỉ có `claims_root` nằm on-chain. Holder gửi cho Verifier một claim cùng salt và proof. Verifier đối soát được mà không thấy các claim khác.
        - **Thuật ngữ chuẩn:** Đây là **Proof of Inclusion**, KHÔNG PHẢI Zero-Knowledge Proof (ZKP).
        """
    )

