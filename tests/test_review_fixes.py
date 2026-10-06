"""Regression tests cho các lỗi tìm thấy khi review PR #1 (PoS + Slashing + Fork/Reorg).

Mỗi test tái hiện đúng kịch bản lỗi đã được xác nhận trên nhánh gốc:
  #1 sync nhận chuỗi dài hơn nhưng ÍT work hơn
  #2 is_chain_valid / verify_credential không verify ECDSA của block PoS
  #3 block PoW difficulty=0 (không đào, không Validator) lọt qua đồng thuận
  #4 slashing bị replay + slash_ratio không được validate
"""

import copy
from dataclasses import asdict

import pytest

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.mining import mine_block, MIN_POW_DIFFICULTY
from blockchain.node import Network, Message
from blockchain.pos import create_trustprofile_consortium
from blockchain.transaction import Credential, Transaction
from blockchain.wallet import generate_wallet, sign_message


# ── helpers ──────────────────────────────────────────────────────────────

def _tip(bc):
    return bc.get_latest_block().compute_hash()


def _pow_block(bc, difficulty, txs=None, mine=True):
    b = Block(
        transactions=list(txs or []),
        height=len(bc.chain),
        previous_hash=_tip(bc),
        difficulty=difficulty,
    )
    if mine:
        mine_block(b)
    return b


def _forged_pos_block(bc, addr="attacker", sig="not-a-real-signature", txs=None):
    return Block(
        transactions=list(txs or []),
        height=len(bc.chain),
        previous_hash=_tip(bc),
        difficulty=0,
        consensus_type="PoS",
        validator_address=addr,
        validator_signature=sig,
    )


def _issue_tx(cred_id="CRED-RF-001"):
    w = generate_wallet()
    cred = Credential(cred_id, "ĐH-A", "Alice", "BSc CS", "2026-06-01", {})
    tx = Transaction("ISSUE", w.public_key_hex, asdict(cred))
    tx.sign(w)
    return tx


@pytest.fixture
def net():
    n = Network()
    yield n
    for node in n.nodes.values():
        node._running = False


# ── #1: sync phải theo most-work, không theo độ dài ─────────────────────

def test_sync_rejects_longer_chain_with_less_work(net):
    a = net.create_node("A", "127.0.0.1", 5001)
    b = net.create_node("B", "127.0.0.1", 5002)

    a.blockchain.add_block(_pow_block(a.blockchain, difficulty=3))  # work = 4096
    for _ in range(3):                                              # work = 3 x 16 = 48
        b.blockchain.add_block(_pow_block(b.blockchain, difficulty=1))

    assert b.height > a.height
    assert a.blockchain.total_work() > b.blockchain.total_work()

    a._handle_sync_response(Message("SYNC_RESPONSE", "B", copy.deepcopy(b.blockchain)))

    assert a.height == 1, "chuỗi dài hơn nhưng ít work hơn không được thay thế chuỗi chính"
    assert a.blockchain.total_work() == 16 ** 3


def test_sync_accepts_chain_with_more_work(net):
    a = net.create_node("A", "127.0.0.1", 5001)
    b = net.create_node("B", "127.0.0.1", 5002)

    a.blockchain.add_block(_pow_block(a.blockchain, difficulty=1))
    b.blockchain.add_block(_pow_block(b.blockchain, difficulty=2))

    a._handle_sync_response(Message("SYNC_RESPONSE", "B", copy.deepcopy(b.blockchain)))

    assert a.blockchain.total_work() == 16 ** 2


# ── #2: verify ECDSA thật sự cho block PoS ──────────────────────────────

def test_chain_valid_rejects_forged_pos_signature_with_registry():
    reg = create_trustprofile_consortium()
    bc = Blockchain()
    bc.add_block(_forged_pos_block(bc))

    ok, idx, reason = bc.is_chain_valid(pos_registry=reg)
    assert not ok and idx == 1
    assert "Validator" in reason


def test_chain_valid_rejects_real_validator_with_fake_signature():
    reg = create_trustprofile_consortium()
    v = next(iter(reg.validators.values()))
    bc = Blockchain()
    bc.add_block(_forged_pos_block(bc, addr=v.address, sig="00" * 64))

    ok, idx, _ = bc.is_chain_valid(pos_registry=reg)
    assert not ok and idx == 1


def test_chain_valid_accepts_genuine_pos_block_with_registry():
    reg = create_trustprofile_consortium()
    v = next(iter(reg.validators.values()))
    bc = Blockchain()
    bc.add_block(reg.forge_block(v, [], len(bc.chain), _tip(bc)))

    assert bc.is_chain_valid(pos_registry=reg) == (True, None, "Chain hợp lệ")


def test_chain_valid_detects_tampering_after_signing():
    """Sửa block PoS sau khi ký (đổi validator_address) → hash đổi → chữ ký không còn khớp."""
    reg = create_trustprofile_consortium()
    v1, v2 = list(reg.validators.values())[:2]
    bc = Blockchain()
    blk = reg.forge_block(v1, [], len(bc.chain), _tip(bc))
    bc.add_block(blk)
    blk.header.validator_address = v2.address

    ok, idx, _ = bc.is_chain_valid(pos_registry=reg)
    assert not ok and idx == 1


def test_sync_rejects_forged_pos_chain(net):
    """Chuỗi PoS giả (dài hơn) gửi qua SYNC không được nhận."""
    a = net.create_node("A", "127.0.0.1", 5001)
    evil = Blockchain()
    for _ in range(3):
        evil.add_block(_forged_pos_block(evil))

    a._handle_sync_response(Message("SYNC_RESPONSE", "evil", evil))
    assert a.height == 0


def test_verify_credential_fails_on_forged_pos_signature():
    reg = create_trustprofile_consortium()
    bc = Blockchain()
    bc.add_block(_forged_pos_block(bc, txs=[_issue_tx()]))

    steps, status, _ = bc.verify_credential("CRED-RF-001", pos_registry=reg)
    assert status == "INVALID"
    assert steps[-1][1] is False


def test_verify_credential_does_not_claim_ecdsa_verified_without_registry():
    """Không có registry thì không được ghi 'ECDSA verified'."""
    bc = Blockchain()
    bc.add_block(_forged_pos_block(bc, txs=[_issue_tx()]))

    steps, status, _ = bc.verify_credential("CRED-RF-001")
    assert status == "INVALID"
    pos_step = [s for s in steps if "PoS" in s[0]][0]
    assert pos_step[1] is False
    assert "CHƯA xác minh" in pos_step[2]
    assert "ECDSA verified" not in pos_step[2]


# ── #3: block PoW difficulty=0 không được lọt qua ───────────────────────

def test_node_rejects_pow_block_with_zero_difficulty(net):
    n = net.create_node("N1", "127.0.0.1", 5001)
    free = _pow_block(n.blockchain, difficulty=0, mine=False)

    n._handle_block(Message("BLOCK", "evil", free))
    assert n.height == 0


def test_chain_valid_rejects_pow_block_with_zero_difficulty():
    bc = Blockchain()
    bc.add_block(_pow_block(bc, difficulty=0, mine=False))

    ok, idx, reason = bc.is_chain_valid()
    assert not ok and idx == 1
    assert str(MIN_POW_DIFFICULTY) in reason


def test_node_still_accepts_valid_pow_block(net):
    n = net.create_node("N1", "127.0.0.1", 5001)
    n._handle_block(Message("BLOCK", "miner", _pow_block(n.blockchain, difficulty=2)))
    assert n.height == 1


# ── #4: slashing — chống replay & validate slash_ratio ──────────────────

def _double_sign_pair(reg, v):
    prev = "0" * 64
    b1 = reg.forge_block(v, [], 1, prev)
    b2 = Block(transactions=[], height=1, previous_hash=prev, difficulty=0, nonce=1,
               consensus_type="PoS", validator_address=v.address)
    b2.header.validator_signature = sign_message(b2.compute_hash(), v.private_key_pem)
    return b1, b2


def test_slash_same_evidence_only_once():
    reg = create_trustprofile_consortium()
    v = next(iter(reg.validators.values()))
    b1, b2 = _double_sign_pair(reg, v)

    ok1, _, _ = reg.detect_and_slash(b1, b2)
    stake_after_first = v.stake
    ok2, msg, _ = reg.detect_and_slash(b1, b2)
    ok3, _, _ = reg.detect_and_slash(b2, b1)  # đảo thứ tự vẫn là cùng bằng chứng

    assert ok1 is True
    assert ok2 is False and "đã được xử lý" in msg
    assert ok3 is False
    assert v.stake == stake_after_first


def test_slash_distinct_double_signs_are_still_punished():
    reg = create_trustprofile_consortium()
    v = next(iter(reg.validators.values()))
    b1, b2 = _double_sign_pair(reg, v)
    reg.detect_and_slash(b1, b2)
    stake_mid = v.stake

    prev = "1" * 64  # lần ký kép khác (height/parent khác)
    c1 = reg.forge_block(v, [], 2, prev)
    c2 = Block(transactions=[], height=2, previous_hash=prev, difficulty=0, nonce=7,
               consensus_type="PoS", validator_address=v.address)
    c2.header.validator_signature = sign_message(c2.compute_hash(), v.private_key_pem)

    ok, _, _ = reg.detect_and_slash(c1, c2)
    assert ok is True and v.stake < stake_mid


@pytest.mark.parametrize("ratio", [-1.0, 0.0, 1.5])
def test_slash_ratio_must_be_in_0_1(ratio):
    reg = create_trustprofile_consortium()
    v = next(iter(reg.validators.values()))
    before = v.stake
    b1, b2 = _double_sign_pair(reg, v)

    ok, _, _ = reg.detect_and_slash(b1, b2, slash_ratio=ratio)
    assert ok is False
    assert v.stake == before and v.slashed_amount == 0
