"""Module proof_package — xuất/nhập gói Selective Disclosure Proof dạng JSON.

Mục đích: cho phép Holder xuất gói chứng minh (proof package) cho đúng
một claim, gửi file JSON cho Verifier ở phiên trình duyệt khác.
Verifier nhập file, hệ thống kiểm tra cấu trúc rồi xác minh trên chain.

Đây là Proof of Inclusion qua Merkle Proof, KHÔNG PHẢI Zero-Knowledge Proof (ZKP).
Chưa có cơ chế đăng nhập hay kiểm soát quyền — các vai trò Holder/Verifier
trong UI chỉ là hướng dẫn luồng demo, không phải bảo mật hoàn chỉnh.
"""

import json

FORMAT_VERSION = "TRUSTMEBRO-PROOF-v1"
MAX_PROOF_FILE_SIZE = 10 * 1024  # 10 KB — gói proof không nên lớn hơn


def build_proof_package(
    credential_id: str,
    claim_name: str,
    claim_value: str,
    salt: str,
    merkle_proof: list[tuple[str, str]],
) -> dict:
    """Tạo gói proof JSON cho đúng một claim.

    Gói KHÔNG chứa: private key, các claim khác, salt khác, toàn bộ hồ sơ.
    """
    return {
        "format_version": FORMAT_VERSION,
        "credential_id": credential_id,
        "claim_name": claim_name,
        "claim_value": claim_value,
        "salt": salt,
        "merkle_proof": [[h, d] for h, d in merkle_proof],
        "note": (
            "Proof of Inclusion (Selective Disclosure) — "
            "không phải Zero-Knowledge Proof (ZKP). "
            "Verifier cần xác minh trên node/chain được tin cậy."
        ),
    }


def export_proof_json(package: dict) -> str:
    """Serialize gói proof thành chuỗi JSON đẹp."""
    return json.dumps(package, indent=2, ensure_ascii=False)


def parse_proof_package(raw: str | bytes) -> tuple[bool, str, dict]:
    """Phân tích và kiểm tra cấu trúc gói proof JSON.

    Returns:
        (ok, error_message, parsed_package)
    """
    # Kiểm tra kích thước
    raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if len(raw_bytes) > MAX_PROOF_FILE_SIZE:
        return False, f"File quá lớn ({len(raw_bytes):,} bytes, tối đa {MAX_PROOF_FILE_SIZE:,} bytes)", {}

    if len(raw_bytes) == 0:
        return False, "File rỗng", {}

    # Parse JSON
    try:
        data = json.loads(raw_bytes.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return False, f"File không phải JSON hợp lệ: {e}", {}

    if not isinstance(data, dict):
        return False, "Cấu trúc gốc phải là JSON object", {}

    # Kiểm tra format_version
    version = data.get("format_version")
    if version != FORMAT_VERSION:
        return False, f"Phiên bản không hỗ trợ: '{version}' (cần '{FORMAT_VERSION}')", {}

    # Kiểm tra trường bắt buộc
    required = ["credential_id", "claim_name", "claim_value", "salt", "merkle_proof"]
    missing = [f for f in required if f not in data]
    if missing:
        return False, f"Thiếu trường bắt buộc: {', '.join(missing)}", {}

    # Kiểm tra kiểu dữ liệu
    for field in ["credential_id", "claim_name", "claim_value", "salt"]:
        if not isinstance(data[field], str):
            return False, f"Trường '{field}' phải là chuỗi", {}

    if not isinstance(data["merkle_proof"], list):
        return False, "Trường 'merkle_proof' phải là mảng JSON", {}

    # Kiểm tra từng phần tử proof
    proof_tuples = []
    for i, item in enumerate(data["merkle_proof"]):
        if not isinstance(item, list) or len(item) != 2:
            return False, f"Phần tử merkle_proof[{i}] phải là mảng [hash, direction]", {}
        h, d = item
        if not isinstance(h, str) or not isinstance(d, str):
            return False, f"merkle_proof[{i}]: hash và direction phải là chuỗi", {}
        if d not in ("left", "right"):
            return False, f"merkle_proof[{i}]: direction phải là 'left' hoặc 'right', nhận '{d}'", {}
        proof_tuples.append((h, d))

    # Trả về gói đã phân tích với proof dạng tuple
    parsed = {
        "credential_id": data["credential_id"].strip(),
        "claim_name": data["claim_name"].strip(),
        "claim_value": data["claim_value"].strip(),
        "salt": data["salt"].strip(),
        "merkle_proof": proof_tuples,
    }
    return True, "", parsed
