"""Module claim_merkle — Merkle Tree cho Selective Disclosure với Salted Leaves.

Mục đích:
- Mỗi claim trong credential được băm thành một lá Merkle kèm một salt ngẫu nhiên riêng:
  leaf_hash = SHA256(JSON([claim_name, claim_value, salt]))
- Chỉ Merkle Root của các claim (claims_root) được đưa vào payload lưu trên blockchain.
- Holder có thể tiết lộ chọn lọc 1 claim kèm salt và Merkle Proof cho Verifier.
- Verifier kiểm chứng tính bao hàm (Proof of Inclusion) với claims_root trên chain
  mà KHÔNG biết hoặc thấy các claim khác.
- LƯU Ý QUAN TRỌNG: Đây là Proof of Inclusion qua Merkle Proof, TUYỆT ĐỐI KHÔNG PHẢI
  Zero-Knowledge Proof (ZKP).
"""

import json
import secrets
from dataclasses import dataclass
from blockchain.hash import sha256_hex
from blockchain.merkle import (
    build_merkle_tree,
    calculate_merkle_root,
    generate_merkle_proof,
    verify_merkle_proof,
)


def generate_salt(num_bytes: int = 16) -> str:
    """Sinh salt ngẫu nhiên bảo mật (mặc định 16 bytes = 128 bit hex).

    Vì sao cần: mở rộng không gian tìm kiếm lên 2^128, chống tấn công
    vét cạn / dictionary attack đối với các claim có miền giá trị hẹp (như 'Grade A').
    """
    return secrets.token_hex(num_bytes)


def compute_claim_leaf_hash(claim_name: str, claim_value: str, salt: str) -> str:
    """Tính hash của một lá claim kèm salt ngẫu nhiên.

    Định dạng chuẩn hóa: sha256(JSON([claim_name, claim_value, salt])).

    LƯU Ý: trước đây dùng nối chuỗi "name:value:salt" bằng dấu ':' — nếu
    claim_value chứa ký tự ':' (vd một claim dạng "note": "A:B") thì hai bộ
    (name, value, salt) khác nhau có thể tạo ra cùng một chuỗi thô, dẫn tới
    cùng leaf_hash (giả mạo claim). Dùng JSON array kèm độ dài từng phần tử
    được mã hoá tường minh nên loại bỏ được nhập nhằng ranh giới.
    """
    raw = json.dumps(
        [str(claim_name).strip(), str(claim_value).strip(), str(salt).strip()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256_hex(raw)


@dataclass
class SaltedClaimItem:
    """Đại diện cho 1 claim có salt và leaf hash."""
    name: str
    value: str
    salt: str
    leaf_hash: str


def build_claims_merkle_tree(
    claims: dict[str, str],
    salts: dict[str, str] | None = None,
) -> tuple[str, dict[str, str], dict[str, list[tuple[str, str]]], list[list[str]], list[SaltedClaimItem]]:
    """Xây dựng Merkle Tree từ từ điển các claims với salt riêng cho từng claim.

    Args:
        claims: dict các claim, ví dụ {"gpa": "3.8", "grade": "A", "major": "CS"}
        salts: dict các salt tương ứng, nếu None hoặc thiếu thì tự sinh ngẫu nhiên

    Returns:
        (claims_root, salts_dict, proofs_dict, tree_levels, claim_items)
        - claims_root: Merkle root đại diện cho toàn bộ claims (chỉ lưu giá trị này on-chain)
        - salts_dict: từ điển {claim_name: salt} lưu off-chain bởi Holder
        - proofs_dict: từ điển {claim_name: merkle_proof}
        - tree_levels: các tầng của cây Merkle
        - claim_items: danh sách các SaltedClaimItem theo thứ tự đã sắp xếp
    """
    if not claims:
        # Trường hợp rỗng: root là hash chuỗi rỗng
        empty_root = sha256_hex("")
        return empty_root, {}, {}, [[empty_root]], []

    salts_dict: dict[str, str] = dict(salts) if salts else {}

    # Sắp xếp các claim theo key để đảm bảo tính xác định (deterministic)
    sorted_keys = sorted(claims.keys())
    claim_items: list[SaltedClaimItem] = []
    leaf_hashes: list[str] = []

    for key in sorted_keys:
        val = str(claims[key])
        salt = salts_dict.get(key) or generate_salt()
        salts_dict[key] = salt

        h = compute_claim_leaf_hash(key, val, salt)
        claim_items.append(SaltedClaimItem(name=key, value=val, salt=salt, leaf_hash=h))
        leaf_hashes.append(h)

    # Dựng Merkle Tree
    tree_levels = build_merkle_tree(leaf_hashes)
    claims_root = tree_levels[-1][0]

    # Sinh Merkle Proof cho từng claim
    proofs_dict: dict[str, list[tuple[str, str]]] = {}
    for idx, key in enumerate(sorted_keys):
        proofs_dict[key] = generate_merkle_proof(leaf_hashes, idx)

    return claims_root, salts_dict, proofs_dict, tree_levels, claim_items


def verify_claim_inclusion_proof(
    claim_name: str,
    claim_value: str,
    salt: str,
    proof: list[tuple[str, str]],
    claims_root: str,
) -> bool:
    """Xác minh một claim riêng lẻ có nằm trong credential hay không (Proof of Inclusion).

    Verifier chỉ nhận được:
    - claim_name, claim_value (claim cần xác minh)
    - salt (salt của claim này)
    - proof (các sibling hashes leo lên root)
    - claims_root (lấy từ payload của credential đã xác thực trên blockchain)

    Verifier KHÔNG thấy các claim khác và không biết giá trị của các lá còn lại.
    LƯU Ý: Đây là Proof of Inclusion, KHÔNG phải Zero-Knowledge Proof (ZKP).
    """
    if not claims_root:
        return False
    leaf_hash = compute_claim_leaf_hash(claim_name, claim_value, salt)
    return verify_merkle_proof(leaf_hash, proof, claims_root)


def simulate_dictionary_attack(
    claim_name: str,
    target_leaf_hash: str,
    candidate_domain: list[str],
    salt: str = "",
) -> tuple[bool, str | None, int]:
    """Mô phỏng tấn công vét cạn / từ điển (Dictionary Attack).

    Mục đích sư phạm: Cho sinh viên thấy vì sao BẮT BUỘC phải có salt.
    - Nếu KHÔNG dùng salt (salt=""): kẻ tấn công thử vét cạn domain hẹp
      (ví dụ Grade in ['A', 'B', 'C', 'D', 'F']) và tìm thấy ngay lập tức.
    - Nếu CÓ dùng salt ngẫu nhiên 128-bit: việc vét cạn trong domain hẹp
      thất bại hoàn toàn vì không biết salt.

    Returns:
        (found, cracked_value, attempts_count)
    """
    attempts = 0
    for cand in candidate_domain:
        attempts += 1
        h = compute_claim_leaf_hash(claim_name, cand, salt)
        if h == target_leaf_hash:
            return True, cand, attempts

    return False, None, attempts

