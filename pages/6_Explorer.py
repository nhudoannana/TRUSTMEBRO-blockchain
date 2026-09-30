"""Trang Blockchain Explorer — hiển thị chuỗi block, demo tamper.

Mục đích: cho sinh viên thấy cấu trúc chuỗi block, liên kết hash,
và hai kịch bản tấn công: sửa 1 block vs sửa rồi tính lại toàn bộ.
"""

import copy
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_pos_registry
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.block import Block
from blockchain.blockchain import Blockchain, verify_pos_signature
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import mine_block, is_valid_pow

init_state()



st.header("6️⃣ Blockchain Explorer")
st.caption('Chuỗi mẫu độc lập để thử sửa dữ liệu. Xem chuỗi của các node đang chạy ở trang Network.')


# ── Helper: tạo demo blockchain (đã mine) ──

def _build_demo_blockchain():
    """Tạo blockchain mẫu với 4 block (+ genesis = 5 block), difficulty=3."""
    wallet = generate_wallet()
    bc = Blockchain()

    samples = [
        ("CRED-001", "Người học DEMO-001",  "BSc Computer Science"),
        ("CRED-002", "Người học DEMO-002",  "MBA Business"),
        ("CRED-003", "Người học DEMO-003",  "MSc Data Science"),
        ("CRED-004", "Người học DEMO-004",  "PhD Mathematics"),
    ]

    for cred_id, holder, title in samples:
        cred = Credential(cred_id, "Trường Đại học DEMO-A", holder, title, "2026-06-01", {})
        tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
        tx.sign(wallet)

        prev_hash = bc.get_latest_block().compute_hash()
        block = Block(
            transactions=[tx], height=len(bc.chain),
            previous_hash=prev_hash, difficulty=3,
        )
        mine_block(block)
        bc.add_block(block)

    return bc


# ── Helper: hiển thị 1 block ──

def _show_block(block, validation_status=None):
    """Hiển thị thông tin chi tiết của 1 block trong expander."""
    block_hash = block.compute_hash()
    status_icon = "✅" if validation_status is None or validation_status else "❌"

    label = f"{status_icon} Block {block.height} — {block_hash[:16]}…"
    if block.height == 0:
        label = f"{status_icon} Block 0 (Genesis)"

    with st.expander(label, expanded=(validation_status is False)):
        col1, col2 = st.columns(2)
        is_pos = block.header.consensus_type == "PoS"
        with col1:
            st.markdown(f"**Height:** {block.height}")
            st.markdown(f"**Timestamp:** `{block.header.timestamp}`")
            st.markdown(f"**Consensus:** {'🪙 Proof of Stake' if is_pos else '⛏️ Proof of Work'}")
            if is_pos:
                st.markdown(f"**Validator:** `{block.header.validator_address[:16]}…`")
            else:
                st.markdown(f"**Difficulty:** {block.header.difficulty}")
                st.markdown(f"**Nonce:** {block.header.nonce:,}")
        with col2:
            st.markdown(f"**Version:** {block.header.version}")
            st.markdown(f"**Transactions:** {block.transaction_count}")
            if is_pos:
                sig_ok, _ = verify_pos_signature(block, get_pos_registry())
                st.markdown(f"**Chữ ký PoS:** {'✅ Hợp lệ' if sig_ok else '❌ Không hợp lệ'}")
            else:
                pow_ok = is_valid_pow(block)
                st.markdown(f"**PoW valid:** {'✅' if pow_ok else '❌'}")

        st.markdown(f"**Hash:** `{block_hash}`")
        st.markdown(f"**Previous Hash:** `{block.header.previous_hash}`")
        st.markdown(f"**Merkle Root:** `{block.header.merkle_root}`")

        if block.transactions:
            st.markdown("**Giao dịch:**")
            for tx in block.transactions:
                cred_id = tx.payload.get("credential_id", "—")
                holder = tx.payload.get("holder_name", "—")
                st.caption(f"  📄 {tx.tx_type} | {cred_id} → {holder} | tx_id: `{tx.tx_id[:24]}…`")

        if validation_status is False:
            st.error("❌ Block này INVALID — xem lý do bên dưới.")


# ── Helper: validate từng block ──

def _validate_per_block(bc):
    """Trả về dict {index: (ok, reason)} cho từng block."""
    results = {}
    for i in range(len(bc.chain)):
        block = bc.chain[i]

        # Merkle root
        tx_hashes = [tx.tx_id for tx in block.transactions]
        expected_root = calculate_merkle_root(tx_hashes)
        if block.header.merkle_root != expected_root:
            results[i] = (False, "merkle_root không khớp danh sách giao dịch")
            continue

        if i > 0:
            # Previous hash
            expected_prev = bc.chain[i - 1].compute_hash()
            if block.header.previous_hash != expected_prev:
                results[i] = (False, f"previous_hash không khớp hash Block {i - 1}")
                continue

            # Kiểm tra cơ chế đồng thuận
            if block.header.consensus_type == "PoS":
                sig_ok, sig_reason = verify_pos_signature(block, get_pos_registry())
                if not sig_ok:
                    results[i] = (False, sig_reason)
                    continue
            else:
                # Proof of Work
                if not is_valid_pow(block):
                    block_hash = block.compute_hash()
                    results[i] = (
                        False,
                        f"PoW không hợp lệ (hash={block_hash[:12]}…, "
                        f"cần {block.header.difficulty} số '0' đầu)",
                    )
                    continue

        results[i] = (True, "OK")

    return results


# ══════════════════════════════════════════════
# Khởi tạo demo blockchain
# ══════════════════════════════════════════════
if st.button("🔄 Tạo / Reset Demo Blockchain", key="btn_reset_bc"):
    st.session_state.demo_blockchain = _build_demo_blockchain()

if "demo_blockchain" not in st.session_state:
    st.session_state.demo_blockchain = _build_demo_blockchain()

bc = st.session_state.demo_blockchain

# ══════════════════════════════════════════════
# PHẦN 1: Hiển thị chuỗi block
# ══════════════════════════════════════════════
st.subheader("🔹 Chuỗi Block")

ok, fail_idx, reason = bc.is_chain_valid(pos_registry=get_pos_registry())
if ok:
    st.success(f"✅ Chain hợp lệ — {len(bc.chain)} block")
else:
    st.error(f"❌ Chain INVALID tại Block {fail_idx}: {reason}")

validations = _validate_per_block(bc)

for i, block in enumerate(bc.chain):
    block_ok = validations[i][0]
    _show_block(block, validation_status=block_ok)

# Bảng tóm tắt
with st.expander("📊 Bảng liên kết hash"):
    rows = []
    for i, block in enumerate(bc.chain):
        rows.append({
            "Block": i,
            "Hash (đầu)": block.compute_hash()[:16],
            "Prev Hash (đầu)": block.header.previous_hash[:16],
            "Link OK?": "—" if i == 0 else (
                "✅" if block.header.previous_hash == bc.chain[i - 1].compute_hash() else "❌"
            ),
            "PoW OK?": "—" if i == 0 else ("✅" if is_valid_pow(block) else "❌"),
            "Nonce": f"{block.header.nonce:,}",
        })
    st.table(rows)

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Tamper Block 2
# ══════════════════════════════════════════════
st.subheader("🔹 Demo: Tamper Block 2")
st.caption("Sửa giao dịch trong Block 2, cập nhật merkle_root → hash Block 2 đổi → chuỗi gãy.")

if len(bc.chain) < 4:
    st.warning("Cần ít nhất 4 block. Bấm Reset.")
else:
    if st.button("🔴 Tamper Block 2", key="btn_tamper_b2"):
        tampered_bc = copy.deepcopy(bc)
        block2 = tampered_bc.chain[2]
        old_hash = block2.compute_hash()

        if block2.transactions:
            block2.transactions[0].payload["holder_name"] = "😈 HACKER"
            block2.transactions[0].payload["title"] = "Fake Degree"
            new_hashes = [tx.tx_id for tx in block2.transactions]
            block2.header.merkle_root = calculate_merkle_root(new_hashes)

        new_hash = block2.compute_hash()

        st.markdown(f"**Block 2 hash cũ:** `{old_hash[:32]}…`")
        st.markdown(f"**Block 2 hash mới:** `{new_hash[:32]}…`")
        st.warning("⚠️ Hash Block 2 thay đổi vì merkle_root trong header đổi!")

        st.markdown("**Kết quả kiểm tra từng block:**")
        t_validations = _validate_per_block(tampered_bc)
        for i in range(len(tampered_bc.chain)):
            v_ok, v_reason = t_validations[i]
            if v_ok:
                st.success(f"  Block {i}: ✅ OK")
            else:
                st.error(f"  Block {i}: ❌ {v_reason}")

        t_ok, t_idx, t_reason = tampered_bc.is_chain_valid(pos_registry=get_pos_registry())
        st.markdown("---")
        st.error(f"**is_chain_valid()** → `(False, {t_idx}, \"{t_reason}\")`")
        st.info(
            "💡 Sửa 1 block → hash block đổi → block tiếp theo phát hiện "
            "previous_hash không khớp. Chuỗi bị gãy tại điểm nối."
        )

    st.divider()

    # ══════════════════════════════════════════════
    # PHẦN 3: Tamper & Recompute All (giờ bị PoW chặn)
    # ══════════════════════════════════════════════
    st.subheader("🔹 Demo: Tamper & Recompute All")
    st.caption(
        "Sửa Block 2, tính lại hash toàn bộ block sau. "
        "Ở Bước 7 (chưa có PoW) thì qua được — giờ bị **Proof of Work chặn**!"
    )

    if st.button("🔴 Tamper & Recompute All", key="btn_tamper_recompute"):
        recomp_bc = copy.deepcopy(bc)
        block2 = recomp_bc.chain[2]
        difficulty = block2.header.difficulty

        if block2.transactions:
            block2.transactions[0].payload["holder_name"] = "😈 HACKER"
            block2.transactions[0].payload["title"] = "Fake Degree"

        # Tính lại merkle_root cho Block 2
        new_root = calculate_merkle_root(
            [tx.tx_id for tx in block2.transactions]
        )
        block2.header.merkle_root = new_root

        # Tính lại previous_hash cho các block sau (nhưng KHÔNG mine lại)
        for i in range(3, len(recomp_bc.chain)):
            recomp_bc.chain[i].header.previous_hash = recomp_bc.chain[i - 1].compute_hash()

        # Validate — giờ PoW sẽ phát hiện
        r_ok, r_idx, r_reason = recomp_bc.is_chain_valid(pos_registry=get_pos_registry())

        if r_ok:
            st.success(f"✅ is_chain_valid() → `(True, None, \"Chain hợp lệ\")`")
        else:
            st.error(f"❌ is_chain_valid() → `(False, {r_idx}, \"{r_reason}\")`")

        st.markdown("**Kết quả từng block:**")
        r_validations = _validate_per_block(recomp_bc)
        for i in range(len(recomp_bc.chain)):
            v_ok, v_reason = r_validations[i]
            if v_ok:
                st.success(f"  Block {i}: ✅ OK")
            else:
                st.error(f"  Block {i}: ❌ {v_reason}")

        # Ước tính thời gian mine lại
        num_blocks_remine = len(recomp_bc.chain) - 2  # từ block 2 đến cuối
        expected_attempts = 16 ** difficulty
        st.warning(
            f"⛏️ **Để vượt qua PoW**, kẻ tấn công phải mine lại "
            f"**{num_blocks_remine} block** (difficulty={difficulty}). "
            f"Mỗi block cần ~{expected_attempts:,} lần thử. "
            f"Tổng: ~{expected_attempts * num_blocks_remine:,} lần hash. "
            f"Với Bitcoin (difficulty ~70+ bit): hàng **tỷ năm** trên 1 CPU."
        )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. Vì sao genesis block cần previous_hash = "000…0"?**

        Genesis là block đầu tiên, không có block trước. Giá trị "000…0"
        là quy ước cố định mà tất cả node đều biết, đảm bảo mọi node
        khởi đầu từ cùng một điểm.

        ---

        **2. Sửa 1 block thì phải sửa bao nhiêu block?**

        Tất cả block phía sau — vì mỗi block chứa hash của block trước.
        Sửa Block k → hash Block k đổi → previous_hash Block k+1 sai →
        phải sửa Block k+1 → … → sửa đến block cuối.

        ---

        **3. PoW chặn tấn công "Recompute All" như thế nào?**

        - Không có PoW: tính lại hash toàn bộ chuỗi chỉ mất vài mili-giây.
        - Có PoW: mỗi block phải mine lại (~16^difficulty lần thử).
          Kẻ tấn công phải mine **nhanh hơn toàn bộ mạng** để đuổi kịp
          chuỗi hợp lệ — cần > 50% tổng sức mạnh tính toán (51% attack).
        """
    )
