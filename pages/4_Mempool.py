"""Trang Mempool — xem hàng chờ giao dịch, thử thêm tx hợp lệ và sai.

Mục đích: cho sinh viên quan sát Mempool lọc giao dịch như thế nào,
thấy rõ lý do từ chối khi giao dịch bị giả mạo, trùng, hoặc sai Issuer.
"""

import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.mempool import Mempool, DummyLedger

init_state()



st.header("4️⃣ Mempool — Hàng chờ giao dịch")
st.caption('Bài tập mempool độc lập. Xem mempool của mạng đang chạy ở trang Network.')

# ── Khởi tạo Mempool trong session_state ──
if "mempool" not in st.session_state:
    st.session_state.mempool = Mempool()

# Cập nhật danh sách Issuer được phép từ wallet hiện có
st.session_state.mempool.authorized_issuers = {
    w["public_key_hex"] for w in st.session_state.wallets
}

dummy_ledger = DummyLedger()

# ══════════════════════════════════════════════
# PHẦN 1: Thêm Transaction hợp lệ
# ══════════════════════════════════════════════
st.subheader("🔹 Thêm Transaction hợp lệ")

if not st.session_state.wallets:
    st.warning("⚠️ Chưa có wallet. Vào trang **Wallet** tạo ít nhất 1 ví trước.")
else:
    wallet_names = [f"{w['name']} — {w['address'][:12]}…" for w in st.session_state.wallets]
    col_w, col_c = st.columns(2)
    with col_w:
        idx = st.selectbox(
            "Chọn Issuer:", range(len(wallet_names)),
            format_func=lambda i: wallet_names[i], key="mp_issuer",
        )
    with col_c:
        mp_cred_id = st.text_input("Credential ID:", value="CRED-MP-001", key="mp_cred_id")
        mp_holder = st.text_input("Holder:", value="Bob", key="mp_holder")

    if st.button("✅ Tạo & Thêm vào Mempool", key="btn_mp_add"):
        wal = st.session_state.wallets[idx]
        cred = Credential(
            credential_id=mp_cred_id,
            issuer_name=wal["name"],
            holder_name=mp_holder,
            title="Certificate",
            issue_date="2026-01-01",
            claims={},
        )
        tx = Transaction(
            tx_type="ISSUE",
            sender_public_key=wal["public_key_hex"],
            payload=asdict(cred),
        )
        wallet_obj = Wallet(wal["private_key_pem"], wal["public_key_hex"], wal["address"])
        tx.sign(wallet_obj)

        ok, reason = st.session_state.mempool.add_transaction(tx, dummy_ledger)
        if ok:
            st.success(f"✅ {reason} — tx_id: `{tx.tx_id[:24]}…`")
            st.session_state.event_log.append(f"Mempool ACCEPT: {mp_cred_id}")
        else:
            st.error(f"❌ {reason}")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Demo từ chối — 3 kịch bản tấn công
# ══════════════════════════════════════════════
st.subheader("🔹 Demo từ chối — 3 kịch bản")

if not st.session_state.wallets:
    st.info("Tạo wallet trước để chạy demo.")
else:
    wal = st.session_state.wallets[0]
    wallet_obj = Wallet(wal["private_key_pem"], wal["public_key_hex"], wal["address"])

    demo_a, demo_b, demo_c = st.columns(3)

    # (a) Sửa payload sau khi ký
    with demo_a:
        st.markdown("**(a) Payload bị sửa**")
        if st.button("🔴 Tấn công giả mạo", key="btn_tamper"):
            cred = Credential("CRED-TAMPER", wal["name"], "Alice", "BSc", "2026-01-01", {})
            tx = Transaction("ISSUE", wal["public_key_hex"], asdict(cred))
            tx.sign(wallet_obj)

            # Sửa payload sau khi ký
            tx.payload["holder_name"] = "Eve (giả mạo)"

            ok, reason = st.session_state.mempool.add_transaction(tx, dummy_ledger)
            st.error(f"❌ {reason}")

    # (b) Issuer không trong registry
    with demo_b:
        st.markdown("**(b) Issuer không phép**")
        if st.button("🔴 Issuer giả mạo", key="btn_rogue"):
            rogue = generate_wallet()
            cred = Credential("CRED-ROGUE", "Fake Univ", "Alice", "BSc", "2026-01-01", {})
            tx = Transaction("ISSUE", rogue.public_key_hex, asdict(cred))
            tx.sign(rogue)

            ok, reason = st.session_state.mempool.add_transaction(tx, dummy_ledger)
            st.error(f"❌ {reason}")

    # (c) Nộp trùng lần 2
    with demo_c:
        st.markdown("**(c) Nộp trùng (replay)**")
        if st.button("🔴 Replay attack", key="btn_replay"):
            cred = Credential("CRED-REPLAY", wal["name"], "Alice", "BSc", "2026-01-01", {})
            tx = Transaction("ISSUE", wal["public_key_hex"], asdict(cred))
            tx.sign(wallet_obj)

            ok1, r1 = st.session_state.mempool.add_transaction(tx, dummy_ledger)
            if ok1:
                st.success(f"Lần 1: ✅ {r1}")
            else:
                st.warning(f"Lần 1: {r1}")

            ok2, r2 = st.session_state.mempool.add_transaction(tx, dummy_ledger)
            st.error(f"Lần 2: ❌ {r2}")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Danh sách transaction đang chờ
# ══════════════════════════════════════════════
st.subheader("🔹 Danh sách Pending Transactions")

pending = st.session_state.mempool.get_transactions()

if pending:
    rows = []
    for tx in pending:
        cred_id = tx.payload.get("credential_id", "—")
        rows.append({
            "tx_id": tx.tx_id[:20] + "…",
            "Loại": tx.tx_type,
            "Credential ID": cred_id,
            "Issuer (address)": tx.sender_public_key[:20] + "…",
            "Thời gian": tx.timestamp,
        })
    st.table(rows)
    st.caption(f"Tổng: **{len(pending)}** transaction đang chờ")
else:
    st.info("Mempool trống. Thêm transaction ở phần trên.")

# Nút reset mempool
if st.button("🗑️ Xoá toàn bộ Mempool", key="btn_clear_mp"):
    st.session_state.mempool = Mempool(
        authorized_issuers={w["public_key_hex"] for w in st.session_state.wallets}
    )
    st.success("Đã xoá Mempool.")
    st.rerun()
