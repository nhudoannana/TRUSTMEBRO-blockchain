"""TRUSTMEBRO — điểm vào ứng dụng Streamlit.

Cấu hình st.navigation + st.Page để quản lý sidebar và thứ tự trang.
Dashboard hiển thị chỉ số thật từ Network/Blockchain/Mempool.
"""

import streamlit as st
from state import init_state, get_network

# ── Cấu hình trang (gọi 1 lần duy nhất, trước st.navigation) ──
st.set_page_config(
    page_title="TRUSTMEBRO",
    page_icon="🔗",
    layout="wide",
)

# ══════════════════════════════════════════════
# AUTHENTICATION — Google OAuth
# ══════════════════════════════════════════════

# Kiểm tra xem có cấu hình [auth] trong secrets không
_has_auth = "auth" in st.secrets if hasattr(st, "secrets") else False

if _has_auth:
    # Nút Login/Logout trên sidebar
    with st.sidebar:
        if st.experimental_user.is_logged_in:
            name = st.experimental_user.name or st.experimental_user.email
            st.markdown(f"👤 **{name}**")
            if st.button("🚪 Đăng xuất", use_container_width=True):
                st.logout()
        else:
            st.markdown("### 🔐 Đăng nhập")
            if st.button("🔑 Đăng nhập bằng Google", use_container_width=True, type="primary"):
                st.login()

    # Chặn nội dung nếu chưa đăng nhập
    if not st.experimental_user.is_logged_in:
        st.title("🔗 TRUSTMEBRO")
        st.info("👋 Vui lòng **đăng nhập bằng Google** ở sidebar để truy cập ứng dụng.")
        st.stop()


# ══════════════════════════════════════════════
# Dashboard (callable cho st.Page)
# ══════════════════════════════════════════════

def dashboard_page():
    """Nội dung Dashboard — chỉ số thật, sơ đồ luồng, Quick Start."""
    init_state()
    network = get_network()

    # ── Header ──
    st.title("🔗 TRUSTMEBRO")
    st.subheader("Mô phỏng phát hành và kiểm tra hồ sơ bằng Blockchain")
    st.caption(
        "Đồ án môn Blockchain — Mô phỏng học tập, "
        "dùng dữ liệu giả lập; không xác minh pháp lý cá nhân hoặc tổ chức."
    )

    st.divider()

    # ── Dashboard metrics ──
    st.markdown("### 📊 Dashboard")

    # Node đại diện: node ONLINE có height cao nhất
    representative = None
    for node in network.nodes.values():
        if node.status == "ONLINE":
            if representative is None or node.height > representative.height:
                representative = node

    total_nodes = len(network.nodes)
    online_nodes = sum(1 for n in network.nodes.values() if n.status == "ONLINE")

    if representative:
        bc = representative.blockchain
        total_blocks = len(bc.chain)
        total_txs = sum(len(b.transactions) for b in bc.chain)
        pending_txs = len(representative.mempool.get_transactions())

        seen_creds = {}
        for block in bc.chain:
            for tx in block.transactions:
                cid = tx.payload.get("credential_id")
                if cid:
                    if tx.tx_type == "ISSUE":
                        seen_creds[cid] = "ACTIVE"
                    elif tx.tx_type == "REVOKE":
                        seen_creds[cid] = "REVOKED"
        active_creds = sum(1 for s in seen_creds.values() if s == "ACTIVE")
        revoked_creds = sum(1 for s in seen_creds.values() if s == "REVOKED")
    else:
        total_blocks = 0
        total_txs = 0
        pending_txs = 0
        active_creds = 0
        revoked_creds = 0

    row1 = st.columns(4)
    row1[0].metric("🖥️ Total Nodes", total_nodes)
    row1[1].metric("🟢 Online Nodes", online_nodes)
    row1[2].metric("📦 Total Blocks", total_blocks)
    row1[3].metric("📝 Confirmed TXs", total_txs)

    row2 = st.columns(4)
    row2[0].metric("⏳ Pending TXs", pending_txs)
    row2[1].metric("✅ Active Credentials", active_creds)
    row2[2].metric("🔴 Revoked Credentials", revoked_creds)
    row2[3].metric(
        "📏 Chain Height",
        representative.height if representative else 0,
    )

    st.divider()

    # ── Sơ đồ luồng End-to-End ──
    st.markdown("### 🔄 Luồng End-to-End")

    flow_steps = [
        ("📄", "Credential"),
        ("→", ""),
        ("📝", "Transaction"),
        ("→", ""),
        ("🔏", "Digital\nSignature"),
        ("→", ""),
        ("🖥️", "Node\nVerification"),
        ("→", ""),
        ("📋", "Mempool"),
        ("→", ""),
        ("⛏️", "Mining"),
        ("→", ""),
        ("🌳", "Merkle\nRoot"),
    ]

    flow_steps_2 = [
        ("🔨", "Proof of\nWork"),
        ("→", ""),
        ("📦", "Block"),
        ("→", ""),
        ("📡", "Broadcast"),
        ("→", ""),
        ("🤝", "Consensus"),
        ("→", ""),
        ("🔗", "Blockchain"),
        ("→", ""),
        ("✅", "Verify\nCredential"),
    ]

    cols1 = st.columns(len(flow_steps))
    for i, (icon, label) in enumerate(flow_steps):
        with cols1[i]:
            if label:
                st.markdown(
                    f"<div style='text-align:center;'>"
                    f"<span style='font-size:1.5rem;'>{icon}</span><br>"
                    f"<small>{label}</small></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='text-align:center;padding-top:0.8rem;'>"
                    f"<span style='font-size:1.2rem;color:gray;'>→</span></div>",
                    unsafe_allow_html=True,
                )

    cols2 = st.columns(len(flow_steps_2))
    for i, (icon, label) in enumerate(flow_steps_2):
        with cols2[i]:
            if label:
                st.markdown(
                    f"<div style='text-align:center;'>"
                    f"<span style='font-size:1.5rem;'>{icon}</span><br>"
                    f"<small>{label}</small></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='text-align:center;padding-top:0.8rem;'>"
                    f"<span style='font-size:1.2rem;color:gray;'>→</span></div>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # ── Quick Start ──
    st.markdown("### 🚀 Quick Start — Hướng dẫn demo theo thứ tự")

    st.markdown(
        """
| # | Bước | Trang | Mô tả |
|---|---|---|---|
| 1 | Tạo Wallet cho Issuer | **Wallet & Digital Signature** | Tạo cặp khoá ECDSA, đặt tên (ví dụ "Trường Đại học A") |
| 2 | Tạo và ký Credential Transaction | **Mining & Consensus Flow** | Chọn Issuer, nhập thông tin credential, ký và submit |
| 3 | Broadcast Transaction tới các Node | *(tự động khi submit)* | TX được gửi đến Node → broadcast cho peer |
| 4 | Kiểm tra Transaction trong Mempool | **Network** | Xem bảng trạng thái, mở chi tiết → Mempool mỗi node |
| 5 | Mine Block | **Mining & Consensus Flow** | Chọn miner, difficulty → PoW → Block broadcast |
| 6 | Xem các Node đạt Consensus | **Mining & Consensus Flow** | Bảng: 3 node cùng Height, cùng Tip hash |
| 7 | Verify Credential | **Verify Credential** | Nhập Credential ID → 12 bước kiểm tra → VERIFIED |
| 8 | Attack Simulator | **Attack Simulator** | 6 kịch bản tấn công, thấy từng lớp bảo vệ |
        """
    )

    st.divider()

    # ── Modules ──
    with st.expander("📦 Các module trong hệ thống"):
        modules = {
            "hash.py":        "Hàm băm SHA-256, so sánh bit, brute-force demo",
            "wallet.py":      "Tạo cặp khoá ECDSA (SECP256K1), ký và xác minh chữ ký",
            "transaction.py": "Credential và Transaction có chữ ký số",
            "merkle.py":      "Merkle Tree — xây dựng, sinh proof, xác minh",
            "block.py":       "BlockHeader và Block — đóng gói giao dịch",
            "blockchain.py":  "Chuỗi block — thêm block, kiểm tra tính hợp lệ, ledger view",
            "mining.py":      "Proof of Work — tìm nonce thoả mãn difficulty",
            "mempool.py":     "Hàng chờ giao dịch chưa đóng block",
            "node.py":        "Full Node và Network — mô phỏng mạng ngang hàng",
        }
        for filename, desc in modules.items():
            st.markdown(f"- `blockchain/{filename}` — {desc}")


# ══════════════════════════════════════════════
# Navigation — sidebar + routing
# ══════════════════════════════════════════════

pg = st.navigation([
    st.Page(dashboard_page, title="Dashboard", icon="🏠"),
    st.Page("pages/1_Hash_Demo.py", title="SHA-256", icon="🔢"),
    st.Page("pages/2_Wallet.py", title="Wallet & Digital Signature", icon="🔑"),
    st.Page("pages/3_Transaction.py", title="Credentials & Transactions", icon="📝"),
    st.Page("pages/4_Mempool.py", title="Mempool", icon="📋"),
    st.Page("pages/5_Merkle.py", title="Merkle Tree", icon="🌳"),
    st.Page("pages/6_Explorer.py", title="Blockchain Explorer", icon="🔗"),
    st.Page("pages/7_Mining.py", title="Proof of Work / Mining", icon="⛏️"),
    st.Page("pages/8_Network.py", title="Network", icon="🌐"),
    st.Page("pages/9_Mining_Flow.py", title="Mining & Consensus Flow", icon="🔄"),
    st.Page("pages/10_Verify.py", title="Verify Credential", icon="✅"),
    st.Page("pages/11_Attacks.py", title="Attack Simulator", icon="🛡️"),
    st.Page("pages/12_PoW_vs_PoS.py", title="PoW vs PoS & Slashing", icon="⚖️"),
    st.Page("pages/13_Chatbot.py", title="Chatbot TRUSTMEBRO", icon="🤖"),
])

st.sidebar.divider()
st.sidebar.caption("Đồ án môn Blockchain — Nhóm 7 người")

pg.run()
