"""Trang Verify — xác minh và thu hồi credential.

Mục đích: Verifier nhập Credential ID, hệ thống kiểm tra 12 bước
từ TX đến Block đến Chain, hiển thị từng bước PASS/FAIL.
Issuer có thể thu hồi credential bằng REVOKE transaction.
"""

import json
import time
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction
from blockchain.claim_merkle import (
    compute_claim_leaf_hash,
    verify_claim_inclusion_proof,
    simulate_dictionary_attack,
    generate_salt,
)

init_state()



st.header("🔟 Verify Credential")

network = get_network()

# Dùng blockchain của Node-1 (tất cả node có cùng chain sau consensus)
node = network.nodes["Node-1"]
bc = node.blockchain

# ══════════════════════════════════════════════
# PHẦN 1: Xác minh Credential
# ══════════════════════════════════════════════
st.subheader("🔹 Xác minh Credential")

cred_id = st.text_input("Nhập Credential ID:", value="", key="verify_cred_id",
                         placeholder="Ví dụ: CRED-0001")

if st.button("🔍 Verify", key="btn_verify") and cred_id.strip():
    cred_id = cred_id.strip()
    steps, final_status, info = bc.verify_credential(
        cred_id, pos_registry=get_network().pos_registry
    )

    # Hiển thị từng bước
    st.markdown("#### Kết quả kiểm tra 12 bước:")
    for i, (name, passed, detail) in enumerate(steps, 1):
        icon = "✅" if passed else "❌"
        st.markdown(f"**{i}. {icon} {name}** — {detail}")

    # Kết quả cuối
    st.markdown("---")
    if final_status == "VERIFIED":
        st.success("### ✅ VERIFIED — Credential hợp lệ và đang ACTIVE")
    elif final_status == "REVOKED":
        st.warning("### 🔴 REVOKED — Credential đã bị thu hồi")
    elif final_status == "NOT_FOUND":
        st.error(f"### ❌ NOT FOUND — Credential '{cred_id}' không tồn tại trong blockchain")
    else:
        fail_step = next((name for name, ok, _ in steps if not ok), "Unknown")
        st.error(f"### ❌ INVALID — Thất bại tại bước: {fail_step}")

    # Thông tin credential (nếu tìm thấy)
    if info:
        st.markdown("---")
        st.markdown("#### 📋 Thông tin Credential")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Credential ID:** `{info.get('credential_id', '—')}`")
            st.markdown(f"**Issuer:** {info.get('issuer_name', '—')}")
            st.markdown(f"**Holder:** {info.get('holder_name', '—')}")
            st.markdown(f"**Title:** {info.get('title', '—')}")
            st.markdown(f"**Issue Date:** {info.get('issue_date', '—')}")
        with col2:
            st.markdown(f"**Issue TX:** `{info.get('issue_tx_id', '—')[:24]}…`")
            st.markdown(f"**Block Height:** {info.get('issue_block_height', '—')}")
            st.markdown(f"**Block Hash:** `{info.get('issue_block_hash', '—')[:24]}…`")
            st.markdown(f"**Merkle Root:** `{info.get('issue_merkle_root', '—')[:24]}…`")

        # Lịch sử
        st.markdown("#### 📜 Lịch sử")
        st.markdown(f"📗 **Cấp:** Block {info.get('issue_block_height', '—')}")
        if "revoke_block_height" in info:
            st.markdown(
                f"📕 **Thu hồi:** Block {info['revoke_block_height']} "
                f"— Lý do: {info.get('revoke_reason', '—')}"
            )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Xác minh Chọn lọc (Selective Disclosure — Proof of Inclusion)
# ══════════════════════════════════════════════
st.subheader("🔹 Xác minh Chọn lọc (Selective Disclosure — Proof of Inclusion)")
st.caption(
    "Holder chỉ xuất trình duy nhất 1 claim cùng Salt và Merkle Proof. "
    "Verifier đối chiếu trực tiếp với claims_root trên Blockchain mà KHÔNG THỂ THẤY các claim khác."
)

st.info(
    "💡 **Nguyên lý Proof of Inclusion & Vai trò của Salt:**\n\n"
    "- Mỗi claim được băm: `leaf_hash = SHA256(JSON([claim_name, claim_value, salt]))`.\n"
    "- Blockchain chỉ lưu duy nhất **`claims_root`** trong block header / transaction payload, không chứa thông tin thô.\n"
    "- **Vì sao cần Salt?** Nếu không có salt, một claim có miền giá trị ít khả năng (như `Grade = A`) "
    "sẽ dễ dàng bị dò băm bằng cách tính thử `sha256('grade:A')`, `sha256('grade:B')`... Salt 128-bit biến không gian thử thành $2^{128}$, chống hoàn toàn tấn công từ điển.\n"
    "- ⚠️ **LƯU Ý:** Đây là **Proof of Inclusion**, TUYỆT ĐỐI KHÔNG PHẢI Zero-Knowledge Proof (ZKP)."
)

# Tải từ session_state nếu có
holder_creds = st.session_state.get("holder_credentials", {})
sel_mode = st.radio("Chế độ nhập dữ liệu:", ["Chọn từ chứng chỉ đã phát hành (Demo nhanh)", "Nhập thủ công"], horizontal=True, key="sel_mode")

if sel_mode == "Chọn từ chứng chỉ đã phát hành (Demo nhanh)" and holder_creds:
    sel_cred_id = st.selectbox("Chọn Credential:", list(holder_creds.keys()), key="sel_cred_picker")
    cred_pack = holder_creds[sel_cred_id]

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        sel_claim_name = st.selectbox("Chọn Claim cần tiết lộ cho Verifier:", list(cred_pack["claims"].keys()), key="sel_claim_picker")
        sel_claim_val = cred_pack["claims"][sel_claim_name]
        st.markdown(f"**Giá trị Claim:** `{sel_claim_val}`")
    with col_c2:
        sel_salt = cred_pack["salts"][sel_claim_name]
        st.markdown(f"**Salt (ngẫu nhiên 128-bit):** `{sel_salt[:16]}…`")
        sel_proof = cred_pack["proofs"][sel_claim_name]
        st.caption(f"Merkle Proof gồm {len(sel_proof)} sibling hashes leo lên root.")

    if st.button("🔍 Xác minh Claim độc lập (Proof of Inclusion)", key="btn_verify_selective"):
        ok, reason, sel_info = bc.verify_selective_claim(
            credential_id=sel_cred_id,
            claim_name=sel_claim_name,
            claim_value=sel_claim_val,
            salt=sel_salt,
            proof=sel_proof,
            pos_registry=network.pos_registry,
        )

        if ok:
            st.success(f"### ✅ {reason}")
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.markdown(f"**Claim xác thực:** `{sel_claim_name} = {sel_claim_val}`")
                leaf_h = compute_claim_leaf_hash(sel_claim_name, sel_claim_val, sel_salt)
                st.markdown(f"**Leaf Hash:** `{leaf_h[:24]}…`")
            with col_v2:
                st.markdown(f"**On-chain claims_root:** `{sel_info['claims_root'][:24]}…`")
                st.markdown(f"**Block Height:** {sel_info['block_height']}")

            st.info(
                "🔒 **Bảo vệ quyền riêng tư tuyệt đối:**\n\n"
                f"Verifier chỉ biết `{sel_claim_name} = {sel_claim_val}`. "
                "Tất cả các claims khác của Holder (như điểm số khác, xếp loại, thông tin cá nhân) "
                "hoàn toàn được ẩn giấu vì Verifier chỉ nhận các hash trung gian vô nghĩa của Merkle tree!"
            )
        else:
            st.error(f"### ❌ {reason}")
elif sel_mode == "Chọn từ chứng chỉ đã phát hành (Demo nhanh)" and not holder_creds:
    st.warning("Chưa có credential nào được phát hành trong phiên làm việc. Vào trang **Credentials & Transactions** tạo trước, hoặc chuyển sang 'Nhập thủ công'.")
else:
    # Nhập thủ công
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        manual_cred_id = st.text_input("Credential ID:", value="CRED-001", key="m_cred_id")
        manual_claim_name = st.text_input("Claim Name:", value="grade", key="m_claim_name")
        manual_claim_val = st.text_input("Claim Value:", value="A", key="m_claim_val")
    with col_m2:
        manual_salt = st.text_input("Salt (hex):", value="", key="m_salt")
        manual_proof_str = st.text_area("Merkle Proof (JSON list [[hash, 'left'/'right'], ...]):", value="[]", height=100, key="m_proof")

    if st.button("🔍 Xác minh Claim thủ công", key="btn_verify_manual"):
        try:
            parsed_proof = json.loads(manual_proof_str)
            proof_tuples = [(p[0], p[1]) for p in parsed_proof]
        except Exception as e:
            st.error(f"Lỗi phân tích cú pháp Proof: {e}")
            st.stop()

        ok, reason, sel_info = bc.verify_selective_claim(
            credential_id=manual_cred_id.strip(),
            claim_name=manual_claim_name.strip(),
            claim_value=manual_claim_val.strip(),
            salt=manual_salt.strip(),
            proof=proof_tuples,
            pos_registry=network.pos_registry,
        )
        if ok:
            st.success(f"### ✅ {reason}")
        else:
            st.error(f"### ❌ {reason}")

# Demo tấn công vét cạn / Từ điển
with st.expander("🧪 Demo tương tác: Tại sao bắt buộc phải có Salt? (Dictionary Attack Simulation)"):
    st.markdown("Giả sử Holder có claim nhạy cảm `grade = A` (thuộc tập khả dĩ: A, B, C, D, F).")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.markdown("#### ❌ Trường hợp KHÔNG dùng Salt")
        st.caption("Băm thẳng sha256('grade:A')")
        unsalted_target = compute_claim_leaf_hash("grade", "A", salt="")
        st.code(f"Hash mục tiêu: {unsalted_target[:32]}…", language="text")
        if st.button("🔨 Băm thử vét cạn (Không Salt)", key="btn_attack_unsalted"):
            cracked, val, att = simulate_dictionary_attack("grade", unsalted_target, ["A", "B", "C", "D", "F"], salt="")
            if cracked:
                st.error(f"🚨 ĐÃ BỊ ĐOÁN RA! Giá trị bị băm thử trúng là: '{val}' chỉ sau {att} phép thử!")
    with col_d2:
        st.markdown("#### ✅ Trường hợp CÓ Salt ngẫu nhiên 128-bit")
        demo_salt = generate_salt()
        salted_target = compute_claim_leaf_hash("grade", "A", salt=demo_salt)
        st.code(f"Hash mục tiêu: {salted_target[:32]}…", language="text")
        st.caption(f"Salt bí mật của Holder: {demo_salt[:16]}…")
        if st.button("🛡️ Băm thử vét cạn (Có Salt)", key="btn_attack_salted"):
            cracked, val, att = simulate_dictionary_attack("grade", salted_target, ["A", "B", "C", "D", "F"], salt="")
            if not cracked:
                st.success(f"🛡️ AN TOÀN TUYỆT ĐỐI! Thử toàn bộ tập ['A','B','C','D','F'] đều không khớp vì thiếu Salt 128-bit!")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Thu hồi Credential (REVOKE)
# ══════════════════════════════════════════════
st.subheader("🔹 Thu hồi Credential (REVOKE)")
st.caption("Issuer gửi REVOKE TX → Mempool → Mine → Credential chuyển sang REVOKED.")

wallets = st.session_state.get("wallets", [])
if not wallets:
    st.info("Chưa có wallet. Vào trang **Wallet** hoặc **Network** để tạo.")
else:
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        wallet_addresses = [w["address"] for w in wallets]
        wallet_labels = {w["address"]: f"{w['name']} — {w['address'][:12]}…" for w in wallets}
        rev_wallet = st.selectbox("Issuer (wallet):", wallet_addresses, format_func=lambda address: wallet_labels[address], key="rev_wallet")
        rev_cred_id = st.text_input("Credential ID cần thu hồi:", key="rev_cred_id",
                                     placeholder="CRED-xxxx")
    with col_r2:
        rev_reason = st.text_input("Lý do thu hồi:", value="Expired", key="rev_reason")
        rev_node = st.selectbox("Gửi đến node:", list(network.nodes.keys()), key="rev_node")

    if st.button("🔴 Gửi REVOKE Transaction", key="btn_revoke"):
        if not rev_cred_id.strip():
            st.warning("Nhập Credential ID.")
        else:
            w_dict = next(w for w in wallets if w["address"] == rev_wallet)
            wallet = Wallet(
                private_key_pem=w_dict["private_key_pem"],
                public_key_hex=w_dict["public_key_hex"],
                address=w_dict["address"],
            )

            payload = {
                "credential_id": rev_cred_id.strip(),
                "reason": rev_reason,
            }
            tx = Transaction("REVOKE", wallet.public_key_hex, payload)
            tx.sign(wallet)

            target = network.nodes[rev_node]
            ok, reason = target.submit_transaction(tx)

            if ok:
                with st.spinner("Propagation..."):
                    time.sleep(0.5)
                st.success(f"✅ REVOKE TX submitted & broadcast!")
                st.info("Bấm **Mine** bên dưới để đưa TX vào block.")
            else:
                st.error(f"❌ {reason}")

    # Nút mine nhanh
    st.markdown("---")
    mine_node = st.selectbox("Mine tại:", list(network.nodes.keys()), key="rev_mine_node")
    if st.button("⛏️ Mine (xử lý REVOKE)", key="btn_rev_mine"):
        miner = network.nodes[mine_node]
        pending = len(miner.mempool.get_transactions())
        if pending == 0:
            st.warning("Mempool trống. Gửi REVOKE TX trước.")
        else:
            with st.spinner("Mining..."):
                block, result = miner.mine_pending(difficulty=2)
            if block:
                with st.spinner("Block propagation..."):
                    time.sleep(0.5)
                st.success(
                    f"✅ Block mined! Height {block.height}, "
                    f"{result['attempts']:,} attempts"
                )
                st.info("Quay lại phần Verify ở trên để kiểm tra trạng thái REVOKED.")
                st.rerun()

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Danh sách credential trong chain
# ══════════════════════════════════════════════
with st.expander("📋 Danh sách credential trong blockchain"):
    found = False
    for block in bc.chain:
        for tx in block.transactions:
            cid = tx.payload.get("credential_id")
            if cid:
                status = bc.credential_status(cid)
                icon = "🟢" if status == "ACTIVE" else "🔴"
                found = True
                st.caption(
                    f"{icon} `{cid}` | {tx.tx_type} | "
                    f"{tx.payload.get('holder_name', '—')} | "
                    f"Block {block.height} | Status: {status}"
                )
    if not found:
        st.caption("Chưa có credential nào. Vào trang **Mining Flow** để tạo.")
