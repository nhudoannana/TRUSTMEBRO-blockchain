"""Module transaction — định nghĩa Credential và Transaction.

Mục đích: đóng gói thông tin chứng nhận thành giao dịch có chữ ký,
đảm bảo tính toàn vẹn và không thể chối bỏ (non-repudiation).
"""

import json
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from blockchain.hash import sha256_hex
from blockchain.wallet import sign_message, verify_signature


@dataclass
class Credential:
    """Chứng nhận số do Issuer cấp cho Holder.

    Vì sao tồn tại: gói thông tin chứng nhận (bằng cấp, chứng chỉ)
    thành cấu trúc chuẩn để đưa vào transaction trên blockchain.
    """
    credential_id: str
    issuer_name: str
    holder_name: str
    title: str
    issue_date: str
    claims: dict = field(default_factory=dict)
    claims_root: str = ""

    def to_onchain_payload(self) -> dict:
        """Chuyển thành payload đưa lên blockchain.

        Theo nguyên lý bảo vệ quyền riêng tư & Selective Disclosure:
        Chỉ lưu metadata và duy nhất claims_root lên blockchain,
        KHÔNG lưu dữ liệu claims chi tiết hay salt on-chain.
        """
        return {
            "credential_id": self.credential_id,
            "issuer_name": self.issuer_name,
            "holder_name": self.holder_name,
            "title": self.title,
            "issue_date": self.issue_date,
            "claims_root": self.claims_root,
        }


class Transaction:
    """Giao dịch phát hành hoặc thu hồi credential.

    Vì sao tồn tại: là đơn vị dữ liệu nhỏ nhất trên blockchain —
    ghi lại hành động (ISSUE/REVOKE) kèm chữ ký của Issuer,
    để bất kỳ node nào cũng xác minh được mà không cần bên thứ ba.
    """

    def __init__(
        self,
        tx_type: str,
        sender_public_key: str,
        payload: dict,
        nonce: str | None = None,
        timestamp: str | None = None,
    ):
        self.tx_type = tx_type                          # "ISSUE" hoặc "REVOKE"
        self.sender_public_key = sender_public_key      # public key hex của Issuer
        self.payload = payload                          # credential dict hoặc {credential_id, reason}
        self.nonce = nonce or secrets.token_hex(16)     # ngẫu nhiên, chống trùng tx_id
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.signature: str | None = None               # chữ ký hex, gán khi sign()
        self.tx_id: str = self.compute_hash()           # hash = fingerprint giao dịch

    def compute_hash(self) -> str:
        """Tính hash SHA-256 của transaction (KHÔNG gồm signature).

        Vì sao tồn tại: hash là fingerprint duy nhất của giao dịch,
        dùng JSON chuẩn hoá (sort_keys, separators gọn) để mọi node
        tính ra cùng kết quả bất kể thứ tự field.
        """
        data = {
            "tx_type": self.tx_type,
            "sender_public_key": self.sender_public_key,
            "payload": self.payload,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return sha256_hex(canonical)

    def sign(self, wallet) -> None:
        """Ký transaction bằng private key của wallet.

        Vì sao tồn tại: chữ ký chứng minh Issuer đã phê duyệt
        nội dung transaction; không ai giả mạo được nếu không có private key.
        """
        self.tx_id = self.compute_hash()
        self.signature = sign_message(self.tx_id, wallet.private_key_pem)

    def to_dict(self) -> dict:
        """Chuyển transaction sang dict để hiển thị hoặc serialize."""
        return {
            "tx_id": self.tx_id,
            "tx_type": self.tx_type,
            "sender_public_key": self.sender_public_key,
            "payload": self.payload,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


def verify_transaction(tx: Transaction) -> tuple[bool, str]:
    """Xác minh transaction: định dạng, hash, chữ ký.

    Vì sao tồn tại: mỗi node phải tự kiểm tra trước khi chấp nhận
    transaction vào mempool hoặc block — không tin ai cả (trustless).

    Returns:
        (True, "Hợp lệ") hoặc (False, lý do cụ thể).
    """
    # 1. Kiểm tra tx_type
    if tx.tx_type not in ("ISSUE", "REVOKE"):
        return False, f"tx_type không hợp lệ: '{tx.tx_type}' (phải là 'ISSUE' hoặc 'REVOKE')"

    # 2. Kiểm tra trường bắt buộc
    if not tx.sender_public_key:
        return False, "Thiếu sender_public_key"

    if not isinstance(tx.payload, dict) or not tx.payload:
        return False, "Thiếu payload"

    # 3. Kiểm tra chữ ký tồn tại
    if not tx.signature:
        return False, "Transaction chưa được ký (signature rỗng)"

    # 4. Kiểm tra tx_id khớp hash
    expected_hash = tx.compute_hash()
    if tx.tx_id != expected_hash:
        return False, (
            f"tx_id không khớp hash — dữ liệu đã bị sửa sau khi tạo "
            f"(tx_id={tx.tx_id[:16]}…, hash={expected_hash[:16]}…)"
        )

    # 5. Kiểm tra chữ ký
    sig_ok = verify_signature(tx.tx_id, tx.signature, tx.sender_public_key)
    if not sig_ok:
        return False, "Chữ ký không khớp — transaction bị giả mạo hoặc sai khoá"

    return True, "Hợp lệ"


def verify_ledger_transaction(tx, status, issuer, authorized_issuers=None) -> tuple[bool, str]:
    """Quy tắc chung cho mempool và giao dịch theo thứ tự trong một nhánh."""
    ok, reason = verify_transaction(tx)
    if not ok:
        return False, f"Transaction không hợp lệ hoặc bị giả mạo: {reason}"
    cred_id = tx.payload.get("credential_id")
    if not isinstance(cred_id, str) or not cred_id.strip():
        return False, "Thiếu credential_id hợp lệ"
    if authorized_issuers and tx.sender_public_key not in authorized_issuers:
        return False, "Issuer không nằm trong danh sách được phép (unauthorized)"
    if tx.tx_type == "ISSUE" and status is not None:
        return False, f"Credential '{cred_id}' đã tồn tại ({status}); cần mã mới khi cấp lại"
    if tx.tx_type == "REVOKE":
        if status != "ACTIVE":
            return False, f"Credential '{cred_id}' không ở trạng thái ACTIVE, không thể thu hồi"
        if issuer != tx.sender_public_key:
            return False, "Chỉ Issuer gốc mới có quyền thu hồi credential"
    return True, "Hợp lệ"
