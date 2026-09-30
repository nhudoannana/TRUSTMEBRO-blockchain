"""Tests cho module blockchain/pos.py.

Kiểm tra:
- Chọn Validator ngẫu nhiên có trọng số theo stake: P(v) ~ stake(v).
- Tính lặp lại được (deterministic / reproducible) với seed cố định.
- Ký khối PoS và xác minh chữ ký số ECDSA.
- Từ chối khối do Validator không chính danh ký.
- Từ chối khối khi chữ ký bị làm giả hoặc dữ liệu bị can thiệp.
- Phát hiện tấn công 'Nothing at Stake' (ký kép cùng height) và thực thi Slashing chính xác.
- Ký các block ở khác height không bị coi là vi phạm.
"""

from blockchain.wallet import generate_wallet
from blockchain.pos import PoSRegistry, Validator


def _setup_registry():
    """Helper: tạo registry với 3 validator có tỷ lệ stake 50% - 30% - 20%."""
    reg = PoSRegistry()
    w1 = generate_wallet()
    w2 = generate_wallet()
    w3 = generate_wallet()

    v1 = reg.register_validator("Validator-Alpha", w1, stake=500)
    v2 = reg.register_validator("Validator-Beta", w2, stake=300)
    v3 = reg.register_validator("Validator-Gamma", w3, stake=200)

    return reg, (v1, v2, v3)


def test_deterministic_weighted_selection():
    """Seed cố định phải cho ra kết quả chọn giống hệt nhau 100%."""
    reg, (v1, v2, v3) = _setup_registry()

    # Cùng seed, cùng height -> phải chọn ra cùng 1 validator
    chosen_1 = reg.select_validator(height=1, seed=42, previous_hash="0"*64)
    chosen_2 = reg.select_validator(height=1, seed=42, previous_hash="0"*64)
    assert chosen_1 is not None
    assert chosen_1.address == chosen_2.address

    # Thống kê phân phối: chạy 1,000 lần với seed khác nhau để kiểm tra tỷ lệ
    counts = {v1.name: 0, v2.name: 0, v3.name: 0}
    for seed_i in range(1000):
        c = reg.select_validator(height=1, seed=seed_i)
        counts[c.name] += 1

    # v1 (50%) phải được chọn nhiều nhất, v2 (30%) nhì, v3 (20%) ba
    assert counts["Validator-Alpha"] > counts["Validator-Beta"]
    assert counts["Validator-Beta"] > counts["Validator-Gamma"]


def test_pos_block_forging_and_verification():
    """Validator chính danh tạo block và node xác minh thành công."""
    reg, (v1, v2, v3) = _setup_registry()

    # Xác định ai được chọn tại height=1, seed=100
    chosen = reg.select_validator(height=1, seed=100, previous_hash="prev_hash_123")
    assert chosen is not None

    # Chosen validator tạo và ký block
    block = reg.forge_block(chosen, transactions=[], height=1, previous_hash="prev_hash_123")

    assert block.header.consensus_type == "PoS"
    assert block.header.validator_address == chosen.address
    assert len(block.header.validator_signature) > 64

    # Node xác minh block
    ok, reason = reg.verify_pos_block(block, height=1, seed=100, previous_hash="prev_hash_123")
    assert ok is True
    assert "Hợp lệ" in reason


def test_unauthorized_proposer_rejected():
    """Validator không được chọn mà tự ý tạo block thì bị node từ chối."""
    reg, (v1, v2, v3) = _setup_registry()

    chosen = reg.select_validator(height=1, seed=100)
    unauthorized = v2 if chosen.address == v1.address else v1

    # Unauthorized validator cố tình tạo block
    fake_block = reg.forge_block(unauthorized, transactions=[], height=1, previous_hash="")

    ok, reason = reg.verify_pos_block(fake_block, height=1, seed=100, previous_hash="")
    assert ok is False
    assert "không chính danh" in reason


def test_tampered_pos_block_rejected():
    """Sửa dữ liệu header sau khi ký -> chữ ký không khớp, bị từ chối."""
    reg, (v1, v2, v3) = _setup_registry()

    chosen = reg.select_validator(height=1, seed=42, previous_hash="genesis_hash")
    block = reg.forge_block(chosen, transactions=[], height=1, previous_hash="genesis_hash")

    # Kẻ gian sửa previous_hash sau khi block đã được ký
    block.header.previous_hash = "hacked_hash"

    ok, reason = reg.verify_pos_block(block, height=1, seed=42, previous_hash="genesis_hash")
    assert ok is False
    assert "không hợp lệ" in reason


def test_slashing_on_double_signing():
    """Validator ký 2 block khác nhau tại cùng height -> Bị Slash 50% stake."""
    reg, (v1, v2, v3) = _setup_registry()

    initial_stake = v1.stake  # 500

    # Validator 1 ký Block A tại height 5
    block_a = reg.forge_block(v1, transactions=[], height=5, previous_hash="hash_a")

    # Validator 1 ký thêm Block B tại height 5 (nội dung khác)
    block_b = reg.forge_block(v1, transactions=[], height=5, previous_hash="hash_b")

    # Kích hoạt phát hiện vi phạm và xử phạt
    slashed, msg, report = reg.detect_and_slash(block_a, block_b, slash_ratio=0.5)

    assert slashed is True
    assert "SLASHING THÀNH CÔNG" in msg
    assert report["slashed_amount"] == 250
    assert v1.stake == 250
    assert v1.slashed_amount == 250


def test_honest_validator_different_heights_not_slashed():
    """Ký 2 block ở 2 height khác nhau (hoạt động bình thường) không bị coi là vi phạm."""
    reg, (v1, v2, v3) = _setup_registry()

    block_h1 = reg.forge_block(v1, transactions=[], height=1, previous_hash="hash_0")
    block_h2 = reg.forge_block(v1, transactions=[], height=2, previous_hash="hash_1")

    slashed, msg, _ = reg.detect_and_slash(block_h1, block_h2)
    assert slashed is False
    assert "khác height" in msg
    assert v1.stake == 500
