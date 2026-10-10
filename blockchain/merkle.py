"""Module merkle — xây dựng Merkle Tree và sinh/xác minh Merkle Proof.

Mục đích: cho phép xác minh một giao dịch thuộc block mà không cần
tải toàn bộ danh sách giao dịch, tiết kiệm băng thông cho light node.
"""

from blockchain.hash import sha256_hex


def build_merkle_tree(leaf_hashes: list[str]) -> list[list[str]]:
    """Xây Merkle Tree từ danh sách hash lá, trả về tất cả các tầng.

    Vì sao tồn tại: lưu trữ toàn bộ cây (không chỉ root) để có thể
    sinh Merkle Proof cho bất kỳ lá nào, phục vụ light node verification.

    Nếu số lá lẻ, nhân đôi hash cuối để ghép cặp.
    Tầng 0 = lá, tầng cuối = [root].
    """
    if not leaf_hashes:
        return [[sha256_hex("")]]

    levels: list[list[str]] = [list(leaf_hashes)]
    current = list(leaf_hashes)

    while len(current) > 1:
        # Nhân đôi hash cuối nếu số phần tử lẻ
        if len(current) % 2 == 1:
            current.append(current[-1])

        next_level = []
        for i in range(0, len(current), 2):
            parent_hash = sha256_hex(current[i] + current[i + 1])
            next_level.append(parent_hash)

        levels.append(next_level)
        current = next_level

    return levels


def calculate_merkle_root(leaf_hashes: list[str]) -> str:
    """Tính Merkle Root — hash duy nhất đại diện toàn bộ danh sách giao dịch.

    Vì sao tồn tại: Block Header chỉ cần lưu 1 hash 32 byte thay vì
    toàn bộ danh sách giao dịch, tiết kiệm không gian rất lớn.
    """
    tree = build_merkle_tree(leaf_hashes)
    return tree[-1][0]


def generate_merkle_proof(leaf_hashes: list[str], index: int) -> list[tuple[str, str]]:
    """Sinh Merkle Proof cho lá tại vị trí index.

    Vì sao tồn tại: proof chỉ gồm O(log n) hash anh em,
    đủ để xác minh lá thuộc cây mà không cần biết các lá khác.

    Returns:
        Danh sách (hash_anh_em, vị_trí) — vị_trí là "left" hoặc "right",
        chỉ vị trí của anh em so với node hiện tại trên đường lên root.
    """
    tree = build_merkle_tree(leaf_hashes)
    proof: list[tuple[str, str]] = []
    idx = index

    for level in tree[:-1]:  # duyệt từ lá lên, bỏ tầng root
        # Xử lý tầng lẻ: nhân đôi phần tử cuối
        working = list(level)
        if len(working) % 2 == 1:
            working.append(working[-1])

        if idx % 2 == 0:
            # Node hiện tại bên trái → anh em bên phải
            sibling = working[idx + 1]
            proof.append((sibling, "right"))
        else:
            # Node hiện tại bên phải → anh em bên trái
            sibling = working[idx - 1]
            proof.append((sibling, "left"))

        idx = idx // 2

    return proof


def verify_merkle_proof(leaf_hash: str, proof: list[tuple[str, str]], root: str,
                        *, trace: list[dict] | None = None) -> bool:
    """Xác minh Merkle Proof: lá có thực sự thuộc cây với root đã cho không.

    Vì sao tồn tại: light node không lưu toàn bộ block,
    chỉ cần root (từ header) + proof (O(log n) hash)
    là đủ kiểm chứng một giao dịch có trong block hay không.
    """
    current = leaf_hash
    for step, (sibling_hash, position) in enumerate(proof, 1):
        before = current
        if position == "left":
            current = sha256_hex(sibling_hash + current)
        else:  # "right"
            current = sha256_hex(current + sibling_hash)
        if trace is not None:
            trace.append({"step": step, "current_hash": before,
                          "sibling_hash": sibling_hash, "direction": position,
                          "parent_hash": current})

    return current == root
