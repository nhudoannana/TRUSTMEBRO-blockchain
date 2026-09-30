"""Tests cho các mô hình tính Stake trong TrustProfile Consortium:
- Mô hình 1: Static Tiered Institutional Reputation (Phân tầng thẩm quyền trường/tổ chức).
- Mô hình 2: Cumulative Merit (Tích luỹ theo số lượng Credential hợp lệ đã phát hành trên chuỗi).
- Mô hình 3: Hybrid (Lai ghép giữa Base Stake + Thưởng cống hiến văn bằng - Phạt Slashing).
"""

from blockchain.wallet import generate_wallet
from blockchain.pos import PoSRegistry, Validator, create_trustprofile_consortium
from blockchain.transaction import Credential, Transaction
from blockchain.blockchain import Blockchain


from blockchain.block import Block


def test_static_tiered_stake_model():
    """Mô hình 1: Stake dựa trên phân tầng uy tín pháp nhân của tổ chức."""
    reg = PoSRegistry(default_mode="TIERED")
    w1 = generate_wallet()
    w2 = generate_wallet()

    # ĐHQG: 500 điểm, Trung tâm tin học: 100 điểm
    v1 = reg.register_validator("ĐH Quốc Gia", w1, stake=500, institution_type="Đại học Quốc gia")
    v2 = reg.register_validator("Trung tâm Tin học X", w2, stake=100, institution_type="Trung tâm Đào tạo")

    assert reg.get_effective_stake(v1, mode="TIERED") == 500
    assert reg.get_effective_stake(v2, mode="TIERED") == 100
    assert reg.total_active_stake() == 600


def test_cumulative_merit_stake_sync_from_blockchain():
    """Mô hình 2: Stake tăng tự động theo số lượng credential hợp lệ trên blockchain."""
    reg = PoSRegistry(default_mode="CUMULATIVE", bonus_per_credential=20)
    w_bk = generate_wallet()
    w_tt = generate_wallet()

    v_bk = reg.register_validator("🏛️ Trường Đại học A", w_bk, stake=500)
    v_tt = reg.register_validator("Trung tâm Tin học X", w_tt, stake=100)

    # Khởi tạo blockchain với các giao dịch cấp bằng
    bc = Blockchain()

    # Trường ĐH-A phát hành 3 bằng
    for i in range(3):
        cred = Credential(
            credential_id=f"DEG-BK-{i}",
            issuer_name="Trường Đại học A",
            holder_name=f"Sinh vien {i}",
            title="Kỹ sư CNTT",
            issue_date="2026-06-01",
        )
        tx = Transaction("ISSUE", w_bk.public_key_hex, cred.to_onchain_payload())
        tx.sign(w_bk)
        b = Block(
            transactions=[tx],
            height=len(bc.chain),
            previous_hash=bc.get_latest_block().compute_hash(),
            consensus_type="PoS",
            validator_address=v_bk.address,
        )
        bc.add_block(b)

    # Trung tâm X phát hành 1 chứng chỉ
    cred_x = Credential(
        credential_id="CERT-X-01",
        issuer_name="Trung tâm Tin học X",
        holder_name="Hoc vien B",
        title="Chứng chỉ Python",
        issue_date="2026-06-01",
    )
    tx_x = Transaction("ISSUE", w_tt.public_key_hex, cred_x.to_onchain_payload())
    tx_x.sign(w_tt)
    b_x = Block(
        transactions=[tx_x],
        height=len(bc.chain),
        previous_hash=bc.get_latest_block().compute_hash(),
        consensus_type="PoS",
        validator_address=v_tt.address,
    )
    bc.add_block(b_x)

    # Quét chuỗi và đồng bộ điểm tích lũy
    results = reg.sync_with_blockchain(bc, mode="CUMULATIVE")

    # Trường ĐH-A có 3 bằng -> 10 base + 3 * 20 = 70
    assert v_bk.credentials_issued == 3
    assert v_bk.stake == 70

    # Trung tâm X có 1 bằng -> 10 base + 1 * 20 = 30
    assert v_tt.credentials_issued == 1
    assert v_tt.stake == 30

    assert reg.total_active_stake() == 100


def test_hybrid_stake_model():
    """Mô hình 3: Lai ghép = Base Stake (thẩm quyền) + (Số bằng * bonus)."""
    reg = PoSRegistry(default_mode="HYBRID", bonus_per_credential=15)
    w_bk = generate_wallet()
    v_bk = reg.register_validator("Trường ĐH-A", w_bk, stake=500)

    bc = Blockchain()
    # Phát hành 2 bằng
    for i in range(2):
        cred = Credential(f"CRED-{i}", "Trường ĐH-A", f"SV {i}", "BSc", "2026-06-01")
        tx = Transaction("ISSUE", w_bk.public_key_hex, cred.to_onchain_payload())
        tx.sign(w_bk)
        b = Block(
            transactions=[tx],
            height=len(bc.chain),
            previous_hash=bc.get_latest_block().compute_hash(),
            consensus_type="PoS",
            validator_address=v_bk.address,
        )
        bc.add_block(b)

    reg.sync_with_blockchain(bc, mode="HYBRID")
    # Base 500 + 2 * 15 = 530
    assert v_bk.credentials_issued == 2
    assert v_bk.stake == 530


def test_slashing_reduces_effective_stake_across_models():
    """Khi bị Slashing, điểm phạt trừ trực tiếp vào Stake của mọi mô hình."""
    reg = PoSRegistry(default_mode="HYBRID", bonus_per_credential=15)
    w = generate_wallet()
    v = reg.register_validator("ĐH Vi phạm", w, stake=400)

    # Giả lập vi phạm bị phạt 200 điểm
    v.slashed_amount = 200

    # Model TIERED: 400 - 200 = 200
    assert reg.get_effective_stake(v, mode="TIERED") == 200

    # Model HYBRID: 400 + 0 - 200 = 200
    assert reg.get_effective_stake(v, mode="HYBRID") == 200

