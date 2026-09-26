"""Trang Wallet — tạo ví ECDSA, ký và xác minh chữ ký số.

Mục đích: cho sinh viên trải nghiệm tạo cặp khoá, ký message,
và thấy rõ chữ ký bị INVALID khi message bị sửa.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import generate_wallet, sign_message, verify_signature

init_state()



st.header("2️⃣ Wallet — Chữ ký số ECDSA")

# ══════════════════════════════════════════════
# PHẦN 1: Tạo Wallet
# ══════════════════════════════════════════════
st.subheader("🔹 Tạo Wallet")
st.caption("Mạng có sẵn 3 ví validator minh họa. Mỗi lần bấm Generate Wallet sẽ tạo thêm một ví riêng với khóa và địa chỉ mới.")

wallet_name = st.text_input("Tên wallet:", value="Demo University", key="wallet_name")

if st.button("🔑 Generate Wallet", key="btn_gen_wallet"):
    w = generate_wallet()
    wallet_entry = {
        "name": wallet_name,
        "private_key_pem": w.private_key_pem,
        "public_key_hex": w.public_key_hex,
        "address": w.address,
    }
    st.session_state.wallets.append(wallet_entry)
    st.success(f"✅ Đã tạo wallet **{wallet_name}**")

# Hiển thị danh sách wallet
if st.session_state.wallets:
    current_addresses = set(get_network().pos_registry.validators)
    st.markdown(f"#### 📋 Danh sách Wallet ({len(st.session_state.wallets)})")
    st.caption(f"{len(current_addresses)} validator hiện tại. Ví cùng tên nhưng khác địa chỉ là các danh tính khác nhau.")
    for i, wal in enumerate(st.session_state.wallets):
        role = "Validator" if wal["address"] in current_addresses else "Ví riêng / demo cũ"
        with st.expander(f"👛 [{role}] {wal['name']} — `{wal['address'][:16]}…`"):
            st.markdown(f"**Address:** `{wal['address']}`")
            st.markdown(f"**Public Key (hex):** `{wal['public_key_hex'][:32]}…`")
            st.code(wal["public_key_hex"], language="text")

            # Private key ẩn mặc định
            if st.checkbox(f"Hiện Private Key", key=f"show_pk_{i}"):
                st.code(wal["private_key_pem"], language="text")
                st.warning("⚠️ Private key phải giữ bí mật tuyệt đối!")
else:
    st.info("Chưa có wallet. Bấm **Generate Wallet** để tạo.")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Ký và Xác minh
# ══════════════════════════════════════════════
st.subheader("🔹 Ký và Xác minh Message")

if not st.session_state.wallets:
    st.warning("⚠️ Tạo ít nhất 1 wallet trước khi ký.")
else:
    # Chọn wallet để ký
    wallet_names = [f"{w['name']} — {w['address'][:12]}…" for w in st.session_state.wallets]

    sign_col, verify_col = st.columns(2)

    # ── Ký ──
    with sign_col:
        st.markdown("**✍️ Ký message**")
        signer_idx = st.selectbox(
            "Chọn wallet ký:",
            range(len(wallet_names)),
            format_func=lambda i: wallet_names[i],
            key="signer_select",
        )
        sign_msg = st.text_area("Message:", value="Hello Blockchain", key="sign_msg")

        if st.button("✍️ Sign", key="btn_sign"):
            signer = st.session_state.wallets[signer_idx]
            sig = sign_message(sign_msg, signer["private_key_pem"])
            st.session_state["last_signature"] = sig
            st.session_state["last_signer_pub"] = signer["public_key_hex"]
            st.session_state["last_signed_msg"] = sign_msg
            st.session_state["verify_msg"] = sign_msg
            st.session_state["verify_sig"] = sig
            st.session_state["verify_pub"] = signer["public_key_hex"]
            st.success(f"✅ Đã ký bằng wallet **{signer['name']}**")
            st.markdown("**Chữ ký (hex):**")
            st.code(sig, language="text")

    # ── Xác minh ──
    with verify_col:
        st.markdown("**🔍 Xác minh chữ ký**")
        verify_msg = st.text_area(
            "Message cần xác minh:",
            value=st.session_state.get("last_signed_msg", ""),
            key="verify_msg",
        )
        verify_sig = st.text_input(
            "Chữ ký (hex):",
            value=st.session_state.get("last_signature", ""),
            key="verify_sig",
        )
        verify_pub = st.text_input(
            "Public Key (hex):",
            value=st.session_state.get("last_signer_pub", ""),
            key="verify_pub",
        )

        if st.button("🔍 Verify", key="btn_verify"):
            if not verify_sig or not verify_pub:
                st.error("❌ Cần nhập đủ chữ ký và public key.")
            else:
                ok = verify_signature(verify_msg, verify_sig, verify_pub)
                if ok:
                    st.success("✅ **VALID** — Chữ ký hợp lệ. Message chưa bị sửa đổi.")
                else:
                    st.error("❌ **INVALID** — Chữ ký không khớp. Message đã bị thay đổi hoặc sai khoá.")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Demo tấn công — sửa message
# ══════════════════════════════════════════════
st.subheader("🔹 Demo: Phát hiện giả mạo")
st.caption('Ký "Transfer 10 BTC to Bob", rồi đổi thành "100 BTC" → chữ ký INVALID.')

if st.button("🎬 Chạy Demo tấn công", key="btn_tamper_demo"):
    # Tạo wallet tạm cho demo
    demo_wallet = generate_wallet()

    original_msg = "Transfer 10 BTC to Bob"
    tampered_msg = "Transfer 100 BTC to Bob"

    sig = sign_message(original_msg, demo_wallet.private_key_pem)

    st.markdown("**Bước 1:** Ký message gốc")
    st.code(f"Message:   {original_msg}\nSignature: {sig[:64]}…", language="text")

    # Verify message gốc
    ok_original = verify_signature(original_msg, sig, demo_wallet.public_key_hex)
    st.success(f"✅ Verify message gốc → **{'VALID' if ok_original else 'INVALID'}**")

    st.markdown("**Bước 2:** Kẻ tấn công sửa '10' → '100', giữ nguyên chữ ký")
    st.code(f"Message:   {tampered_msg}\nSignature: {sig[:64]}… (giữ nguyên)", language="text")

    # Verify message bị sửa
    ok_tampered = verify_signature(tampered_msg, sig, demo_wallet.public_key_hex)
    st.error(f"❌ Verify message bị sửa → **{'VALID' if ok_tampered else 'INVALID'}**")

    st.info(
        "💡 Chữ ký được tính trên hash của message gốc. "
        "Khi message thay đổi dù 1 bit, hash khác hoàn toàn (Avalanche Effect), "
        "nên chữ ký không còn khớp."
    )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. Vì sao Private Key phải bí mật còn Public Key thì không?**

        - **Private Key** dùng để **ký** — ai có nó đều tạo được chữ ký hợp lệ,
          tức giả mạo được danh tính. Lộ private key = mất quyền kiểm soát.
        - **Public Key** dùng để **xác minh** — càng công khai càng tốt,
          để bất kỳ ai cũng kiểm tra được chữ ký mà không cần tin tưởng bên thứ ba.

        ---

        **2. Chữ ký số chứng minh điều gì?**

        - ✅ **Tính toàn vẹn** (Integrity): message chưa bị sửa đổi sau khi ký.
        - ✅ **Không thể chối bỏ** (Non-repudiation): chỉ chủ private key mới ký được.
        - ✅ **Xác thực nguồn gốc** (Authentication): message đến từ đúng người ký.

        **Chữ ký KHÔNG đảm bảo điều gì?**

        - ❌ **Không giữ bí mật nội dung**: message vẫn là plaintext, ai cũng đọc được.
          Muốn bảo mật nội dung cần **encryption** (mã hoá), không phải signature.
        """
    )
