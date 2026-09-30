"""Module mempool — hàng chờ giao dịch chưa được đóng block.

Mục đích: lưu trữ tạm các giao dịch hợp lệ đang chờ miner chọn,
loại bỏ giao dịch trùng, sai chữ ký, hoặc Issuer không được phép
trước khi vào block.
"""

from blockchain.transaction import Transaction, verify_ledger_transaction


class DummyLedger:
    """Bản giả ledger_view — trả None cho mọi credential.

    Vì sao tồn tại: ở giai đoạn chưa có blockchain thật,
    dùng bản giả để test Mempool độc lập.
    Sẽ được thay bằng blockchain thật ở bước sau.
    """

    def credential_status(self, credential_id: str) -> str | None:
        """Luôn trả None — chưa có credential nào trên chain."""
        return None

    def credential_issuer(self, credential_id: str) -> str | None:
        """Luôn trả None — chưa biết ai phát hành."""
        return None


class Mempool:
    """Hàng chờ giao dịch chưa đóng block.

    Vì sao tồn tại: giao dịch cần được kiểm tra kỹ trước khi vào block —
    Mempool là bộ lọc đầu tiên, chỉ giữ lại giao dịch hợp lệ
    để miner không lãng phí công sức đào block chứa rác.
    """

    def __init__(self, authorized_issuers: set[str] | None = None):
        self._pool: dict[str, Transaction] = {}     # tx_id → Transaction
        self.authorized_issuers: set[str] = set(authorized_issuers or [])

    def add_transaction(self, tx: Transaction, ledger_view) -> tuple[bool, str]:
        """Thêm transaction vào Mempool sau 5 bước kiểm tra.

        Vì sao tồn tại: mỗi node tự kiểm tra trước khi lan truyền,
        ngăn giao dịch rác hoặc giả mạo lây lan trong mạng.

        Returns:
            (True, "Đã thêm vào Mempool") hoặc (False, lý do cụ thể).
        """
        cred_id = tx.payload.get("credential_id") if isinstance(tx.payload, dict) else None
        ok, reason = verify_ledger_transaction(
            tx, ledger_view.credential_status(cred_id),
            ledger_view.credential_issuer(cred_id), self.authorized_issuers,
        )
        if not ok:
            return False, f"Từ chối — {reason}"
        if tx.tx_id in self._pool:
            return False, "Từ chối — transaction đã tồn tại trong Mempool (trùng tx_id)"

        # Tất cả kiểm tra đều qua → thêm vào pool
        self._pool[tx.tx_id] = tx
        return True, "Đã thêm vào Mempool"

    def remove_transactions(self, tx_ids: list[str]) -> None:
        """Xoá các transaction đã được đóng vào block.

        Vì sao tồn tại: sau khi miner đóng block thành công,
        các transaction trong block phải rời mempool để không bị đóng lại.
        """
        for tx_id in tx_ids:
            self._pool.pop(tx_id, None)

    def get_transactions(self) -> list[Transaction]:
        """Trả về danh sách transaction đang chờ trong Mempool.

        Vì sao tồn tại: miner gọi hàm này để lấy danh sách
        transaction cần đóng vào block tiếp theo.
        """
        return list(self._pool.values())
