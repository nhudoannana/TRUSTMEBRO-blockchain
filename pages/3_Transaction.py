"""Trang Credential & Transaction — tạo chứng nhận, ký thành giao dịch.

Mục đích: cho sinh viên trải nghiệm luồng Issuer tạo credential,
đóng gói thành transaction có chữ ký, và xác minh tính hợp lệ.
"""

import json
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import Wallet
from blockchain.transaction import Credential, Transaction, verify_transaction
from blockchain.claim_merkle import build_claims_merkle_tree

init_state()

# ── Tự động seed wallet các trường ĐH Consortium vào session_state ──




st.header("3️⃣ Credential & Transaction")

# ══════════════════════════════════════════════
# PHẦN 1: Tạo Credential & Transaction
# ══════════════════════════════════════════════
st.subheader("🔹 Phát hành Credential")

if not st.session_state.wallets:
    st.warning("⚠️ Chưa có wallet. Vào trang **Wallet** tạo ít nhất 1 ví trước.")
else:
    # Chọn Issuer wallet
    wallet_names = [f"{w['name']} — {w['address'][:12]}…" for w in st.session_state.wallets]
    issuer_idx = st.selectbox(
        "Chọn Issuer (wallet ký):",
        range(len(wallet_names)),
        format_func=lambda i: wallet_names[i],
        key="issuer_select",
    )

    # Danh bạ các miền dữ liệu hồ sơ thực tế trong TRUSTMEBRO
    PRESETS = {
        "🎓 Bằng Đại học / Học vị (Academic Degree)": {
            "cred_id": "DEG-2026-001",
            "title": "BSc in Computer Science & Engineering",
            "claims": {
                "major": "Computer Science",
                "gpa": "3.85",
                "grade": "A",
                "honors": "Summa Cum Laude",
                "thesis": "Blockchain-based Verifiable Credentials",
                "credits_earned": "142"
            }
        },
        "💼 Hồ sơ Kinh nghiệm & Năng lực Nghề nghiệp (TRUSTMEBRO)": {
            "cred_id": "EXP-DEV-882",
            "title": "Senior Blockchain & Backend Engineer Attestation",
            "claims": {
                "company": "TechCorp / FinTech R&D (minh họa)",
                "position": "Senior Blockchain Developer",
                "years_of_experience": "5",
                "seniority": "Level 4 (Senior Specialist)",
                "verified_skills": "Python, Cryptography, Distributed Consensus",
                "performance_rating": "Top 5% Outstanding"
            }
        },
        "📜 Chứng chỉ Quốc tế / Giấy phép Chuyên môn (Certification)": {
            "cred_id": "CERT-DEMO-9041",
            "title": "Chứng chỉ Kỹ năng DEMO-001",
            "claims": {
                "certificate_name": "Chứng chỉ Chuyên môn Giả lập",
                "score": "912/1000",
                "valid_until": "2029-09-30",
                "credential_status": "Active & Verified",
                "verification_authority": "Tổ chức Kiểm định DEMO-C"
            }
        },
        "🩺 Hồ sơ Thể trạng / Chứng nhận Y tế Bảo mật (Health Attestation)": {
            "cred_id": "MED-HLT-5510",
            "title": "Verified Medical & Fitness Attestation",
            "claims": {
                "blood_type": "O+",
                "vaccination_status": "Fully Vaccinated (Triple Dose)",
                "allergy_alert": "Penicillin (Severe)",
                "fitness_tier": "Class 1 - Optimal Aviation/Specialized Standard"
            }
        },
        "⚙️ Tùy biến Dữ liệu Tự do (Custom Key-Value JSON)": {
            "cred_id": "CUSTOM-001",
            "title": "Custom Flexible Verified Profile",
            "claims": {
                "custom_attribute_1": "Giá trị linh hoạt 1",
                "custom_attribute_2": "Giá trị linh hoạt 2",
                "domain_tag": "Enterprise-Confidential"
            }
        }
    }

    preset_names = list(PRESETS.keys())
    sel_preset = st.selectbox(
        "📂 Chọn Miền Dữ liệu Hồ sơ (Linh hoạt cho mọi nghiệp vụ):",
        preset_names,
        key="domain_preset",
    )
    chosen_preset = PRESETS[sel_preset]

    # Đồng bộ khi người dùng chuyển đổi preset
    if st.session_state.get("_last_preset") != sel_preset:
        st.session_state._last_preset = sel_preset
        st.session_state["cred_id"] = chosen_preset["cred_id"]
        st.session_state["title"] = chosen_preset["title"]
        st.session_state["claims_json"] = json.dumps(chosen_preset["claims"], indent=2, ensure_ascii=False)

    st.markdown("---")
    st.markdown("**Thông tin Credential / Hồ sơ xác thực:**")

    col1, col2 = st.columns(2)
    with col1:
        cred_id = st.text_input(
            "Credential ID:",
            key="cred_id",
        )
        holder_name = st.text_input("Holder (chủ sở hữu hồ sơ):", value="Người học DEMO-001", key="holder")
        issue_date = st.date_input("Ngày cấp:", key="issue_date")
    with col2:
        title = st.text_input(
            "Tiêu đề chứng nhận / Hồ sơ:",
            key="title",
        )
        st.markdown("**Danh sách Claims nhạy cảm (Tự động băm Salted Merkle Tree):**")
        claims_input_json = st.text_area(
            "Định dạng JSON (Mỗi cặp key-value là 1 claim độc lập):",
            height=130,
            key="claims_json",
        )

    # Hộp giải thích sư phạm về Salt và Proof of Inclusion
    st.info(
        "💡 **Tại sao bắt buộc phải dùng Salt ngẫu nhiên cho từng claim?**\n\n"
        "Nếu băm trực tiếp `hash(claim_name + claim_value)`, kẻ xấu hoặc người xác minh có thể thực hiện "
        "**tấn công dò băm / từ điển (Dictionary Attack)** đối với các claim có miền giá trị rất hẹp (low-entropy) như "
        "**`Grade`** (chỉ có A, B, C, D, F) hoặc **`GPA`**. Họ chỉ việc băm thử 5 giá trị này và so sánh với hash lá trên cây để phát hiện ngay kết quả của Holder! "
        "Nhờ có **Salt ngẫu nhiên 128-bit riêng biệt**, không gian băm mở rộng lên $2^{128}$ khả năng, chống tấn công dò băm hiệu quả. Salt không đảm bảo ẩn danh tuyệt đối."
    )
    st.warning(
        "⚠️ **LƯU Ý THUẬT NGỮ:** Đây là **Proof of Inclusion** (Bằng chứng bao hàm qua Merkle Tree) với Salted Leaves để chọn lọc tiết lộ thông tin (Selective Disclosure). "
        "Đây **KHÔNG PHẢI** là **Zero-Knowledge Proof (ZKP)** và không được gọi là ZKP."
    )

    if st.button("📜 Tạo Salted Claims, Merkle Tree & Ký Transaction", key="btn_create_tx"):
        issuer_wal = st.session_state.wallets[issuer_idx]

        # Parse claims JSON
        try:
            claims_dict = json.loads(claims_input_json)
        except Exception as e:
            st.error(f"Lỗi cú pháp JSON claims: {e}")
            st.stop()

        if not isinstance(claims_dict, dict) or not claims_dict:
            st.error('Claims phải là JSON object không rỗng, ví dụ {"grade": "A"}.')
            st.stop()
        if not cred_id.strip():
            st.error("Nhập Credential ID trước khi tạo giao dịch.")
            st.stop()

        # Dựng Salted Claims Merkle Tree
        claims_root, salts, proofs, tree_levels, claim_items = build_claims_merkle_tree(claims_dict)

        # Tạo Credential đối tượng
        cred = Credential(
            credential_id=cred_id,
            issuer_name=issuer_wal["name"],
            holder_name=holder_name,
            title=title,
            issue_date=str(issue_date),
            claims=claims_dict,
            claims_root=claims_root,
        )

        # Tạo Transaction chỉ lưu on-chain payload (KHÔNG lưu claims thô)
        tx = Transaction(
            tx_type="ISSUE",
            sender_public_key=issuer_wal["public_key_hex"],
            payload=cred.to_onchain_payload(),
        )

        # Ký bằng wallet Issuer
        wallet_obj = Wallet(
            private_key_pem=issuer_wal["private_key_pem"],
            public_key_hex=issuer_wal["public_key_hex"],
            address=issuer_wal["address"],
        )
        tx.sign(wallet_obj)

        # Lưu vào session_state
        if "transactions" not in st.session_state:
            st.session_state.transactions = []
        st.session_state.transactions.append(tx.to_dict())

        # Lưu gói dữ liệu ngoài chuỗi (Off-chain package) cho Holder để dùng ở trang Verify
        if "holder_credentials" not in st.session_state:
            st.session_state.holder_credentials = {}
        st.session_state.holder_credentials[cred_id] = {
            "credential_id": cred_id,
            "holder_name": holder_name,
            "title": title,
            "claims": claims_dict,
            "salts": salts,
            "proofs": proofs,
            "claims_root": claims_root,
            "claim_items": claim_items,
        }

        # Ghi log
        st.session_state.event_log.append(
            f"ISSUE credential '{cred_id}' (claims_root={claims_root[:16]}…) cho {holder_name} bởi {issuer_wal['name']}"
        )

        st.success("✅ Transaction đã tạo và ký thành công! (Payload on-chain chỉ chứa claims_root)")

        # Bảng chi tiết các claim lá Merkle
        st.markdown("#### 🌿 Bảng chi tiết từng Claim (Salted Leaves):")
        claim_rows = []
        for item in claim_items:
            claim_rows.append({
                "Claim Name": item.name,
                "Claim Value": item.value,
                "Salt (128-bit ngẫu nhiên)": item.salt[:16] + "…",
                "Leaf Hash (sha256)": item.leaf_hash[:20] + "…",
            })
        st.table(claim_rows)

        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.markdown("**Claims Merkle Root:**")
            st.code(claims_root, language="text")
            st.markdown("**Transaction ID (tx_id):**")
            st.code(tx.tx_id, language="text")
        with col_res2:
            st.markdown("**Chữ ký Issuer (ECDSA):**")
            st.code(tx.signature[:80] + "…", language="text")
            ok, reason = verify_transaction(tx)
            if ok:
                st.success(f"🔍 Verify Transaction: ✅ {reason}")
            else:
                st.error(f"🔍 Verify Transaction: ❌ {reason}")

        # So sánh On-chain vs Off-chain
        with st.expander("🛡️ So sánh dữ liệu On-chain vs Off-chain"):
            c_on, c_off = st.columns(2)
            with c_on:
                st.markdown("##### ⛓️ On-chain Payload (Lưu trên Blockchain)")
                st.caption("Chỉ chứa metadata và claims_root — không chứa thông tin điểm/claims thô. Lưu ý: metadata như holder, title vẫn hiện trên chuỗi.")
                st.json(tx.payload)
            with c_off:
                st.markdown("##### 💼 Off-chain Data (Holder nắm giữ)")
                st.caption("Chứa đầy đủ claims, salts ngẫu nhiên và Merkle proofs để xuất trình khi cần:")
                st.json({
                    "claims": claims_dict,
                    "salts": salts,
                    "claims_root": claims_root,
                })


    st.divider()

    # ══════════════════════════════════════════════
    # PHẦN 2: Danh sách Transaction đã tạo
    # ══════════════════════════════════════════════
    if st.session_state.get("transactions"):
        st.subheader("🔹 Danh sách Transaction đã tạo")
        send_node = st.selectbox("Gửi giao dịch đã ký đến node:", list(get_network().nodes), key="created_tx_node")
        st.caption("Gửi vào mempool, sau đó sang Mining & Consensus Flow để tạo block và Verify Credential để kiểm chứng.")
        for i, tx_dict in enumerate(st.session_state.transactions):
            cred_info = tx_dict["payload"]
            label = (
                f"{tx_dict['tx_type']} — "
                f"{cred_info.get('credential_id', 'N/A')} — "
                f"{cred_info.get('holder_name', 'N/A')}"
            )
            with st.expander(f"📄 {label}"):
                st.markdown(f"**tx_id:** `{tx_dict['tx_id']}`")
                st.markdown(f"**tx_type:** `{tx_dict['tx_type']}`")
                st.markdown(f"**Timestamp:** `{tx_dict['timestamp']}`")
                st.json(tx_dict["payload"])
                if st.button("📤 Gửi transaction này lên mạng", key="submit_created_" + tx_dict["tx_id"]):
                    pending = Transaction(
                        tx_dict["tx_type"], tx_dict["sender_public_key"], tx_dict["payload"],
                        nonce=tx_dict["nonce"], timestamp=tx_dict["timestamp"],
                    )
                    pending.tx_id = tx_dict["tx_id"]
                    pending.signature = tx_dict["signature"]
                    ok, reason = get_network().nodes[send_node].submit_transaction(pending)
                    if ok:
                        st.success("Đã gửi giao dịch đã ký vào mạng. Tiếp tục tạo block ở Mining & Consensus Flow.")
                    else:
                        st.error(reason)


    st.divider()

    # ══════════════════════════════════════════════
    # PHẦN 3: Demo thu hồi (REVOKE)
    # ══════════════════════════════════════════════
    st.subheader("🔹 Thu hồi Credential (REVOKE)")
    st.caption("Tạo transaction REVOKE cho một credential đã phát hành.")

    revoke_cred_id = st.text_input("Credential ID cần thu hồi:", key="revoke_cred_id")
    revoke_reason = st.text_input("Lý do thu hồi:", value="Phát hiện sai sót", key="revoke_reason")

    if st.button("🚫 Tạo REVOKE Transaction", key="btn_revoke"):
        if not revoke_cred_id:
            st.error("❌ Nhập Credential ID cần thu hồi.")
        else:
            issuer_wal = st.session_state.wallets[issuer_idx]
            tx = Transaction(
                tx_type="REVOKE",
                sender_public_key=issuer_wal["public_key_hex"],
                payload={"credential_id": revoke_cred_id, "reason": revoke_reason},
            )
            wallet_obj = Wallet(
                private_key_pem=issuer_wal["private_key_pem"],
                public_key_hex=issuer_wal["public_key_hex"],
                address=issuer_wal["address"],
            )
            tx.sign(wallet_obj)

            if "transactions" not in st.session_state:
                st.session_state.transactions = []
            st.session_state.transactions.append(tx.to_dict())

            st.session_state.event_log.append(
                f"REVOKE credential '{revoke_cred_id}': {revoke_reason}"
            )

            ok, reason = verify_transaction(tx)
            st.success(f"✅ REVOKE transaction đã tạo — tx_id: `{tx.tx_id[:32]}…`")
            if ok:
                st.success(f"🔍 Verify: ✅ {reason}")
            else:
                st.error(f"🔍 Verify: ❌ {reason}")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. Vì sao compute_hash() không gồm signature?**

        Vì signature được tạo *từ* hash — nếu gồm signature trong hash thì tạo
        vòng lặp: hash phụ thuộc signature, signature phụ thuộc hash.

        ---

        **2. Nonce dùng để làm gì?**

        Đảm bảo hai transaction cùng nội dung (ví dụ cấp lại credential)
        vẫn có tx_id khác nhau, tránh bị coi là trùng lặp.

        ---

        **3. Kẻ tấn công sửa payload rồi tính lại hash thì sao?**

        Hash mới sẽ khác hash cũ → chữ ký không còn khớp.
        Muốn ký lại cần private key của Issuer — kẻ tấn công không có.
        Đây là lý do blockchain kết hợp **hash + chữ ký** chứ không chỉ dùng một trong hai.
        """
    )
