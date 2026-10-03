"""Trang Network — quản lý 3 Full Node, broadcast TX, sync chain.

Mục đích: cho sinh viên thấy tính phi tập trung — mỗi node giữ
bản sao riêng, tự xác minh, giao dịch lan truyền qua toàn mạng.
"""

import time
import queue
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.node import Network
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.blockchain import block_work, calculate_chain_work
from blockchain.fork_simulator import create_fork_blocks, deliver_block_to_nodes, generate_fork_dot

init_state()



st.header("8️⃣ Network & Full Nodes")


# ── Khởi tạo Network (cache_resource, chia sẻ giữa các trang) ──

network = get_network()

# ── Tự động seed wallet các trường ĐH Consortium vào session_state ──


# ══════════════════════════════════════════════
# PHẦN 1: Bảng Điều Khiển Tổng Quan Đồng Thuận (Consensus Overview)
# ══════════════════════════════════════════════
st.subheader("🔹 Bảng Điều Khiển Đồng Thuận Mạng P2P (Consensus Engine)")

# Tìm tip hash của chuỗi chính (node có tổng work cao nhất hoặc chuỗi dài nhất)
best_node = None
best_work = -1
for n in network.nodes.values():
    w = n.blockchain.total_work()
    if w > best_work or (w == best_work and (best_node is None or n.height > best_node.height)):
        best_work = w
        best_node = n

master_tip = best_node.blockchain.get_latest_block().compute_hash() if best_node else ""
master_height = best_node.height if best_node else 0

# Đếm số node đồng thuận với master_tip
agreed_nodes = [nid for nid, n in network.nodes.items() if n.blockchain.get_latest_block().compute_hash() == master_tip]
consensus_pct = int(len(agreed_nodes) / len(network.nodes) * 100) if network.nodes else 0
has_full_consensus = (consensus_pct == 100)

col_ov1, col_ov2 = st.columns([3, 2])
with col_ov1:
    if has_full_consensus:
        st.success(
            "### 🟢 TOÀN MẠNG ĐỒNG THUẬN (CONSENSUS REACHED)\n"
            f"Tất cả **3/3 Nodes** trong Liên minh TRUSTMEBRO đang lưu trữ cùng một sổ cái văn bằng tại **Height {master_height}**."
        )
    else:
        st.error(
            "### ⚠️ PHÂN NHÁNH HOẶC CHƯA ĐỒNG BỘ (FORK / DESYNC DETECTED)\n"
            f"Chỉ có **{len(agreed_nodes)}/{len(network.nodes)} Nodes** thống nhất về Tip Hash chuỗi chính. "
            "Có node đang bị tụt lại (do offline) hoặc mạng đang tồn tại phân nhánh cạnh tranh."
        )
    st.caption(
        "💡 **Quy tắc Đồng thuận:** Mạng tuân thủ thuật toán **Most-Work Nakamoto Consensus** "
        f"(chuỗi có tổng $\\sum 16^d$ lớn hơn) kết hợp **Consortium PoS** cho các tổ chức giáo dục & doanh nghiệp đã xác thực."
    )

def _do_sync_all(net):
    if hasattr(net, "sync_all_nodes"):
        net.sync_all_nodes()
        return

    # Fallback an toàn nếu Streamlit đang cache object Network cũ
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

with col_ov2:
    st.metric(
        "Tỷ lệ Đồng thuận Mạng P2P",
        f"{consensus_pct}%",
        delta="Hoàn hảo" if has_full_consensus else f"{len(agreed_nodes)}/{len(network.nodes)} Nodes",
        delta_color="normal" if has_full_consensus else "inverse",
    )
    st.markdown(f"**Tip Hash chuỗi chính:** `{master_tip[:18]}…`")
    if st.button("🔄 Đồng bộ Toàn mạng P2P (Re-sync Nodes)", key="btn_resync_network_p2p"):
        _do_sync_all(network)
        st.success("✅ Đã bật tất cả node và đồng bộ toàn mạng thành công!")
        st.rerun()

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Trạng thái Các Nút mạng Phân tán (Distributed Nodes Grid)
# ══════════════════════════════════════════════
st.subheader("🔹 Trạng thái các Nút Mạng Phân tán (Peer-to-Peer Nodes)")

NODE_METADATA = {
    "Node-1": {
        "title": "🏛️ Node-1 (ĐH-A — Minh họa)",
        "location": "Phòng Lab Blockchain (Địa điểm minh họa)",
        "role": "Validator / Proposer",
        "ping": "12 ms",
    },
    "Node-2": {
        "title": "🏫 Node-2 (ĐH-B — Minh họa)",
        "location": "Trung tâm Dữ liệu (Địa điểm minh họa)",
        "role": "Full Node Validator",
        "ping": "35 ms",
    },
    "Node-3": {
        "title": "🏢 Node-3 (TC-C — Minh họa)",
        "location": "Data Center (Địa điểm minh họa)",
        "role": "Enterprise Auditor",
        "ping": "24 ms",
    },
}

if hasattr(network, "pos_registry") and network.pos_registry:
    first_node = list(network.nodes.values())[0] if network.nodes else None
    if first_node and hasattr(network.pos_registry, "sync_with_blockchain"):
        network.pos_registry.sync_with_blockchain(first_node.blockchain)

cols = st.columns(3)
for idx, (nid, node) in enumerate(network.nodes.items()):
    meta = NODE_METADATA.get(nid, {
        "title": f"🖥️ {nid}",
        "location": "Trạm kiểm định",
        "role": "Full Node",
        "ping": "20 ms",
    })
    is_online = (node.status == "ONLINE")
    node_tip = node.blockchain.get_latest_block().compute_hash()
    is_agreed = (node_tip == master_tip)

    with cols[idx]:
        st.markdown(f"#### {meta['title']}")
        st.caption(f"📍 {meta['location']}")

        # Huy hiệu trạng thái
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if is_online:
                st.markdown("🟢 **ONLINE**")
            else:
                st.markdown("🔴 **OFFLINE**")
        with col_b2:
            if is_agreed:
                st.markdown("✅ **ĐỒNG THUẬN**")
            else:
                st.markdown("⚠️ **LỆCH TIP**")

        st.markdown(f"- **Vai trò:** `{meta['role']}`")
        st.markdown(f"- **Địa chỉ logic:** `{node.host}:{node.port}`")
        st.markdown(f"- **Độ trễ (Latency):** `{meta['ping']}`")
        st.markdown(f"- **Chiều cao (Height):** `{node.height}`")
        st.markdown(f"- **Tip Hash:** `{node_tip[:12]}…`")
        st.markdown(f"- **Mempool pending:** `{len(node.mempool.get_transactions())} TXs`")

        # Hiển thị điểm Uy tín PoS theo hoạt động cấp bằng on-chain
        matched_val = None
        if hasattr(network, "pos_registry") and network.pos_registry:
            validators_sorted = list(network.pos_registry.validators.values())
            if nid == "Node-1" and len(validators_sorted) >= 1:
                matched_val = validators_sorted[0]
            elif nid == "Node-2" and len(validators_sorted) >= 2:
                matched_val = validators_sorted[1]
            elif nid == "Node-3" and len(validators_sorted) >= 3:
                matched_val = validators_sorted[2]

        if matched_val:
            st.markdown(f"- **Uy tín PoS:** `⭐ {matched_val.stake:,} pts` ({matched_val.credentials_issued} bằng)")
        else:
            st.markdown(f"- **Nhánh phụ lưu trữ:** `{len(node.blockchain.side_branches)}`")

        # Nút tương tác nhanh
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if is_online:
                if st.button("🔴 Tắt", key=f"btn_card_off_{nid}"):
                    node.go_offline()
                    st.rerun()
            else:
                if st.button("🟢 Bật", key=f"btn_card_on_{nid}"):
                    node.go_online()
                    st.rerun()
        with col_btn2:
            if st.button("🔄 Sync", key=f"btn_card_sync_{nid}"):
                node.request_sync()
                time.sleep(0.3)
                st.rerun()

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Gửi Transaction
# ══════════════════════════════════════════════
st.subheader("🔹 Gửi Transaction vào mạng")

wallets = st.session_state.get("wallets", [])
if not wallets:
    st.info("Chưa có wallet. Tạo nhanh bên dưới hoặc vào trang **Wallet** để tạo.")
    if st.button("⚡ Tạo wallet demo nhanh", key="btn_quick_wallet"):
        w = generate_wallet()
        st.session_state.wallets = [
            {"name": "Trường Đại học A", "private_key_pem": w.private_key_pem,
             "public_key_hex": w.public_key_hex, "address": w.address}
        ]
        st.rerun()
else:
    col_form1, col_form2 = st.columns(2)
    with col_form1:
        wallet_addresses = [w["address"] for w in wallets]
        wallet_labels = {w["address"]: f"{w['name']} — {w['address'][:12]}…" for w in wallets}
        selected_wallet = st.selectbox("Issuer (wallet):", wallet_addresses, format_func=lambda address: wallet_labels[address], key="net_wallet")
        target_node = st.selectbox("Gửi đến node:", list(network.nodes.keys()), key="net_target")

    with col_form2:
        cred_id = st.text_input("Credential ID:", value="CRED-NET-001", key="net_cred_id")
        holder = st.text_input("Holder:", value="Người học DEMO-001", key="net_holder")
        title = st.text_input("Title:", value="BSc Computer Science", key="net_title")

    if st.button("📤 Tạo & Gửi Transaction", key="btn_send_tx"):
        w_dict = next(w for w in wallets if w["address"] == selected_wallet)
        wallet = Wallet(
            private_key_pem=w_dict["private_key_pem"],
            public_key_hex=w_dict["public_key_hex"],
            address=w_dict["address"],
        )

        cred = Credential(cred_id, selected_wallet, holder, title, "2026-06-01", {})
        tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
        tx.sign(wallet)

        node = network.nodes[target_node]
        ok, reason = node.submit_transaction(tx)

        if ok:
            with st.spinner("Đợi propagation..."):
                time.sleep(0.5)  # chờ worker thread xử lý
            st.success(f"✅ {reason}")
            st.rerun()
        else:
            st.error(f"❌ {reason}")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Demo tấn công — TX giả mạo
# ══════════════════════════════════════════════
st.subheader("🔹 Demo: TX giả mạo bị cả mạng từ chối")

if wallets:
    if st.button("🔴 Gửi TX giả mạo (sửa payload sau khi ký)", key="btn_fake_tx"):
        w_dict = wallets[0]
        wallet = Wallet(
            private_key_pem=w_dict["private_key_pem"],
            public_key_hex=w_dict["public_key_hex"],
            address=w_dict["address"],
        )

        cred = Credential("CRED-FAKE", w_dict["name"], "Hacker", "Fake PhD", "2026-01-01", {})
        tx = Transaction("ISSUE", wallet.public_key_hex, asdict(cred))
        tx.sign(wallet)

        # Giả mạo payload sau khi ký
        tx.payload["title"] = "Fake PhD in Everything"

        node1 = network.nodes["Node-1"]
        ok, reason = node1.submit_transaction(tx)
        st.error(f"❌ Node-1 từ chối: {reason}")
        st.info("TX không được broadcast → không node nào nhận.")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 5: Sync Chain
# ══════════════════════════════════════════════
st.subheader("🔹 Đồng bộ Chain (Sync)")
st.caption(
    "Node OFFLINE bỏ lỡ block mới. Khi online lại, Sync lấy chain dài nhất "
    "hợp lệ từ peer. (Hữu ích khi có mining/consensus tạo block mới.)"
)

sync_node = st.selectbox("Chọn node cần sync:", list(network.nodes.keys()), key="sync_node")
if st.button("🔄 Sync ngay", key="btn_sync"):
    node = network.nodes[sync_node]
    if node.status != "ONLINE":
        st.warning(f"{sync_node} đang OFFLINE — bật lên trước.")
    else:
        node.request_sync()
        with st.spinner("Đợi sync response..."):
            time.sleep(0.5)
        st.success(f"✅ {sync_node} height = {node.height}")
        st.rerun()

st.divider()

# ══════════════════════════════════════════════
# PHẦN 6: Mô phỏng Phân nhánh (Fork) & Tái tổ chức chuỗi (Chain Reorganization)
# ══════════════════════════════════════════════
st.subheader("🔱 Mô phỏng Phân nhánh (Fork) & Tái tổ chức chuỗi (Chain Reorganization)")

st.info(
    "💡 **Quy tắc Most-Work Chain (Nakamoto Consensus):**\n\n"
    "- Khi 2 miner tạo ra 2 block hợp lệ ở cùng chiều cao (height) gần như đồng thời, mạng sẽ bị **phân nhánh (Fork)**.\n"
    "- Mỗi node lưu giữ **cả hai nhánh** (chuỗi chính và nhánh phụ / side branches).\n"
    "- **Quy tắc chọn chuỗi:** Tính theo **tổng công việc PoW** $\\sum 16^{\\text{difficulty}}$, không chỉ dựa vào độ dài. "
    "Chuỗi có nhiều công sức băm tích lũy nhất sẽ là chuỗi hợp lệ duy nhất (Canonical Chain).\n"
    "- **Tái tổ chức chuỗi (Reorganization):** Khi một nhánh nhận thêm block hoặc có tổng PoW cao hơn, các node lập tức "
    "chuyển sang nhánh đó. Tất cả giao dịch ở nhánh bị loại bỏ (orphaned) sẽ được **hoàn trả lại vào Mempool**!"
)

# Quản lý state cho Fork demo
if "fork_demo" not in st.session_state:
    st.session_state.fork_demo = {
        "step": 0,
        "block_1a": None,
        "block_1b": None,
        "block_2b": None,
        "tx_alice": None,
        "tx_bob": None,
        "tx_carol": None,
    }

f_state = st.session_state.fork_demo

col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    if st.button("1️⃣ Tạo 2 Block cùng Height", key="btn_fork_step1"):
        # Lấy base block từ Node-1
        base_block = network.nodes["Node-1"].blockchain.get_latest_block()
        w = wallets[0] if wallets else None
        if not w:
            st.warning("Cần ít nhất 1 wallet để tạo giao dịch.")
            st.stop()

        wal_obj = Wallet(w["private_key_pem"], w["public_key_hex"], w["address"])

        # Tạo TX cho Nhánh A (DEMO-001) và Nhánh B (DEMO-002)
        tx_a = Transaction("ISSUE", wal_obj.public_key_hex, {"credential_id": "CRED-FORK-A", "holder": "Người học DEMO-001", "title": "BSc A"})
        tx_a.sign(wal_obj)

        tx_b = Transaction("ISSUE", wal_obj.public_key_hex, {"credential_id": "CRED-FORK-B", "holder": "Người học DEMO-002", "title": "BSc B"})
        tx_b.sign(wal_obj)

        # Đào 2 block cùng height
        with st.spinner("⛏️ 2 Miner đang đào 2 block song song..."):
            b_1a, b_1b = create_fork_blocks(base_block, [tx_a], [tx_b], diff_a=2, diff_b=2)

        f_state["block_1a"] = b_1a
        f_state["block_1b"] = b_1b
        f_state["tx_alice"] = tx_a
        f_state["tx_bob"] = tx_b
        f_state["step"] = 1

        # Gửi Block 1A cho Node-1 và Node-3; gửi Block 1B cho Node-2
        deliver_block_to_nodes(network, b_1a, ["Node-1", "Node-3"], sender_id="Miner-1")
        deliver_block_to_nodes(network, b_1b, ["Node-2"], sender_id="Miner-2")

        # Đồng thời gửi Block 1B cho Node-1 để Node-1 lưu vào side_branches
        deliver_block_to_nodes(network, b_1b, ["Node-1"], sender_id="Miner-2")
        time.sleep(0.4)

        network.log_event("Simulation", f"🔱 FORK CREATED: Block 1A sent to Node-1/Node-3; Block 1B sent to Node-2")
        st.success("✅ Đã tạo Fork! Node-1 và Node-3 chọn Nhánh A; Node-2 chọn Nhánh B.")
        st.rerun()

with col_f2:
    btn_disabled = (f_state["step"] < 1)
    if st.button("2️⃣ Đào Block 2B trên Nhánh B", key="btn_fork_step2", disabled=btn_disabled):
        w = wallets[0]
        wal_obj = Wallet(w["private_key_pem"], w["public_key_hex"], w["address"])
        tx_c = Transaction("ISSUE", wal_obj.public_key_hex, {"credential_id": "CRED-FORK-C", "holder": "Người học DEMO-003", "title": "BSc C"})
        tx_c.sign(wal_obj)

        with st.spinner("⛏️ Miner-2 đang đào Block 2B nối vào Nhánh B..."):
            b_2b = Block(
                transactions=[tx_c],
                height=f_state["block_1b"].height + 1,
                previous_hash=f_state["block_1b"].compute_hash(),
                difficulty=2,
            )
            mine_block(b_2b)

        f_state["block_2b"] = b_2b
        f_state["tx_carol"] = tx_c
        f_state["step"] = 2

        # Gửi Block 2B cho Node-2 trước
        deliver_block_to_nodes(network, b_2b, ["Node-2"], sender_id="Miner-2")
        time.sleep(0.3)

        network.log_event("Simulation", f"⛏️ Block 2B mined on Branch B! Total PoW Branch B = {256+256} > Branch A ({256})")
        st.success(f"✅ Block 2B mined! Nhánh B hiện có 2 block (Work={256+256:,} > {256:,}).")
        st.rerun()

with col_f3:
    btn_reorg_disabled = (f_state["step"] < 2)
    if st.button("3️⃣ Broadcast 2B & Kích hoạt Reorg", key="btn_fork_step3", disabled=btn_reorg_disabled):
        # Gửi Block 2B cho Node-1 và Node-3
        deliver_block_to_nodes(network, f_state["block_2b"], ["Node-1", "Node-3"], sender_id="Miner-2")
        time.sleep(0.5)

        f_state["step"] = 3
        network.log_event("Simulation", "🔄 Reorg triggered on Node-1 and Node-3: switched to Branch B!")
        st.success("🎉 REORG THÀNH CÔNG! Toàn mạng đã thống nhất theo Nhánh B có tổng PoW cao hơn!")
        st.rerun()

with col_f4:
    if st.button("🔄 Reset Mô phỏng Fork", key="btn_fork_reset"):
        st.session_state.fork_demo = {
            "step": 0, "block_1a": None, "block_1b": None, "block_2b": None,
            "tx_alice": None, "tx_bob": None, "tx_carol": None,
        }
        # Reset các blockchain của các node về Genesis
        for nid, node in network.nodes.items():
            with node._state_lock:
                gen = node.blockchain.chain[0]
                node.blockchain.chain = [gen]
                node.blockchain.side_branches = []
                node.blockchain.block_pool = {gen.compute_hash(): gen}
                node.mempool.remove_transactions([tx.tx_id for tx in node.mempool.get_transactions()])
                node._seen_tx_ids.clear()
                while True:
                    try:
                        node.inbox.get_nowait()
                    except queue.Empty:
                        break
        network.log_event("Simulation", "🔄 Fork simulation reset to Genesis.")
        st.rerun()

# ── Trực quan hóa Sơ đồ nhánh (Graphviz) ──
st.markdown("#### 🌳 Sơ đồ Cây Phân nhánh (Fork Tree Visualization):")
sel_vis_node = st.selectbox("Chọn Node để xem sơ đồ phân nhánh:", list(network.nodes.keys()), key="sel_vis_node")
node_to_vis = network.nodes[sel_vis_node]

try:
    dot_code = generate_fork_dot(node_to_vis)
    st.graphviz_chart(dot_code)
except Exception as e:
    st.warning(f"Không thể vẽ sơ đồ: {e}")

st.caption(
    "🟢 **Xanh lá**: Block thuộc Chuỗi chính (Active / Canonical Chain). | "
    "🟠 **Cam vàng**: Block thuộc Nhánh phụ / Bị bỏ rơi (Side Branch / Orphaned)."
)

# ── Kiểm tra Mempool Rollback ──
st.markdown("#### 📥 Trạng thái Hoàn trả Giao dịch về Mempool sau Reorg:")
col_m_info1, col_m_info2 = st.columns(2)
with col_m_info1:
    st.markdown(f"**Mempool của {sel_vis_node}:**")
    m_txs = node_to_vis.mempool.get_transactions()
    if m_txs:
        for t in m_txs:
            c_id = t.payload.get("credential_id", "—")
            st.info(f"📄 Giao dịch đang chờ: `{c_id}` (tx_id: `{t.tx_id[:16]}…`)")
    else:
        st.caption("(Mempool hiện đang trống)")
with col_m_info2:
    st.markdown("**Giải thích sự kiện:**")
    if f_state["step"] == 1:
        st.markdown("- **Trạng thái:** Mạng bị Fork. Node-1 theo Nhánh A (Block 1A), Node-2 theo Nhánh B (Block 1B). Cả hai nhánh đều được lưu.")
    elif f_state["step"] == 2:
        st.markdown("- **Trạng thái:** Nhánh B có thêm Block 2B -> Tổng công việc PoW của Nhánh B ($16^2 + 16^2 = 512$) lớn hơn Nhánh A ($16^2 = 256$).")
    elif f_state["step"] >= 3:
        st.markdown(
            "- **Trạng thái:** Node-1 và Node-3 đã phát hiện Nhánh B có tổng PoW lớn hơn và tiến hành **Reorg**.\n"
            "- Block 1A bị tách khỏi chuỗi chính thành nhánh phụ.\n"
            "- Giao dịch `CRED-FORK-A` trong Block 1A **đã được tự động hoàn trả lại vào Mempool** của các node để không bị mất mát!"
        )
    else:
        st.markdown("Bấm nút **1️⃣ Tạo 2 Block cùng Height** để bắt đầu quy trình mô phỏng.")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 7: Chi tiết từng Node
# ══════════════════════════════════════════════
st.subheader("🔹 Chi tiết Node")

for nid, node in network.nodes.items():
    with st.expander(f"📦 {nid} — Height {node.height} — "
                     f"{len(node.mempool.get_transactions())} TX pending"):
        # Blockchain
        st.markdown("**Blockchain:**")
        for block in node.blockchain.chain:
            st.caption(
                f"  Block {block.height} | "
                f"hash: `{block.compute_hash()[:20]}…` | "
                f"prev: `{block.header.previous_hash[:20]}…` | "
                f"txs: {block.transaction_count}"
            )

        # Mempool
        st.markdown("**Mempool:**")
        txs = node.mempool.get_transactions()
        if txs:
            for tx in txs:
                cred_id = tx.payload.get("credential_id", "—")
                st.caption(f"  📄 {tx.tx_type} | {cred_id} | `{tx.tx_id[:20]}…`")
        else:
            st.caption("  (trống)")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 7: Event Log
# ══════════════════════════════════════════════
st.subheader("🔹 Event Log (thread-safe)")

col_log1, col_log2 = st.columns([1, 4])
with col_log1:
    if st.button("🗑️ Xoá log", key="btn_clear_log"):
        network.clear_event_log()
        st.rerun()

with col_log2:
    if st.button("🔄 Refresh", key="btn_refresh_log"):
        st.rerun()

log = network.get_event_log(last_n=30)
if log:
    for line in reversed(log):  # mới nhất ở trên
        st.text(line)
else:
    st.caption("(chưa có sự kiện)")

