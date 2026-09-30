"""Trang Hash Demo — minh hoạ SHA-256, Avalanche Effect, và Brute-force.

Mục đích: giúp sinh viên tương tác trực tiếp với hàm băm,
quan sát các tính chất quan trọng mà blockchain dựa vào.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state
from blockchain.hash import sha256_hex, bit_difference_percent, bruteforce

init_state()



st.header("1️⃣ Hash Demo — SHA-256")

# ══════════════════════════════════════════════
# PHẦN 1: Generate Hash
# ══════════════════════════════════════════════
st.subheader("🔹 Generate Hash")
st.caption("Nhập bất kỳ dữ liệu nào để xem hash SHA-256 tương ứng.")

input_data = st.text_input("Nhập dữ liệu:", value="Hello TRUSTMEBRO", key="hash_input")

if st.button("Generate Hash", key="btn_gen_hash"):
    hash_result = sha256_hex(input_data)
    st.markdown(f"**Dữ liệu gốc:** `{input_data}`")
    st.code(hash_result, language="text")
    st.markdown(
        f"**Độ dài:** {len(hash_result)} ký tự hex "
        f"= {len(hash_result) * 4} bit (luôn cố định 256 bit)"
    )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Avalanche Effect
# ══════════════════════════════════════════════
st.subheader("🔹 Avalanche Effect")
st.caption("Thay đổi dù chỉ 1 ký tự → ~50% bit output thay đổi.")

col1, col2 = st.columns(2)
with col1:
    str_a = st.text_input("Chuỗi A:", value="hello", key="ava_a")
with col2:
    str_b = st.text_input("Chuỗi B:", value="hallo", key="ava_b")

if st.button("So sánh", key="btn_avalanche"):
    hash_a = sha256_hex(str_a)
    hash_b = sha256_hex(str_b)
    diff = bit_difference_percent(hash_a, hash_b)

    st.markdown(f"**Hash A:** `{hash_a}`")
    st.markdown(f"**Hash B:** `{hash_b}`")

    # Hiển thị % bit khác nhau với màu sắc
    if str_a == str_b:
        st.info(f"📊 Bit khác nhau: **{diff:.1f}%** — hai chuỗi giống hệt nhau.")
    else:
        st.success(f"📊 Bit khác nhau: **{diff:.1f}%** — gần 50% như kỳ vọng!")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Tính một chiều
# ══════════════════════════════════════════════
st.subheader("🔹 Tính một chiều (One-way Property)")

st.markdown(
    """
    Cho trước một hash, **không tồn tại** thuật toán nào suy ngược được input ban đầu.

    Ví dụ — thử đoán input của hash sau:
    """
)

mystery_input = "blockchain"
mystery_hash = sha256_hex(mystery_input)
st.code(mystery_hash, language="text")

st.warning(
    "⚠️ Cách duy nhất tìm input là **thử từng tổ hợp** (brute-force). "
    "Với chuỗi dài, số tổ hợp quá lớn để thử hết trong thời gian hợp lý."
)

st.divider()

# ══════════════════════════════════════════════
# PHẦN 4: Brute-force mô phỏng
# ══════════════════════════════════════════════
st.subheader("🔹 Brute-force mô phỏng")
st.caption("Thử vét cạn để tìm ngược input từ hash. Quan sát thời gian tăng theo cấp số nhân.")

bf_col1, bf_col2, bf_col3 = st.columns(3)
with bf_col1:
    bf_input = st.text_input("Chuỗi gốc (ngắn, 1-4 ký tự):", value="ab", key="bf_input")
with bf_col2:
    charset_option = st.selectbox(
        "Bảng ký tự:",
        ["Chữ số (0-9)", "Chữ thường (a-z)", "Chữ số + chữ thường"],
        key="bf_charset",
    )
with bf_col3:
    bf_max_len = st.slider("Độ dài tối đa thử:", 1, 5, 3, key="bf_maxlen")

# Ánh xạ lựa chọn → charset
CHARSET_MAP = {
    "Chữ số (0-9)": "0123456789",
    "Chữ thường (a-z)": "abcdefghijklmnopqrstuvwxyz",
    "Chữ số + chữ thường": "0123456789abcdefghijklmnopqrstuvwxyz",
}
charset = CHARSET_MAP[charset_option]

if st.button("🔍 Bắt đầu Brute-force", key="btn_bruteforce"):
    target_hash = sha256_hex(bf_input)
    st.markdown(f"**Hash mục tiêu:** `{target_hash}`")

    with st.spinner("Đang thử từng tổ hợp..."):
        result = bruteforce(target_hash, charset, bf_max_len)

    if result["found"]:
        st.success(
            f"✅ Tìm thấy: `{result['found']}` "
            f"sau **{result['attempts']:,}** lần thử, "
            f"**{result['seconds']:.4f}** giây."
        )
    else:
        st.error(
            f"❌ Không tìm thấy trong {result['attempts']:,} lần thử "
            f"({result['seconds']:.4f} giây). "
            f"Chuỗi gốc dài hơn {bf_max_len} ký tự hoặc ngoài bảng ký tự."
        )

    # Bảng so sánh thời gian theo độ dài
    st.markdown("#### ⏱️ So sánh thời gian theo độ dài tối đa")
    st.caption("Chạy brute-force với cùng chuỗi gốc, tăng dần max_len.")

    comparison_rows = []
    for test_len in range(1, bf_max_len + 1):
        r = bruteforce(target_hash, charset, test_len)
        status = f"✅ `{r['found']}`" if r["found"] else "❌ Không tìm thấy"
        # Tính không gian tìm kiếm: tổng tổ hợp từ độ dài 1 → test_len
        space = sum(len(charset) ** i for i in range(1, test_len + 1))
        comparison_rows.append({
            "Độ dài tối đa": test_len,
            "Không gian": f"{space:,}",
            "Số lần thử": f"{r['attempts']:,}",
            "Thời gian (s)": f"{r['seconds']:.4f}",
            "Kết quả": status,
        })

    st.table(comparison_rows)

st.divider()

# ══════════════════════════════════════════════
# PHẦN 5: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. Vì sao output SHA-256 luôn 256 bit?**

        SHA-256 sử dụng thuật toán nén Merkle–Damgård: dù input dài bao nhiêu,
        nó được chia thành các block 512 bit và xử lý tuần tự qua hàm nén,
        kết quả cuối luôn là 256 bit. Điều này giúp so sánh nhanh và lưu trữ
        đồng nhất trong blockchain.

        ---

        **2. Hash khác Encryption ở điểm nào?**

        | | Hash | Encryption |
        |---|---|---|
        | Chiều | Một chiều (không giải ngược) | Hai chiều (mã hoá ↔ giải mã) |
        | Khoá | Không cần khoá | Cần khoá (đối xứng hoặc bất đối xứng) |
        | Mục đích | Xác minh tính toàn vẹn | Bảo mật nội dung |
        | Output | Độ dài cố định | Độ dài phụ thuộc input |

        ---

        **3. Brute-force phụ thuộc yếu tố nào?**

        - **Kích thước bảng ký tự** (charset): 10 chữ số vs. 62 ký tự (a-z, A-Z, 0-9)
          → không gian tìm kiếm khác nhau rất lớn.
        - **Độ dài chuỗi gốc**: mỗi ký tự thêm nhân không gian lên |charset| lần
          → tăng theo **cấp số nhân**.
        - **Tốc độ phần cứng**: GPU/ASIC nhanh hơn CPU hàng nghìn lần,
          nhưng với SHA-256 đủ dài, vẫn không khả thi.
        """
    )
