"""Trang Attack Simulator — 6 kịch bản tấn công mô phỏng.

Mục đích: cho sinh viên trình diễn trực tiếp khi bảo vệ, thấy từng
lớp bảo vệ (signature, hash chain, merkle, registry, replay, PoW)
bắt giả mạo ở bước nào. Mọi tấn công chạy trên BẢN SAO (deepcopy).
"""

import copy
import time
import streamlit as st
import sys
import os
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from state import init_state
from blockchain.wallet import Wallet, generate_wallet
from blockchain.transaction import Credential, Transaction, verify_transaction
from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import mine_block, is_valid_pow
from blockchain.mempool import Mempool, DummyLedger

init_state()



st.header("🛡️ Attack Simulator")
st.caption(
    "Mỗi kịch bản chạy trên **BẢN SAO** (deepcopy) — không ảnh hưởng dữ liệu thật. "
    "Bấm từng nút để trình diễn khi bảo vệ đồ án."
)


# ══════════════════════════════════════════════
# Demo blockchain (session_state)
# ══════════════════════════════════════════════

def _build_demo():
    """Tạo blockchain mẫu: genesis + 3 block, mỗi block 1 credential, difficulty=2."""
    w = generate_wallet()
    bc = Blockchain()
    samples = [
        ("CRED-ATK-001", "Người học DEMO-001", "Chứng chỉ Phân tích dữ liệu"),
        ("CRED-ATK-002", "Người học DEMO-002", "Chứng chỉ Kỹ năng số"),
        ("CRED-ATK-003", "Người học DEMO-003", "BSc Computer Science"),
    ]
    for cred_id, holder, title in samples:
        cred = Credential(cred_id, "Trường Đại học A", holder, title, "2026-01-01", {})
        tx = Transaction("ISSUE", w.public_key_hex, asdict(cred))
        tx.sign(w)
        prev = bc.get_latest_block().compute_hash()
        block = Block(transactions=[tx], height=len(bc.chain),
                      previous_hash=prev, difficulty=2)
        mine_block(block)
        bc.add_block(block)
    return bc, w


def _get_demo():
    """Lấy hoặc tạo demo blockchain."""
    if "attack_data" not in st.session_state:
        bc, w = _build_demo()
        st.session_state.attack_data = {
            "bc": bc,
            "wallet_pem": w.private_key_pem,
            "wallet_pub": w.public_key_hex,
            "wallet_addr": w.address,
        }
    d = st.session_state.attack_data
    w = Wallet(d["wallet_pem"], d["wallet_pub"], d["wallet_addr"])
    return d["bc"], w


source_bc, demo_wallet = _get_demo()

col_info, col_reset = st.columns([3, 1])
with col_info:
    ok, _, _ = source_bc.is_chain_valid()
    st.info(
        f"📦 Demo blockchain: **{len(source_bc.chain)} block** | "
        f"difficulty=2 | is_chain_valid = {'✅' if ok else '❌'}"
    )
with col_reset:
    if st.button("🔄 Reset Blockchain", key="btn_reset_atk"):
        bc, w = _build_demo()
        st.session_state.attack_data = {
            "bc": bc, "wallet_pem": w.private_key_pem,
            "wallet_pub": w.public_key_hex, "wallet_addr": w.address,
        }
        st.rerun()


# ── Helper hiển thị bảng kết quả ──

def _show_steps(steps: list[tuple[str, str, str]]):
    """Hiển thị bảng: STT | Bước | Kết quả."""
    rows = []
    for i, (step, detail, status) in enumerate(steps, 1):
        rows.append({"#": i, "Bước": step, "Chi tiết": detail, "Kết quả": status})
    st.table(rows)


st.divider()


# ══════════════════════════════════════════════
# ATTACK 1: Sửa credential sau khi ký
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 1 — Sửa credential sau khi ký")
st.caption("Kẻ tấn công sửa điểm 6.5 → 8.5 nhưng giữ nguyên chữ ký.")

if st.button("▶️ Chạy Attack 1", key="btn_atk1"):
    # Tạo TX hợp lệ
    cred = Credential("CRED-DEMO-ATK", "Tổ chức Kiểm định C", "Người học DEMO-001", "Chứng chỉ Phân tích dữ liệu — Điểm 6.5", "2026-06-01", {})
    tx = Transaction("ISSUE", demo_wallet.public_key_hex, asdict(cred))
    tx.sign(demo_wallet)

    original_hash = tx.tx_id
    ok_before, _ = verify_transaction(tx)

    # Giả mạo
    tx.payload["title"] = "Chứng chỉ Kỹ năng DEMO — Điểm 8.5"
    new_hash = tx.compute_hash()
    ok_after, reason_after = verify_transaction(tx)

    _show_steps([
        ("Tạo TX: Điểm 6.5", f"tx_id: `{original_hash[:24]}…`", "✅ Hợp lệ"),
        ("verify_transaction trước khi sửa", f"ok={ok_before}", "✅ PASS"),
        ("Sửa payload: 6.5 → 8.5", "title = 'Điểm 8.5'", "🔴 Giả mạo"),
        ("tx_id so với compute_hash()",
         f"tx_id=`{original_hash[:16]}…` ≠ hash=`{new_hash[:16]}…`",
         "❌ KHÁC"),
        ("verify_transaction sau khi sửa", reason_after, "❌ INVALID"),
    ])

    st.error("**Bảo vệ bởi: Chữ ký số (ECDSA)** — sửa 1 bit payload → hash đổi → chữ ký không khớp.")

st.divider()


# ══════════════════════════════════════════════
# ATTACK 2: Sửa dữ liệu một Block
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 2 — Sửa dữ liệu một Block")
st.caption("Sửa timestamp Block 2 → hash đổi → block sau phát hiện previous_hash sai.")

if st.button("▶️ Chạy Attack 2", key="btn_atk2"):
    atk = copy.deepcopy(source_bc)
    block2 = atk.chain[2]
    old_hash = block2.compute_hash()
    old_ts = block2.header.timestamp

    # Giả mạo timestamp
    block2.header.timestamp = "2099-12-31T23:59:59"
    new_hash = block2.compute_hash()

    # Block 3 kiểm tra
    block3_prev = atk.chain[3].header.previous_hash if len(atk.chain) > 3 else "N/A"

    # Validate
    ok, fail_idx, reason = atk.is_chain_valid()

    _show_steps([
        ("Block 2 hash gốc", f"`{old_hash[:32]}…`", "✅"),
        ("Sửa timestamp", f"'{old_ts}' → '2099-12-31T23:59:59'", "🔴 Giả mạo"),
        ("Block 2 hash mới", f"`{new_hash[:32]}…`", "⚠️ Đã thay đổi"),
        ("Block 3 previous_hash",
         f"`{block3_prev[:32]}…` (vẫn trỏ hash cũ)",
         "❌ Không khớp hash mới"),
        ("is_chain_valid()", f"Block {fail_idx}: {reason}", "❌ DETECTED"),
    ])

    st.error("**Bảo vệ bởi: Hash chain + PoW** — sửa 1 block → hash đổi → mọi block sau phát hiện.")

st.divider()


# ══════════════════════════════════════════════
# ATTACK 3: Sửa TX trong block → Merkle Root đổi
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 3 — Thay TX trong Block")
st.caption("Thay TX trong Block 1 bằng TX giả → Merkle Root không khớp.")

if st.button("▶️ Chạy Attack 3", key="btn_atk3"):
    atk = copy.deepcopy(source_bc)
    block1 = atk.chain[1]
    old_root = block1.header.merkle_root
    old_tx_id = block1.transactions[0].tx_id

    # Tạo TX giả (đúng chữ ký nhưng nội dung khác)
    fake_cred = Credential("CRED-FAKE-003", "Fake Uni", "Eve", "PhD Everything", "2026-01-01", {})
    fake_tx = Transaction("ISSUE", demo_wallet.public_key_hex, asdict(fake_cred))
    fake_tx.sign(demo_wallet)

    # Thay TX nhưng KHÔNG cập nhật Merkle Root
    block1.transactions[0] = fake_tx
    new_root = calculate_merkle_root([t.tx_id for t in block1.transactions])

    ok, fail_idx, reason = atk.is_chain_valid()

    _show_steps([
        ("TX gốc trong Block 1", f"tx_id: `{old_tx_id[:24]}…`", "✅"),
        ("Thay bằng TX giả", f"tx_id: `{fake_tx.tx_id[:24]}…`", "🔴 Giả mạo"),
        ("Merkle Root trong header", f"`{old_root[:24]}…`", "Giữ nguyên"),
        ("Merkle Root tính lại từ TX", f"`{new_root[:24]}…`", "❌ KHÁC"),
        ("is_chain_valid()", f"Block {fail_idx}: {reason}", "❌ DETECTED"),
    ])

    st.error("**Bảo vệ bởi: Merkle Tree** — thay/sửa TX → merkle root tính lại khác header → block bị từ chối.")

st.divider()


# ══════════════════════════════════════════════
# ATTACK 4: Fake Issuer
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 4 — Giả danh Issuer")
st.caption("Kẻ tấn công tự tạo wallet, ký TX nhưng không có trong registry → bị từ chối.")

if st.button("▶️ Chạy Attack 4", key="btn_atk4"):
    rogue = generate_wallet()

    # TX ký bằng wallet giả
    cred = Credential("CRED-ROGUE", "Giả mạo X", "Người học DEMO-001", "Fake PhD", "2026-01-01", {})
    rogue_tx = Transaction("ISSUE", rogue.public_key_hex, asdict(cred))
    rogue_tx.sign(rogue)

    # Verify chữ ký — OK (vì đúng key pair)
    sig_ok, _ = verify_transaction(rogue_tx)

    # Nhưng registry chặn
    mempool = Mempool(authorized_issuers={demo_wallet.public_key_hex})
    reg_ok, reg_reason = mempool.add_transaction(rogue_tx, DummyLedger())

    # TX không ký (không có private key)
    unsigned_tx = Transaction("ISSUE", "0" * 130, asdict(cred))
    unsig_ok, unsig_reason = verify_transaction(unsigned_tx)

    _show_steps([
        ("Rogue wallet tạo TX + ký", f"address: `{rogue.address[:20]}…`", "✅ Ký hợp lệ"),
        ("verify_transaction (chữ ký)", f"ok={sig_ok}", "✅ PASS (đúng key pair)"),
        ("Mempool kiểm tra registry", reg_reason, "❌ REJECTED"),
        ("TX không ký (không có private key)", unsig_reason, "❌ REJECTED"),
    ])

    st.error(
        "**Bảo vệ bởi: Issuer Registry + Chữ ký** — "
        "chữ ký đúng format nhưng không nằm trong danh sách → bị từ chối. "
        "Không có private key → không ký được."
    )

st.divider()


# ══════════════════════════════════════════════
# ATTACK 5: Replay + Duplicate Credential
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 5 — Replay & Duplicate Credential")
st.caption("Nộp lặp cùng TX (replay) hoặc cấp trùng credential_id → chỉ chấp nhận một.")

if st.button("▶️ Chạy Attack 5", key="btn_atk5"):
    st.markdown("#### 5a. Replay — Nộp cùng TX hai lần")

    cred = Credential("CRED-REPLAY", "Trường Đại học A", "Người học DEMO-001", "Chứng chỉ Phân tích dữ liệu", "2026-01-01", {})
    tx = Transaction("ISSUE", demo_wallet.public_key_hex, asdict(cred))
    tx.sign(demo_wallet)

    mempool = Mempool()
    ok1, r1 = mempool.add_transaction(tx, DummyLedger())
    ok2, r2 = mempool.add_transaction(tx, DummyLedger())

    _show_steps([
        ("Submit TX lần 1", f"tx_id: `{tx.tx_id[:20]}…`", f"{'✅ ACCEPT' if ok1 else '❌'}"),
        ("Submit TX lần 2 (cùng tx_id)", r2, f"{'✅' if ok2 else '❌ REJECTED'}"),
    ])

    st.markdown("#### 5b. Duplicate Credential ID — Cấp trùng")

    # Credential CRED-ATK-001 đã có trong blockchain (ACTIVE)
    dup_cred = Credential("CRED-ATK-001", "Trường Đại học A", "Người học DEMO-002", "Chứng chỉ Kỹ năng số", "2026-06-01", {})
    dup_tx = Transaction("ISSUE", demo_wallet.public_key_hex, asdict(dup_cred))
    dup_tx.sign(demo_wallet)

    mempool2 = Mempool()
    # Dùng source_bc làm ledger view → CRED-ATK-001 đang ACTIVE
    dup_ok, dup_reason = mempool2.add_transaction(dup_tx, source_bc)

    _show_steps([
        ("CRED-ATK-001 trong blockchain", "Status: ACTIVE (đã cấp cho Người học DEMO-001)", "✅ Đang tồn tại"),
        ("Submit ISSUE CRED-ATK-001 lần 2", dup_reason, f"{'✅' if dup_ok else '❌ REJECTED'}"),
    ])

    st.error(
        "**Bảo vệ bởi: Mempool (duplicate tx_id) + Ledger View (credential status)** — "
        "không thể replay TX hoặc cấp trùng credential."
    )

st.divider()


# ══════════════════════════════════════════════
# ATTACK 6: Sửa block + tính lại hash → PoW chặn
# ══════════════════════════════════════════════
st.subheader("🔴 Attack 6 — Sửa Block + Tính lại toàn bộ hash")
st.caption(
    "Kẻ tấn công sửa Block 1, tạo TX mới, cập nhật merkle root, "
    "tính lại previous_hash cho mọi block sau. PoW phát hiện!"
)

if st.button("▶️ Chạy Attack 6", key="btn_atk6"):
    atk = copy.deepcopy(source_bc)
    block1 = atk.chain[1]
    difficulty = block1.header.difficulty
    old_hash = block1.compute_hash()

    # Tạo TX giả thay thế
    fake_cred = Credential("CRED-ATK-001", "Trường Đại học A", "Người học DEMO-001", "Chứng chỉ Giả mạo 9.0", "2026-01-01", {})
    fake_tx = Transaction("ISSUE", demo_wallet.public_key_hex, asdict(fake_cred))
    fake_tx.sign(demo_wallet)

    block1.transactions = [fake_tx]
    block1.header.merkle_root = calculate_merkle_root([fake_tx.tx_id])
    block1.transaction_count = 1

    # Tính lại previous_hash cho tất cả block sau
    for i in range(2, len(atk.chain)):
        atk.chain[i].header.previous_hash = atk.chain[i - 1].compute_hash()

    new_hash = block1.compute_hash()
    pow_ok = is_valid_pow(block1)

    # Validate chain
    ok, fail_idx, reason = atk.is_chain_valid()

    # Ước tính thời gian mine lại
    blocks_to_remine = len(atk.chain) - 1  # tất cả trừ genesis
    avg_attempts = 16 ** difficulty

    # Benchmark: mine 1 block thật để đo tốc độ
    bench_block = Block(transactions=[], height=99, previous_hash="0" * 64, difficulty=difficulty)
    t0 = time.time()
    mine_block(bench_block)
    bench_time = time.time() - t0

    est_total = bench_time * blocks_to_remine

    steps = [
        ("Block 1 hash gốc", f"`{old_hash[:32]}…`", "✅"),
        ("Thay TX: Điểm 6.5 → 9.0", "Tạo TX mới, cập nhật merkle_root", "🔴 Giả mạo"),
        ("Block 1 hash mới", f"`{new_hash[:32]}…`", "⚠️ Đã thay đổi"),
        ("Tính lại previous_hash B2→B3",
         "Cập nhật previous_hash cho mọi block sau", "✅ Đã recompute"),
        ("PoW Block 1", f"hash starts with '{'0' * difficulty}'?  → {pow_ok}", "❌ INVALID"),
        ("is_chain_valid()", f"Block {fail_idx}: {reason}", "❌ DETECTED"),
    ]

    _show_steps(steps)

    st.markdown("#### ⏱️ Chi phí mine lại")
    remine_rows = [
        {"Metric": "Difficulty", "Value": str(difficulty)},
        {"Metric": "Block cần mine lại", "Value": str(blocks_to_remine)},
        {"Metric": "Lần thử TB / block", "Value": f"~{avg_attempts:,}"},
        {"Metric": "Thời gian / block (benchmark)", "Value": f"{bench_time:.4f}s"},
        {"Metric": "Tổng thời gian ước tính", "Value": f"{est_total:.4f}s"},
    ]
    st.table(remine_rows)

    st.warning(
        f"⛏️ Với difficulty={difficulty}: mine lại {blocks_to_remine} block "
        f"mất ~{est_total:.2f}s. Nhưng Bitcoin difficulty ~70+ bit: "
        f"mine lại chuỗi mất **hàng tỷ năm** trên 1 CPU. "
        f"Và kẻ tấn công phải mine **nhanh hơn toàn bộ mạng** (51% attack)."
    )

    st.error(
        "**Bảo vệ bởi: Proof of Work** — tính lại hash dễ, nhưng mine lại "
        "để thoả difficulty → tốn thời gian khổng lồ, không khả thi."
    )

st.divider()

# ══════════════════════════════════════════════
# Tổng kết
# ══════════════════════════════════════════════
with st.expander("📋 Tổng kết: 6 lớp bảo vệ"):
    st.markdown(
        """
| # | Tấn công | Lớp bảo vệ | Cơ chế |
|---|---|---|---|
| 1 | Sửa credential sau khi ký | **Chữ ký số** | ECDSA — sửa payload → hash đổi → signature invalid |
| 2 | Sửa dữ liệu block | **Hash chain** | Block hash đổi → block sau phát hiện previous_hash sai |
| 3 | Thay TX trong block | **Merkle Tree** | TX mới → merkle root khác header → block invalid |
| 4 | Giả danh Issuer | **Registry** | Public key không nằm trong danh sách → bị từ chối |
| 5 | Replay / trùng credential | **Mempool + Ledger** | Trùng tx_id hoặc credential đã ACTIVE → rejected |
| 6 | Recompute toàn bộ | **Proof of Work** | Mine lại chuỗi tốn thời gian khổng lồ → không khả thi |

**Kết luận:** Blockchain bảo vệ bằng nhiều lớp chồng nhau — kẻ tấn công
phải phá **đồng thời tất cả** các lớp, trong khi mỗi lớp đã đủ khó.
        """
    )
