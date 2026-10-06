"""Trang Mining — mô phỏng Proof of Work, benchmark difficulty.

Mục đích: cho sinh viên trải nghiệm đào block, thấy thời gian
tăng theo cấp số nhân khi difficulty tăng, hiểu vì sao PoW an toàn.
"""

import time
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state
from blockchain.block import Block
from blockchain.mining import mine_block, is_valid_pow

init_state()



st.header("7️⃣ Proof of Work — Mining")
st.caption("Bài tập đào khối độc lập. Dùng Mining & Consensus Flow để ghi khối lên mạng đang chạy.")

# ══════════════════════════════════════════════
# PHẦN 1: Khối Ứng Viên & Trình Mô Phỏng Đào (Candidate Block Card)
# ══════════════════════════════════════════════
st.subheader("🔹 Khối Ứng Viên (Candidate Block) & Trình Đào PoW")
st.caption(
    "Trong Proof of Work, Miner đóng gói các trường header của khối ứng viên và liên tục thay đổi giá trị Nonce "
    "cho đến khi tìm được mã băm SHA-256 nhỏ hơn hoặc bằng Target Hash (thỏa mãn số lượng ký tự '0' ở đầu)."
)

# Cấu hình phần cứng đào
HARDWARE_PROFILES = {
    "💻 CPU Tiêu chuẩn (Laptop sinh viên)": {"hashrate": 1500, "desc": "Sử dụng các luồng CPU thông thường."},
    "🎮 Card Đồ họa Rời (Gaming RTX GPU)": {"hashrate": 45000, "desc": "Tính toán song song hàng ngàn luồng CUDA."},
    "⚡ Máy đào ASIC Chuyên dụng (Antminer Rig)": {"hashrate": 250000, "desc": "Vi mạch chuyên dụng tối ưu hóa riêng cho SHA-256."},
}

col_hw1, col_hw2 = st.columns(2)
with col_hw1:
    difficulty = st.slider("Độ khó mạng (Difficulty — số ký tự '0' đầu):", 2, 5, 3, key="mine_diff")
    target_pattern = "0" * difficulty
    target_hash_display = target_pattern + "f" * (64 - difficulty)
    expected_attempts = 16 ** difficulty
    st.markdown(f"**Target Hash:** `{'0' * difficulty}` + `{'f' * (64 - difficulty)}`")
    st.caption(f"Không gian tìm kiếm trung bình: ~16^{difficulty} = **{expected_attempts:,}** giá trị Nonce")

with col_hw2:
    hw_choice = st.selectbox("Mô phỏng Phần cứng Khai thác (Hardware Profile):", list(HARDWARE_PROFILES.keys()), key="mine_hw")
    hw_info = HARDWARE_PROFILES[hw_choice]
    est_seconds = expected_attempts / hw_info["hashrate"]
    st.caption("Hashrate của các cấu hình là giả định minh họa; chương trình vẫn chạy trên CPU hiện tại.")
    st.markdown(f"**Năng lực băm lý thuyết:** `{hw_info['hashrate']:,} H/s` — *{hw_info['desc']}*")
    st.markdown(f"⏱️ **Thời gian giải ước tính lý thuyết:** `{est_seconds:.2f}s`")

# Thẻ thông tin Khối Ứng Viên (Candidate Block Inspector)
st.markdown("#### 📦 Thẻ Khối Ứng Viên (Candidate Block Header):")
col_cb1, col_cb2 = st.columns(2)
with col_cb1:
    cand_height = 1
    cand_prev = "0" * 64
    st.text_input("Height:", value=str(cand_height), disabled=True)
    st.text_input("Previous Hash:", value=cand_prev, disabled=True)
with col_cb2:
    cand_merkle = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    st.text_input("Merkle Root (Giao dịch văn bằng):", value=cand_merkle, disabled=True)
    st.text_input("Difficulty:", value=str(difficulty), disabled=True)

if st.button("⛏️ Bắt đầu Đào Khối (Start Mining)", key="btn_mine"):
    block = Block(
        transactions=[], height=cand_height,
        previous_hash=cand_prev, difficulty=difficulty,
    )

    start_t = time.time()
    with st.spinner(f"⛏️ Miner đang thử các giá trị Nonce để giải bài toán (Target: {difficulty} số '0')..."):
        result = mine_block(block)
    real_time = result["seconds"] if result["seconds"] > 0 else 0.0001
    real_hashrate = int(result["attempts"] / real_time)

    st.success("🎉 **BLOCK SUCCESSFULLY MINED! ĐÃ TÌM THẤY NONCE HỢP LỆ!**")

    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Nonce vàng tìm được", f"{result['nonce']:,}")
    m_col2.metric("Số lần băm thử (Attempts)", f"{result['attempts']:,}")
    m_col3.metric("Thời gian thực tế", f"{result['seconds']:.4f} s", delta=f"{real_hashrate:,} H/s trên máy")

    st.markdown("#### 🔍 So khớp Hash Khối với Target:")
    leading = result["block_hash"][:difficulty]
    trailing = result["block_hash"][difficulty:]
    st.code(
        f"Mã Hash đạt chuẩn: [{leading}] {trailing}\n"
        f"Yêu cầu Target:   [{target_pattern}] {'*' * (64 - difficulty)} (Thoả mãn {difficulty} số '0' đầu)",
        language="text",
    )

    # Verify
    assert is_valid_pow(block)
    st.caption("✅ `is_valid_pow()` xác nhận khối hoàn toàn hợp lệ theo quy tắc Nakamoto Consensus.")

st.divider()

# ══════════════════════════════════════════════
# PHẦN 2: Benchmark
# ══════════════════════════════════════════════
st.subheader("🔹 Benchmark — So sánh difficulty")
st.caption("Mine 3 lần mỗi mức difficulty (2, 3, 4), xem thời gian trung bình tăng theo cấp số.")

if st.button("📊 Chạy Benchmark", key="btn_benchmark"):
    results_table = []
    chart_data = {}

    for diff in [2, 3, 4]:
        times = []
        attempts_list = []
        for trial in range(3):
            block = Block(
                transactions=[], height=1,
                previous_hash="0" * 64, difficulty=diff,
                # Dùng timestamp khác nhau mỗi lần để hash khác
                timestamp=f"2026-01-01T00:00:{trial:02d}+00:00",
            )
            result = mine_block(block)
            times.append(result["seconds"])
            attempts_list.append(result["attempts"])

        avg_time = sum(times) / len(times)
        avg_attempts = sum(attempts_list) / len(attempts_list)

        results_table.append({
            "Difficulty": diff,
            "Target": "0" * diff + "…",
            "Không gian (~)": f"{16**diff:,}",
            "Lần thử TB": f"{avg_attempts:,.0f}",
            "Thời gian TB (s)": f"{avg_time:.4f}",
            "Lần 1 (s)": f"{times[0]:.4f}",
            "Lần 2 (s)": f"{times[1]:.4f}",
            "Lần 3 (s)": f"{times[2]:.4f}",
        })
        chart_data[f"d={diff}"] = avg_time

    st.table(results_table)

    # Biểu đồ
    st.markdown("#### ⏱️ Thời gian trung bình theo Difficulty")
    st.bar_chart(chart_data)

    # Phân tích
    if len(results_table) >= 2:
        t2 = float(results_table[0]["Thời gian TB (s)"])
        t3 = float(results_table[1]["Thời gian TB (s)"])
        t4 = float(results_table[2]["Thời gian TB (s)"])
        st.info(
            f"📊 Tỷ lệ tăng: d=2→3: **×{t3/max(t2,0.0001):.1f}**, "
            f"d=3→4: **×{t4/max(t3,0.0001):.1f}** "
            f"(lý thuyết: ×16 mỗi cấp)"
        )

st.divider()

# ══════════════════════════════════════════════
# PHẦN 3: Câu hỏi thảo luận
# ══════════════════════════════════════════════
with st.expander("💬 Câu hỏi thảo luận"):
    st.markdown(
        """
        **1. PoW giúp đạt đồng thuận bằng cơ chế nào?**

        - **Chi phí tính toán**: tạo block mới tốn hàng nghìn–triệu phép hash.
        - **Xác minh tức thì**: kiểm tra PoW chỉ cần 1 phép hash.
        - **Chuỗi dài nhất thắng**: node chọn chuỗi có tổng công sức lớn nhất,
          vì chuỗi dài hơn = nhiều PoW hơn = nhiều tài nguyên thật hơn.
        - **Tấn công 51%**: muốn sửa chuỗi phải đào nhanh hơn toàn bộ mạng,
          cần > 50% sức mạnh tính toán — rất tốn kém.

        ---

        **2. Vì sao thời gian tăng theo cấp số nhân?**

        | Difficulty | Số 0 đầu | Xác suất hash hợp lệ | Lần thử TB |
        |---|---|---|---|
        | 2 | 00 | 1/256 | ~256 |
        | 3 | 000 | 1/4.096 | ~4.096 |
        | 4 | 0000 | 1/65.536 | ~65.536 |
        | 5 | 00000 | 1/1.048.576 | ~1 triệu |

        Mỗi cấp difficulty nhân không gian tìm kiếm lên **×16**.
        Bitcoin hiện tại có difficulty tương đương ~70+ số 0 đầu (dạng bit).

        ---

        **3. Tại sao xác minh PoW nhanh hơn tạo PoW?**

        - Tạo: thử hàng triệu nonce → hàng triệu phép hash.
        - Xác minh: chỉ 1 phép hash, kiểm tra có đủ số 0 không.
        - Đây là **bất đối xứng**: tốn công để tạo, dễ dàng để kiểm tra —
          giống như giải Sudoku khó nhưng kiểm tra đáp án thì nhanh.
        """
    )
