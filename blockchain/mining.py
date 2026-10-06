"""Module mining — thuật toán Proof of Work.

Mục đích: mô phỏng quá trình miner tìm nonce sao cho hash block
bắt đầu bằng đủ số ký tự '0' theo difficulty, minh hoạ chi phí
tính toán ngăn kẻ tấn công sửa chuỗi.
"""

import time


def mine_block(block) -> dict:
    """Đào block: tăng nonce cho đến khi hash thoả mãn difficulty.

    Vì sao tồn tại: Proof of Work buộc miner tiêu tốn tài nguyên tính toán
    để tạo block — ai muốn sửa block cũ phải đào lại toàn bộ block sau,
    chi phí tăng theo cấp số nhân khiến tấn công không khả thi.

    Returns:
        dict: nonce, attempts, seconds, block_hash.
    """
    difficulty = block.header.difficulty
    target_prefix = "0" * difficulty

    start = time.perf_counter()
    nonce = 0

    while True:
        block.header.nonce = nonce
        block_hash = block.compute_hash()
        if block_hash.startswith(target_prefix):
            elapsed = time.perf_counter() - start
            return {
                "nonce": nonce,
                "attempts": nonce + 1,
                "seconds": round(elapsed, 6),
                "block_hash": block_hash,
            }
        nonce += 1


# Mức difficulty tối thiểu mà mạng chấp nhận cho block PoW.
# difficulty=0 nghĩa là "không cần đào" — nếu không chặn, kẻ tấn công có thể
# gắn consensus_type="PoW", difficulty=0 để né cả PoW lẫn kiểm tra Validator của PoS.
MIN_POW_DIFFICULTY = 1


def is_acceptable_pow(block) -> bool:
    """PoW hợp lệ VÀ đạt mức difficulty tối thiểu của mạng."""
    return block.header.difficulty >= MIN_POW_DIFFICULTY and is_valid_pow(block)


def is_valid_pow(block) -> bool:
    """Kiểm tra block đã thoả mãn Proof of Work chưa.

    Vì sao tồn tại: xác minh PoW cực nhanh (1 lần hash),
    trong khi tạo PoW tốn hàng nghìn–triệu lần thử.
    Đây là tính chất bất đối xứng cốt lõi của PoW.
    """
    difficulty = block.header.difficulty
    target_prefix = "0" * difficulty
    block_hash = block.compute_hash()
    return block_hash.startswith(target_prefix)
