"""Trang so sánh PoW vs PoS và Demo cơ chế phạt Slashing trong TRUSTMEBRO Consortium.

Mục đích:
- Đối chiếu toàn diện giữa Proof of Work và Proof of Stake trong hệ thống hồ sơ & chứng chỉ số.
- Trình diễn mô hình Consortium PoS: Các trường đại học & tổ chức kiểm định nắm giữ cổ phần bảo chứng (Reputation Stake).
- Bầu chọn Validator chính danh theo trọng số cổ phần P(v) ~ Stake(v) để ký số và tạo khối.
- Mô phỏng gian lận văn bằng / ký kép (Nothing at Stake) và thực thi cơ chế trừng phạt Slashing.
- Live Benchmark đo thời gian tạo khối và số lần thử nonce PoW; không đo điện năng.
"""

import time
import random
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state, get_network
from blockchain.wallet import generate_wallet, Wallet
from blockchain.transaction import Credential, Transaction
from blockchain.block import Block
from blockchain.mining import mine_block
from blockchain.pos import PoSRegistry, Validator

init_state()

st.header("⚖️ Cơ chế Đồng thuận: PoW vs PoS & Quản trị Liên minh TRUSTMEBRO")

st.info(
    "🎓 **LƯU Ý GIÁO DỤC QUAN TRỌNG:**\n\n"
    "Hệ thống mô phỏng kiến trúc **Consortium Proof of Stake (PoS / Reputation Stake)** phù hợp cho "
    "mạng lưới quản lý văn bằng, chứng chỉ và hồ sơ năng lực số (tương tự kiến trúc EBSI của Châu Âu hay Velocity Network). "
    "**Hệ thống tuyệt đối KHÔNG mô phỏng tiền mã hoá thật** (không có coin/token tài chính). "
    "Mọi 'Stake' trong mô phỏng là **Điểm cổ phần bảo chứng mô phỏng** dùng để minh họa trọng số bầu chọn, không chứng nhận uy tín pháp lý."
)

network = get_network()
pos_reg: PoSRegistry = network.pos_registry

# ══════════════════════════════════════════════
# 4 TABS CHUYÊN ĐỀ
# ══════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 So sánh PoW vs PoS",
    "🏛️ Quản trị Liên minh & Tạo Khối PoS",
    "🚨 Tấn công Nothing at Stake & Slashing",
    "⚡ Live Benchmark Đo lường",
])

# ──────────────────────────────────────────────
# TAB 1: BẢNG SO SÁNH TOÀN DIỆN
# ──────────────────────────────────────────────
with tab1:
    st.subheader("🔹 Bảng đối chiếu chi tiết Proof of Work và Proof of Stake trong TRUSTMEBRO")

    st.markdown(
        """
| Tiêu chí so sánh | ⛏️ Proof of Work (PoW) | 🪙 Proof of Stake (PoS / Consortium) |
|---|---|---|
| **Bản chất trong TRUSTMEBRO** | Các máy chủ cạnh tranh giải bài toán băm SHA-256 | Các Trường Đại học & Tổ chức Kiểm định nắm giữ Cổ phần Bảo chứng |
| **Cơ chế bầu chọn** | Ai tìm ra số Nonce thoả mãn độ khó trước thì được ghi khối | Bầu chọn ngẫu nhiên có trọng số theo uy tín/cổ phần: $P(v) \\sim Stake(v)$ |
| **Chi phí tính toán CPU** | **Rất lãng phí:** Hàng triệu phép băm thử vô nghĩa để tìm Nonce | Tính Merkle root, băm header và ký ECDSA; không thử nonce |
| **Tiêu thụ năng lượng** | Phụ thuộc difficulty và phần cứng; demo chưa đo điện năng | Không đào nonce; mức tiêu thụ thực tế cần đo trên phần cứng |
| **Phần cứng yêu cầu** | Máy đào chuyên dụng giá đắt (ASIC, GPU công suất cao) | Máy tính thông thường của trường hoặc máy chủ cơ sở dữ liệu |
| **Rủi ro & Tấn công chính** | **51% Hashrate Attack:** Thâu tóm năng lực băm để ghi đè lịch sử | **Nothing at Stake, Ký kép (Double-Signing), Bắt tay ngầm (Cartel)** |
| **Cơ chế răn đe / Xử phạt** | Tiền điện và khấu hao phần cứng bị mất nếu đào chuỗi sai | **Slashing:** Tịch thu trực tiếp điểm ký quỹ và tước quyền phát hành |
| **Độ trễ xác nhận (Finality)** | Phụ thuộc độ khó và quy tắc xác nhận; demo có thể reorg | Ký số không cần đào; demo chưa có cơ chế finality hoặc giá trị pháp lý |
        """
    )

    st.divider()

    st.markdown("### 🔍 Vì sao PoS là lựa chọn tối ưu cho Mạng lưới Hồ sơ & Văn bằng số?")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("#### ❌ Hạn chế của PoW đối với hồ sơ học thuật/nghề nghiệp:")
        st.markdown(
            """
            - **Chi phí vận hành phi lý:** Không một trường đại học nào muốn chi hàng ngàn USD tiền điện mỗi tháng chỉ để xác nhận một tấm bằng tốt nghiệp cử nhân.
            - **Thời gian chờ đợi:** Sinh viên và nhà tuyển dụng cần xác thực hồ sơ tức thì, không thể chờ 10–60 phút để chuỗi giải xong câu đố băm.
            - **Không gắn với trách nhiệm pháp nhân:** Bất kỳ thợ đào ẩn danh nào có máy mạnh đều có thể tạo khối, không đảm bảo tính chính danh của tổ chức giáo dục.
            """
        )
    with col_r2:
        st.markdown("#### ✅ Ưu việt của Consortium PoS trong TRUSTMEBRO:")
        st.markdown(
            """
            - **Tính chính danh minh bạch:** Chỉ các trường được cấp phép (ĐH-A, ĐH-B, TC-C) mới được tham gia hội đồng đề xuất khối.
            - **Trách nhiệm giải trình cao (Slashing):** Trường nào cố tình ký 2 phiên bản hồ sơ mâu thuẫn sẽ bị tịch thu 50% điểm bảo chứng và đình chỉ cấp bằng trên mạng lưới.
            - **Tương thích bảo mật linh hoạt:** Kết hợp hoàn hảo với **Salted Merkle Tree** để giữ bí mật thông tin cá nhân của người học.
            """
        )

# ──────────────────────────────────────────────
# TAB 2: QUẢN TRỊ LIÊN MINH & TẠO KHỐI POS
# ──────────────────────────────────────────────
with tab2:
    st.subheader("🏛️ Quản trị Hội đồng Validator & Bầu chọn Tạo Khối")
    
    with st.expander("💡 **Giải thích Học thuật: 'Stake' là gì trong TRUSTMEBRO khi KHÔNG có Tiền ảo (No Coin)?**", expanded=False):
        st.markdown(
            """
            - **Vì sao không dùng Coin?** Các trường đại học (ĐH-A, ĐH-B) là đơn vị giáo dục công lập, 
              không giao dịch tiền mã hóa hay đầu cơ tài chính để chứng thực bằng cấp.
            - **Bản chất 'Stake' ở đây:** Là **Cổ phần Bảo chứng Uy tín (Reputation Stake)** và **Mức độ Đóng góp (Proof of Contribution)**.
            - **3 Mô hình định nghĩa Stake linh hoạt:**
              1. 🏛️ **Phân tầng Thẩm quyền (Static Tiered):** Gán điểm ban đầu theo kiểm định giáo dục (AUN-QA, ABET, Bộ GD&ĐT).
              2. 📜 **Tích lũy theo Cống hiến (Cumulative Merit):** Điểm tăng tự động theo **số lượng văn bằng hợp lệ** đã phát hành lên blockchain.
              3. ⚡ **Mô hình Lai ghép (Hybrid - Khuyến nghị):** Kết hợp uy tín pháp nhân ban đầu với số lượng hồ sơ thực tế đóng góp vào mạng lưới.
            - **Cơ chế Slashing:** Nếu ký 2 văn bằng mâu thuẫn (Nothing at Stake) hoặc phát hành văn bằng ma, tổ chức sẽ bị phạt tịch thu điểm bảo chứng và đình chỉ quyền tạo khối.
            """
        )

    first_n = list(network.nodes.values())[0]

    # Bộ chọn Mô hình Stake
    col_mode1, col_mode2 = st.columns([3, 1])
    with col_mode1:
        stake_mode_choice = st.radio(
            "🎯 **Lựa chọn Mô hình Tính Điểm 'Stake' cho Mạng lưới:**",
            [
                "⚡ Mô hình Lai ghép (Hybrid) — [Khuyến nghị]: Base Stake + (Số bằng hợp lệ × 15) - Slashing",
                "🏛️ Phân tầng Thẩm quyền Pháp nhân (Static Tiered): Dựa theo kiểm định trường (500 / 300 / 200 điểm)",
                "📜 Tích lũy theo Đóng góp Thực tế (Cumulative Merit): Điểm tính từ số Credential hợp lệ đã cấp on-chain",
            ],
            index=0,
            key="radio_stake_mode_selection",
        )
    with col_mode2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Quét lại Chuỗi Blockchain", key="btn_rescan_stake_chain"):
            pass

    # Xác định mode code
    if "Static Tiered" in stake_mode_choice:
        active_mode = "TIERED"
    elif "Cumulative Merit" in stake_mode_choice:
        active_mode = "CUMULATIVE"
    else:
        active_mode = "HYBRID"

    # Đồng bộ số lượng văn bằng thực tế từ Blockchain
    pos_reg.sync_with_blockchain(first_n.blockchain, mode=active_mode)

    # Hiển thị bảng Validator chi tiết
    val_rows = []
    tot_st = pos_reg.total_active_stake()
    for v in pos_reg.validators.values():
        pct = (v.stake / tot_st * 100) if tot_st > 0 else 0
        bonus_pts = v.credentials_issued * pos_reg.bonus_per_credential if active_mode != "TIERED" else 0
        val_rows.append({
            "Tổ chức Thành viên": v.name,
            "Phân loại Thẩm quyền": getattr(v, "institution_type", "Thành viên"),
            "Văn bằng Đã cấp (On-chain)": f"📜 {v.credentials_issued} hồ sơ",
            "Base Stake": f"{v.base_stake:,}",
            "Thưởng Đóng góp": f"+{bonus_pts:,}" if active_mode != "TIERED" else "— (Cố định)",
            "Đã bị phạt (Slash)": f"-{v.slashed_amount:,}" if v.slashed_amount > 0 else "0",
            "Stake Hiệu lực": f"⭐ {v.stake:,}",
            "Tỷ lệ Biểu quyết (%)": f"{pct:.1f}%",
            "Trạng thái": "🟢 Hoạt động" if v.is_active else "🔴 Đình chỉ",
        })
    st.table(val_rows)

    # Form thêm tổ chức mới vào liên minh
    with st.expander("➕ Đăng ký Thêm Tổ chức / Cơ sở Đào tạo vào Liên minh"):
        col_new1, col_new2 = st.columns(2)
        with col_new1:
            new_val_name = st.text_input("Tên Tổ chức:", value="Viện Đào tạo Mẫu (VĐT — Minh họa)", key="new_val_name")
            new_val_type = st.selectbox(
                "Phân loại tổ chức:",
                ["Đại học Trọng điểm", "Đại học Quốc gia", "Tổ chức Kiểm định & Doanh nghiệp", "Viện Đào tạo Quốc tế"],
                key="new_val_type",
            )
        with col_new2:
            new_val_stake = st.number_input("Điểm Cổ phần Ký quỹ (Base Stake):", min_value=50, max_value=2000, value=250, step=50, key="new_val_stake")
            new_val_desc = st.text_input("Mô tả trách nhiệm bảo chứng:", value="Đào tạo kỹ sư công nghệ thực hành & chứng chỉ nghề.", key="new_val_desc")

        if st.button("📝 Đăng ký Validator vào Mạng lưới", key="btn_register_val"):
            w_new = generate_wallet()
            pos_reg.register_validator(
                name=new_val_name,
                wallet=w_new,
                stake=new_val_stake,
                institution_type=new_val_type,
                reputation_score=96,
                description=new_val_desc,
            )
            pos_reg.sync_with_blockchain(first_n.blockchain, mode=active_mode)
            st.success(f"✅ Đã thêm '{new_val_name}' vào Hội đồng Liên minh TRUSTMEBRO!")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🎲 Trình diễn Bầu chọn & Ký Khối Minh họa")

    st.caption("Khối ở phần này chỉ để kiểm tra chữ ký; chưa được thêm vào mạng. Dùng trang Mining & Consensus Flow để phát hành lên chuỗi.")
    first_n = list(network.nodes.values())[0]
    default_h = first_n.height + 1
    default_prev = first_n.blockchain.get_latest_block().compute_hash()

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        sim_height = st.number_input("Chiều cao Block (Height):", min_value=1, max_value=1000, value=default_h, step=1, key="pos_height")
    with col_s2:
        sim_seed = st.number_input("Seed ngẫu nhiên cố định:", min_value=1, max_value=999999, value=network.consensus_seed, step=1, key="pos_seed")
    with col_s3:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_forge = st.button("🎲 Bầu chọn & Ký Khối PoS", key="btn_forge_pos_demo")

    if btn_forge:
        # Bầu chọn
        chosen = pos_reg.select_validator(height=sim_height, seed=sim_seed, previous_hash=default_prev)
        if not chosen:
            st.error("Không có validator hợp lệ trong mạng.")
        else:
            st.success(f"🏆 **Validator chính danh được thuật toán chọn:** **{chosen.name}** (`{chosen.address[:16]}…`)")

            # Thu thập giao dịch thực tế từ mempool hoặc mẫu
            pending_txs = first_n.mempool.get_transactions()
            if not pending_txs:
                # Tạo giao dịch mẫu bằng cấp
                w_demo = generate_wallet()
                cred_demo = Credential("DEMO-DEG-01", chosen.name, "Nguyen Van A", "BSc Software Engineering", "2026-06-01", {})
                tx_demo = Transaction("ISSUE", w_demo.public_key_hex, cred_demo.to_onchain_payload())
                tx_demo.sign(w_demo)
                tx_pack = [tx_demo]
                st.caption("ℹ️ Mempool trống — Tự động tạo 1 giao dịch cấp bằng cử nhân mẫu để đóng gói vào khối.")
            else:
                tx_pack = list(pending_txs[:5])
                st.caption(f"📦 Đang đóng gói {len(tx_pack)} giao dịch thực tế lấy từ Mempool.")

            # Tạo khối PoS
            block = pos_reg.forge_block(chosen, tx_pack, height=sim_height, previous_hash=default_prev)

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown("**Chi tiết Block Header (PoS):**")
                st.json({
                    "height": block.height,
                    "consensus_type": block.header.consensus_type,
                    "validator_address": block.header.validator_address,
                    "merkle_root": block.header.merkle_root[:24] + "…",
                    "previous_hash": block.header.previous_hash[:24] + "…",
                    "transaction_count": block.transaction_count,
                    "timestamp": block.header.timestamp,
                })
            with col_b2:
                st.markdown("**Kiểm tra Tính Chính danh & Chữ ký số:**")
                ok, reason = pos_reg.verify_pos_block(block, height=sim_height, seed=sim_seed, previous_hash=default_prev)
                if ok:
                    st.success(f"✅ {reason}")
                else:
                    st.error(f"❌ {reason}")

                st.markdown("**Chữ ký số ECDSA của Validator:**")
                st.code(block.header.validator_signature, language="text")

# ──────────────────────────────────────────────
# TAB 3: NOTHING AT STAKE & SLASHING
# ──────────────────────────────────────────────
with tab3:
    st.subheader("🚨 Mô phỏng Gian lận 'Nothing at Stake' (Ký kép) & Cơ chế Phạt Slashing")
    st.markdown(
        """
        **Bối cảnh nghiệp vụ văn bằng:**
        - Vì ký số khối PoS không cần đào nonce, một cơ sở đào tạo thiếu trung thực có thể cố tình tạo và ký **2 khối mâu thuẫn tại cùng một chiều cao** (ví dụ: Khối A cấp bằng cho người này, Khối B tại cùng height cấp bằng cho người khác).
        - **Phản ứng của mạng lưới:** Các node kiểm chứng đối chiếu hai chữ ký cùng chiều cao và thu được bằng chứng gian lận mật mã không thể chối cãi.
        - **Thực thi Slashing:** Giao thức lập tức **tịch thu tỷ lệ điểm bảo chứng** của trường đó và đình chỉ quyền đề xuất khối nếu điểm về 0!
        """
    )

    slash_candidates = [v for v in pos_reg.validators.values() if v.is_active and v.stake > 0]
    if not slash_candidates:
        st.warning("⚠️ Tất cả validator đã bị phạt hết điểm. Bấm **🔄 Khôi phục** bên dưới.")
    else:
        slash_names = [v.name for v in slash_candidates]
        sel_cheater_name = st.selectbox("Chọn Tổ chức để mô phỏng hành vi gian lận ký kép:", slash_names, key="cheater_sel")
        cheater = next(v for v in pos_reg.validators.values() if v.name == sel_cheater_name)

        col_atk1, col_atk2 = st.columns([2, 1])
        with col_atk1:
            st.markdown("#### 📊 Phân bổ điểm Bảo chứng Hiện tại:")
            chart_data = {v.name: v.stake for v in pos_reg.validators.values()}
            tot = sum(chart_data.values()) or 1
            for name, stk in chart_data.items():
                pct = stk / tot * 100
                bar_color = "🔴" if name == cheater.name else "🟢"
                st.markdown(
                    f"**{bar_color} {name[:28]}**  \n"
                    f"{'█' * max(1, int(pct / 3))} `{stk:,} điểm` ({pct:.1f}%)"
                )

        with col_atk2:
            st.markdown("#### ⚙️ Cấu hình hình phạt:")
            st.markdown(f"- **Tổ chức vi phạm:** `{cheater.name}`")
            st.markdown(f"- **Stake hiện tại:** `{cheater.stake:,}` điểm")
            st.markdown(f"- **Base Stake:** `{cheater.base_stake:,}` điểm")
            st.markdown(f"- **Đã bị phạt trước đó:** `{cheater.slashed_amount:,}` điểm")
            slash_rate = st.slider("Tỷ lệ phạt Slashing (%):", min_value=10, max_value=100, value=50, step=10, key="slash_slider") / 100.0
            slash_preview = int(cheater.stake * slash_rate)
            st.info(f"⚡ Sẽ phạt: **{slash_preview:,} điểm** → Còn lại: **{cheater.stake - slash_preview:,} điểm**")

        st.markdown("---")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            btn_attack = st.button("🔴 Thực hiện Ký Kép & Kích hoạt Slashing", key="btn_slash_run", type="primary")
        with col_btn2:
            st.markdown("")

        if btn_attack:
            # Tạo Block 1A và 1B (cùng height 10, nội dung khác nhau)
            b1 = pos_reg.forge_block(cheater, transactions=[], height=10, previous_hash="hash_chain_branch_A")
            b2 = pos_reg.forge_block(cheater, transactions=[], height=10, previous_hash="hash_chain_branch_B")

            st.markdown("#### 📋 Bằng chứng Mật mã Vi phạm Thu thập được:")
            st.code(
                f"[BLOCK A - Height 10] Hash: {b1.compute_hash()[:40]}…\n"
                f"  Ký bởi: {cheater.name}\n"
                f"  Chữ ký A: {b1.header.validator_signature[:56]}…\n\n"
                f"[BLOCK B - Height 10] Hash: {b2.compute_hash()[:40]}…\n"
                f"  Ký bởi: {cheater.name}\n"
                f"  Chữ ký B: {b2.header.validator_signature[:56]}…\n\n"
                f"⚠️ Cùng Validator, cùng Height, 2 chữ ký KHÁC NHAU → VI PHẠM ĐÃ ĐƯỢC CHỨNG MINH!",
                language="text"
            )

            slashed, msg, report = pos_reg.detect_and_slash(b1, b2, slash_ratio=slash_rate)

            if slashed:
                st.error(f"### 🚨 {msg}")
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    st.markdown("**📋 Báo cáo Chi tiết Slashing:**")
                    st.json(report)
                with col_r2:
                    st.markdown("**📉 Trực quan Mức Phạt:**")
                    old_stk = report["old_stake"]
                    slashed_amt = report["slashed_amount"]
                    remaining = report["remaining_stake"]
                    st.markdown(f"- **Stake trước:** `{old_stk:,}` điểm")
                    st.markdown(f"- **Bị tịch thu:** `🔴 -{slashed_amt:,}` điểm ({int(slash_rate * 100)}%)")
                    st.markdown(f"- **Stake còn lại:** `{'🔴 0 (Đình chỉ)' if remaining <= 0 else f'🟡 {remaining:,}'}`")
                    if not report["is_active"]:
                        st.error("🚫 **Tổ chức đã bị ĐÌnh chỉ hoàn toàn!** Mất quyền tham gia Hội đồng Liên minh.")
                    else:
                        st.warning("⚠️ Tổ chức còn điểm nhưng đã bị cảnh cáo. Thêm vi phạm sẽ bị loại hoàn toàn.")
                st.rerun()

    st.markdown("---")
    if st.button("🔄 Khôi phục Stake Hội đồng về Mặc định", key="btn_reset_pos"):
        pos_reg.reset_demo_stakes()
        st.success("✅ Đã khôi phục điểm stake; giữ nguyên validator, khóa và các block đã tạo.")
        st.rerun()

# ──────────────────────────────────────────────
# TAB 4: SO SÁNH PoW vs PoS — BIỂU ĐỒ TRỰC QUAN
# ──────────────────────────────────────────────
with tab4:
    st.subheader("⚡ Live Benchmark & So sánh Trực quan PoW vs PoS")
    st.caption("Đo thời gian tạo khối rỗng trên máy đang chạy và số lần thử nonce PoW. Không đo điện năng, độ trễ mạng hay thông lượng giao dịch.")

    col_cfg1, col_cfg2 = st.columns([2, 1])
    with col_cfg1:
        bench_diff = st.slider("Độ khó PoW (Difficulty — số lượng số 0 dẫn đầu):", min_value=2, max_value=5, value=3, key="bench_diff")
        bench_rounds = st.slider("Số vòng mô phỏng (Rounds):", min_value=3, max_value=8, value=6, key="bench_rounds")
    with col_cfg2:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_bench = st.button("🚀 Chạy Benchmark So sánh", key="btn_run_bench", type="primary")

    if btn_bench:
        v_bench = list(pos_reg.validators.values())[0]

        pow_times_ms = []
        pos_times_ms = []
        pow_hashes = []

        prog = st.progress(0, text="Đang đo lường…")
        for rnd in range(bench_rounds):
            prog.progress((rnd + 1) / bench_rounds, text=f"Vòng {rnd + 1}/{bench_rounds}…")

            # --- PoW ---
            t0 = time.perf_counter()
            block_pow = Block(transactions=[], height=rnd + 1, previous_hash="0" * 64, difficulty=bench_diff)
            pow_res = mine_block(block_pow)
            pow_ms = (time.perf_counter() - t0) * 1000
            pow_times_ms.append(pow_ms)
            pow_hashes.append(pow_res["attempts"])

            # --- PoS ---
            t0 = time.perf_counter()
            pos_reg.forge_block(v_bench, transactions=[], height=rnd + 1, previous_hash="0" * 64)
            pos_ms = (time.perf_counter() - t0) * 1000
            pos_times_ms.append(pos_ms)

        prog.empty()

        avg_pow_ms = round(sum(pow_times_ms) / len(pow_times_ms), 2)
        avg_pos_ms = round(sum(pos_times_ms) / len(pos_times_ms), 2)
        total_pow_hashes = sum(pow_hashes)

        # ── Metrics ──
        st.markdown("### 📊 Kết quả Tổng hợp")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("TB Thời gian PoW", f"{avg_pow_ms:,.1f} ms")
        mc2.metric("TB Thời gian PoS", f"{avg_pos_ms:.2f} ms")
        mc3.metric("Tổng lần thử nonce PoW", f"{total_pow_hashes:,}")

        st.divider()

        # ── BIỂU ĐỒ 1: So sánh đa chỉ số ──
        st.markdown("#### 📊 Biểu đồ 1: So sánh Tổng quan PoW vs PoS")
        try:
            import plotly.graph_objects as go
            categories = ["Khối tạo", "TB thời gian (ms)"]
            pow_vals = [bench_rounds, avg_pow_ms]
            pos_vals = [bench_rounds, avg_pos_ms]

            fig_compare = go.Figure()
            fig_compare.add_trace(go.Bar(
                name="PoW",
                x=categories,
                y=pow_vals,
                marker_color="#f59e0b",
                text=[str(v) for v in pow_vals],
                textposition="auto",
            ))
            fig_compare.add_trace(go.Bar(
                name="PoS",
                x=categories,
                y=pos_vals,
                marker_color="#10b981",
                text=[str(v) for v in pos_vals],
                textposition="auto",
            ))
            fig_compare.update_layout(
                barmode="group",
                title="So sánh PoW vs PoS",
                paper_bgcolor="#1e1e2e",
                plot_bgcolor="#1e1e2e",
                font=dict(color="white"),
                legend=dict(bgcolor="#2a2a3e"),
                yaxis=dict(gridcolor="#3a3a4e"),
            )
            st.plotly_chart(fig_compare, use_container_width=True)
        except ImportError:
            pass

        st.divider()

        # ── BIỂU ĐỒ 2: Thời gian tạo khối theo vòng (Line chart) ──
        st.markdown("#### 📈 Biểu đồ 2: Thời gian tạo khối theo vòng (ms)")
        try:
            rounds_x = list(range(1, bench_rounds + 1))
            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(
                x=rounds_x,
                y=pow_times_ms,
                mode="lines+markers",
                name="PoW",
                line=dict(color="#f59e0b", width=2),
                marker=dict(size=7, symbol="circle"),
            ))
            fig_line.add_trace(go.Scatter(
                x=rounds_x,
                y=pos_times_ms,
                mode="lines+markers",
                name="PoS",
                line=dict(color="#10b981", width=2),
                marker=dict(size=7, symbol="circle"),
            ))
            fig_line.update_layout(
                title="Thời gian tạo khối theo vòng (ms)",
                xaxis_title="Vòng (Round)",
                yaxis_title="Thời gian (ms)",
                paper_bgcolor="#1e1e2e",
                plot_bgcolor="#1e1e2e",
                font=dict(color="white"),
                legend=dict(bgcolor="#2a2a3e"),
                xaxis=dict(gridcolor="#3a3a4e", dtick=1),
                yaxis=dict(gridcolor="#3a3a4e"),
            )
            st.plotly_chart(fig_line, use_container_width=True)
        except ImportError:
            st.line_chart({"PoW (ms)": pow_times_ms, "PoS (ms)": pos_times_ms})

        st.success(
            f"✅ **Kết luận:** Trong {bench_rounds} vòng đo lường:\n"
            f"- PoW tốn trung bình **{avg_pow_ms:,.1f} ms** và **{total_pow_hashes:,} phép băm** tổng cộng.\n"
            f"- PoS tạo và ký khối trung bình **{avg_pos_ms:.2f} ms**.\n"
            "- Chưa đo điện năng nên không kết luận phần trăm tiết kiệm điện."
        )


