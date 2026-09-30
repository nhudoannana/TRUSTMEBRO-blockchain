"""Trang Mining Flow — chạy trọn luồng end-to-end.

Create TX → Sign → Broadcast → Mempool → Mine → Block →
Validate → Consensus → Chain updated.
"""

import time
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network

init_state()



st.header("9️⃣ Block Creation & Consensus Flow (PoS & PoW)")


# ── Network (cache_resource, chia sẻ giữa các trang) ──

network = get_network()


# ── Tự động seed wallet các trường Đại học Consortium vào session_state ──
# Lần đầu tiên (hoặc khi chưa có validator wallets), tự động thêm 3 trường
# ĐH-A / ĐH-B / TC-C từ PoS Registry vào danh sách Issuer.


# ── Đảm bảo có wallet ──

wallets = st.session_state.get("wallets", [])
if not wallets:
    st.info("Cần ít nhất 1 wallet. Bấm tạo nhanh bên dưới.")
    if st.button("⚡ Tạo wallet demo", key="flow_quick_wallet"):
        w = generate_wallet()
        st.session_state.wallets = [
            {"name": "Trường Đại học DEMO-A", "private_key_pem": w.private_key_pem,
             "public_key_hex": w.public_key_hex, "address": w.address}
        ]
        st.rerun()
    st.stop()


# ══════════════════════════════════════════════
# Trạng thái hiện tại
# ══════════════════════════════════════════════
st.subheader("🔹 Trạng thái mạng")

status_rows = []
tip_hashes = set()
for nid, node in network.nodes.items():
    tip = node.blockchain.get_latest_block().compute_hash()
    tip_hashes.add(tip)
    status_rows.append({
        "Node": nid,
        "Status": "🟢" if node.status == "ONLINE" else "🔴",
        "Height": node.height,
        "Mempool": len(node.mempool.get_transactions()),
        "Tip Hash": tip[:16] + "…",
    })

st.table(status_rows)

if len(tip_hashes) == 1:
    st.success(f"🤝 **Consensus (Đồng thuận)** — Cả 3 node cùng tip hash, height {list(network.nodes.values())[0].height}")
else:
    st.warning("⚠️ **Các node chưa đồng bộ — tip hash khác nhau**")
    st.info(
        "💡 **Giải thích hiện tượng:**\n\n"
        "- Có ít nhất một Node đang ở trạng thái **🔴 OFFLINE** (ví dụ Node-1 hoặc Node-2 bị tắt trong lúc các node khác tạo block mới).\n"
        "- Khi một node offline, nó không nhận được thông điệp `BLOCK` qua mạng, dẫn đến bị tụt lại ở chiều cao cũ (Height thấp hơn và Tip hash khác).\n"
        "- Để đưa toàn mạng về trạng thái **Đồng thuận 100% (Consensus)**, bấm nút **Đồng bộ tất cả Node** bên dưới để tự động bật lại các node và đồng bộ chuỗi theo quy tắc Nakamoto Consensus."
    )
    def _do_sync_all(net):
        if hasattr(net, "sync_all_nodes"):
            net.sync_all_nodes()
            return
        import copy
        best_node = None
        best_work = -1
        for node in net.nodes.values():
            node.status = "ONLINE"
            w = node.blockchain.total_work()
            if w > best_work or (w == best_work and (best_node is None or node.height > best_node.height)):
                best_work = w
                best_node = node
        if best_node:
            best_chain = copy.deepcopy(best_node.blockchain)
            for nid, node in net.nodes.items():
                if nid != best_node.node_id:
                    node.blockchain = copy.deepcopy(best_chain)
            net.log_event("Network", f"🔄 SYNC ALL: Đã đồng bộ tất cả node theo {best_node.node_id} (Height {best_node.height})")

    if st.button("🔄 Bật lại tất cả Node & Đồng bộ Mạng (Sync All)", key="btn_sync_all_flow"):
        _do_sync_all(network)
        st.success("✅ Đã bật tất cả node và đồng bộ toàn mạng thành công!")
        st.rerun()

st.divider()

# ══════════════════════════════════════════════
# BƯỚC 1: Tạo & Gửi Transaction
# ══════════════════════════════════════════════
st.subheader("① Tạo & Gửi Transaction")

col1, col2 = st.columns(2)
with col1:
    wallet_addresses = [w["address"] for w in wallets]
    wallet_labels = {w["address"]: f"{w['name']} — {w['address'][:12]}…" for w in wallets}
    sel_wallet = st.selectbox("Issuer:", wallet_addresses, format_func=lambda address: wallet_labels[address], key="flow_wallet")
    target = st.selectbox("Gửi đến:", list(network.nodes.keys()), key="flow_target")
with col2:
    cred_id = st.text_input("Credential ID:", value=f"CRED-{int(time.time()) % 10000:04d}", key="flow_cred")
    holder = st.text_input("Holder:", value="Người học DEMO-001", key="flow_holder")
    title = st.text_input("Title:", value="BSc Computer Science", key="flow_title")

if st.button("📤 Create → Sign → Submit → Broadcast", key="btn_flow_submit"):
    w_dict = next(w for w in wallets if w["address"] == sel_wallet)
    wallet = Wallet(
        private_key_pem=w_dict["private_key_pem"],
        public_key_hex=w_dict["public_key_hex"],
        address=w_dict["address"],
    )

    cred = Credential(cred_id, sel_wallet, holder, title, "2026-06-01", {})
    tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
    tx.sign(wallet)

    network.log_event("Flow", f"① TX created: {cred_id} → signed")

    node = network.nodes[target]
    ok, reason = node.submit_transaction(tx)

    if ok:
        with st.spinner("Propagation..."):
            time.sleep(0.5)
        st.success(f"✅ TX submitted & broadcast!")
        network.log_event("Flow", f"① TX propagated to all online nodes")

        # Hiện mempool mỗi node
        st.markdown("**Mempool sau broadcast:**")
        for nid, n in network.nodes.items():
            count = len(n.mempool.get_transactions())
            st.caption(f"  {nid}: {count} TX pending")
        st.rerun()
    else:
        st.error(f"❌ {reason}")

st.divider()

# ══════════════════════════════════════════════
# BƯỚC 2: Tạo Khối & Đồng Thuận (PoS / PoW)
# ══════════════════════════════════════════════
st.subheader("② Tạo Khối & Đạt Đồng Thuận Toàn Mạng (Consensus)")

flow_mode = st.radio(
    "Lựa chọn Cơ chế Đồng thuận:",
    [
        "🪙 Proof of Stake (PoS) — Khuyến nghị cho Liên minh TRUSTMEBRO (Không đào nonce, ký số khối)",
        "⛏️ Proof of Work (PoW) — Đào Nonce Cổ điển (Cạnh tranh sức mạnh băm CPU)",
    ],
    index=0,
    key="flow_consensus_choice",
)

first_node = list(network.nodes.values())[0]
pending_count = len(first_node.mempool.get_transactions())
st.metric("Giao dịch đang chờ trong Mempool", pending_count)

if "PoS" in flow_mode:
    st.info(
        "🏛️ **Mô hình Liên minh TRUSTMEBRO Consortium:**\n\n"
        "Các trường đại học & tổ chức kiểm định nắm giữ **Cổ phần bảo chứng uy tín (Reputation Stake)**. "
        "Thuật toán ngẫu nhiên có trọng số P(v) ~ Stake(v) sẽ chỉ định Validator chính danh đại diện ký số lên khối. "
        "Không hao phí CPU/điện năng, chốt khối ngay lập tức!"
    )

    # Hiển thị bảng Validator
    val_table = []
    tot_st = network.pos_registry.total_active_stake()
    for v in network.pos_registry.validators.values():
        pct = (v.stake / tot_st * 100) if tot_st > 0 else 0
        val_table.append({
            "Tổ chức Validator": v.name,
            "Phân loại": getattr(v, "institution_type", "Thành viên"),
            "Điểm Bảo chứng (Stake)": f"{v.stake:,}",
            "Tỷ lệ Cổ phần": f"{pct:.1f}%",
            "Uy tín": f"{getattr(v, 'reputation_score', 100)}/100",
            "Trạng thái": "🟢 Sẵn sàng" if v.is_active else "🔴 Bị phạt",
        })
    st.table(val_table)

    # Dự báo Proposer cho slot hiện tại
    cur_height = first_node.height + 1
    prev_h = first_node.blockchain.get_latest_block().compute_hash()
    predicted_val = network.pos_registry.select_validator(
        height=cur_height,
        seed=network.consensus_seed,
        previous_hash=prev_h,
    )

    col_pos1, col_pos2 = st.columns(2)
    with col_pos1:
        if predicted_val:
            st.success(f"🏆 **Validator chính danh được chọn tại Height {cur_height}:**\n\n**{predicted_val.name}**")
        else:
            st.error("Không có validator khả dụng.")
    with col_pos2:
        exec_node = st.selectbox("Node đại diện phát sóng khối:", list(network.nodes.keys()), key="pos_exec_node")

    if st.button("🪙 Bầu chọn, Ký số & Tạo Khối PoS", key="btn_flow_forge_pos"):
        if pending_count == 0:
            st.warning("⚠️ Mempool trống — hãy tạo và gửi giao dịch ở Bước 1 trước.")
        elif not predicted_val:
            st.error("Không có validator được bầu chọn.")
        else:
            proposer_node = network.nodes[exec_node]
            network.log_event("Flow", f"② PoS block forging initiated by '{predicted_val.name}'")

            with st.spinner("🪙 Đang xác thực quyền, ký số ECDSA & phát sóng khối PoS..."):
                block, res = proposer_node.forge_pos_pending(validator=predicted_val, seed=network.consensus_seed)

            if block is not None:
                with st.spinner("Phát sóng và đồng thuận giữa 3 Node..."):
                    time.sleep(0.5)

                st.success(
                    f"✅ **Khối PoS tạo thành công!** Height {block.height} | "
                    f"Ký bởi: **{res['validator_name']}** | "
                    f"Thời gian tạo/ký: {res['seconds']:.6f}s (chưa đo điện năng)"
                )
                st.code(res["block_hash"], language="text")

                network.log_event("Flow", "② ✅ PoS Consensus reached — all nodes updated ledger")
                st.rerun()
            else:
                st.error(f"Thất bại: {res}")

else:
    # Chế độ PoW truyền thống
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        miner_node = st.selectbox("Miner:", list(network.nodes.keys()), key="flow_miner")
        difficulty = st.slider("Difficulty:", 2, 5, 3, key="flow_diff")
    with col_m2:
        st.caption("Thuật toán tìm Nonce thỏa mãn số lượng ký tự '0' đầu hash.")

    if st.button("⛏️ Mine Block (PoW)", key="btn_flow_mine"):
        if pending_count == 0:
            st.warning("Mempool trống — gửi TX trước (Bước 1).")
        else:
            miner = network.nodes[miner_node]
            network.log_event("Flow", f"② PoW Mining started at {miner_node}")

            with st.spinner(f"⛏️ {miner_node} đang đào..."):
                block, result = miner.mine_pending(difficulty=difficulty)

            if block is not None:
                with st.spinner("Block propagation..."):
                    time.sleep(0.5)

                st.success(
                    f"✅ **Block mined!** Height {block.height} | "
                    f"Nonce {result['nonce']:,} | "
                    f"{result['attempts']:,} attempts | "
                    f"{result['seconds']:.4f}s"
                )
                st.code(result["block_hash"], language="text")

                network.log_event("Flow", f"② Block propagated → consensus check")
                st.rerun()
            else:
                st.warning(f"Không mine được: {result}")

st.divider()

# ══════════════════════════════════════════════
# BƯỚC 3: Xem chi tiết blockchain
# ══════════════════════════════════════════════
st.subheader("③ Blockchain chi tiết")

for nid, node in network.nodes.items():
    with st.expander(f"📦 {nid} — Height {node.height}"):
        for block in node.blockchain.chain:
            bh = block.compute_hash()
            ctype = block.header.consensus_type or "PoW"
            badge = "🪙 PoS" if ctype == "PoS" else "⛏️ PoW"
            extra_info = f"Validator: `{block.header.validator_address[:12]}…`" if ctype == "PoS" else f"nonce={block.header.nonce:,}"
            st.markdown(
                f"**Block {block.height}** [{badge}] | "
                f"`{bh[:16]}…` | "
                f"{extra_info} | "
                f"{block.transaction_count} TXs"
            )
            for tx in block.transactions:
                cred = tx.payload.get("credential_id", "—")
                holder_name = tx.payload.get("holder_name", "—")
                st.caption(f"    📄 {tx.tx_type} {cred} → {holder_name}")

st.divider()

# ══════════════════════════════════════════════
# Event Log
# ══════════════════════════════════════════════
st.subheader("📋 Event Log")

col_l1, col_l2 = st.columns([1, 4])
with col_l1:
    if st.button("🗑️ Xoá log", key="flow_clear_log"):
        network.clear_event_log()
        st.rerun()
with col_l2:
    if st.button("🔄 Refresh", key="flow_refresh"):
        st.rerun()

log = network.get_event_log(last_n=40)
if log:
    for line in reversed(log):
        st.text(line)
else:
    st.caption("(chưa có sự kiện)")

