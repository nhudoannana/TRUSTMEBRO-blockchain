"""Tests cho module blockchain/merkle.py.

Kiểm tra Merkle Root thay đổi khi sửa lá, proof đúng/sai,
và trường hợp số lá lẻ.
"""

from blockchain.hash import sha256_hex
from blockchain.merkle import (
    build_merkle_tree,
    calculate_merkle_root,
    generate_merkle_proof,
    verify_merkle_proof,
)


SAMPLE_LEAVES = [sha256_hex(f"tx{i}") for i in range(4)]


# ── Test root thay đổi khi sửa 1 lá ──

def test_root_changes_when_leaf_tampered():
    """Sửa 1 lá → Merkle Root phải thay đổi hoàn toàn.

    Mô phỏng tấn công: kẻ tấn công sửa 1 giao dịch trong block.
    """
    root_original = calculate_merkle_root(SAMPLE_LEAVES)

    tampered = list(SAMPLE_LEAVES)
    tampered[2] = sha256_hex("fake_tx")  # sửa lá thứ 3

    root_tampered = calculate_merkle_root(tampered)
    assert root_original != root_tampered


# ── Test proof đúng → verify True ──

def test_valid_proof():
    """Proof hợp lệ phải verify thành công với root đúng."""
    root = calculate_merkle_root(SAMPLE_LEAVES)

    for i in range(len(SAMPLE_LEAVES)):
        proof = generate_merkle_proof(SAMPLE_LEAVES, i)
        assert verify_merkle_proof(SAMPLE_LEAVES[i], proof, root) is True


# ── Test proof sai (root sai) → verify False ──

def test_invalid_proof_wrong_root():
    """Proof đúng nhưng root sai → verify thất bại.

    Mô phỏng: kẻ tấn công đưa proof từ block khác.
    """
    proof = generate_merkle_proof(SAMPLE_LEAVES, 0)
    fake_root = sha256_hex("fake_root")
    assert verify_merkle_proof(SAMPLE_LEAVES[0], proof, fake_root) is False


# ── Test lá sai (leaf hash bị sửa) → verify False ──

def test_invalid_proof_wrong_leaf():
    """Leaf hash bị sửa → proof không khớp root.

    Mô phỏng: kẻ tấn công claim giao dịch giả nằm trong block.
    """
    root = calculate_merkle_root(SAMPLE_LEAVES)
    proof = generate_merkle_proof(SAMPLE_LEAVES, 1)

    fake_leaf = sha256_hex("fake_transaction")
    assert verify_merkle_proof(fake_leaf, proof, root) is False


# ── Test số lá lẻ ──

def test_odd_number_of_leaves():
    """Số lá lẻ (3, 5, 7) vẫn xây tree và verify proof thành công."""
    for n in [3, 5, 7]:
        leaves = [sha256_hex(f"leaf{i}") for i in range(n)]
        root = calculate_merkle_root(leaves)
        tree = build_merkle_tree(leaves)

        # Root phải tồn tại và có đúng 1 phần tử
        assert len(tree[-1]) == 1
        assert tree[-1][0] == root

        # Proof cho mọi lá phải verify thành công
        for i in range(n):
            proof = generate_merkle_proof(leaves, i)
            assert verify_merkle_proof(leaves[i], proof, root) is True


# ── Test proof length = O(log n) ──

def test_proof_length_log_n():
    """Proof chỉ cần O(log n) hash, không phải n hash."""
    leaves = [sha256_hex(f"tx{i}") for i in range(8)]  # 8 lá → log2(8) = 3
    proof = generate_merkle_proof(leaves, 0)
    assert len(proof) == 3  # chỉ cần 3 hash anh em


def test_verification_trace_records_ordered_operands_without_changing_boolean():
    import hashlib
    h = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    leaf, left, right = h("text"), h("left"), h("right")
    first = h(left + leaf)
    root = h(first + right)
    trace = []
    assert verify_merkle_proof(leaf, [(left, "left"), (right, "right")], root, trace=trace)
    assert trace == [
        {"step": 1, "current_hash": leaf, "sibling_hash": left, "direction": "left", "parent_hash": first},
        {"step": 2, "current_hash": first, "sibling_hash": right, "direction": "right", "parent_hash": root},
    ]
    assert verify_merkle_proof(leaf, [(left, "left"), (right, "right")], root)
    empty = []
    assert verify_merkle_proof(leaf, [], leaf, trace=empty) and empty == []
    mismatch = []
    assert not verify_merkle_proof(leaf, [(right, "right")], root, trace=mismatch)
    assert mismatch[-1]["parent_hash"] == h(leaf + right)
