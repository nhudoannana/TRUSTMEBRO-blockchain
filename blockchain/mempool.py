"""Module mempool — hàng chờ giao dịch chưa được đóng block.

Mục đích: lưu trữ tạm các giao dịch hợp lệ đang chờ miner chọn,
loại bỏ giao dịch trùng, sai chữ ký, hoặc Issuer không được phép
trước khi vào block.
"""

from blockchain.transaction import Transaction, verify_ledger_transaction, verify_transaction


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

    def _reconciliation_rejection_code(self, tx, status, issuer):
        """Mã giải thích theo thứ tự validator; không quyết định admission."""
        if tx.tx_type not in ("ISSUE", "REVOKE"):
            return "invalid_tx_type"
        if not tx.sender_public_key:
            return "invalid_sender"
        if not isinstance(tx.payload, dict) or not tx.payload:
            return "invalid_payload"
        if not tx.signature:
            return "invalid_signature"
        if tx.tx_id != tx.compute_hash():
            return "invalid_tx_hash"
        if not verify_transaction(tx)[0]:
            return "invalid_signature"
        credential = tx.payload.get("credential_id")
        if not isinstance(credential, str) or not credential.strip():
            return "invalid_credential_id"
        if self.authorized_issuers and tx.sender_public_key not in self.authorized_issuers:
            return "unauthorized_issuer"
        if tx.tx_type == "ISSUE" and status is not None:
            return "credential_exists"
        if tx.tx_type == "REVOKE" and status != "ACTIVE":
            return "not_active_on_chain"
        if tx.tx_type == "REVOKE" and issuer != tx.sender_public_key:
            return "wrong_issuer"
        return "invalid_transaction"

    def plan_reconciliation(self, ledger_view, candidates, confirmed_ids: set[str]) -> dict:
        """Đối soát thuần với confirmed ledger, retained FIFO trước detached."""
        grouped = {}
        for origin in ("retained", "detached"):
            for candidate in candidates:
                if candidate["origin"] != origin:
                    continue
                tx = candidate["transaction"]
                group = grouped.setdefault(tx.tx_id, {"transaction": tx, "origins": [], "occurrences": 0})
                if origin not in group["origins"]:
                    group["origins"].append(origin)
                group["occurrences"] += 1
        counts = dict(candidates=len(grouped), retained=0, restored=0,
                      rejected=0, confirmed=0, duplicates=0)
        pending, transactions, reserved = [], [], set()
        for tx_id, group in grouped.items():
            tx = group["transaction"]
            credential = tx.payload.get("credential_id") if isinstance(tx.payload, dict) else None
            record = dict(tx_id=tx_id, credential_id=credential, origins=group["origins"],
                          occurrences=group["occurrences"])
            if group["occurrences"] > 1:
                counts["duplicates"] += 1
                record["duplicate_reason_code"] = "duplicate_candidate"
            if tx_id in confirmed_ids:
                counts["confirmed"] += 1
                record.update(disposition="confirmed", reason_code="confirmed_on_new_chain",
                              message="Đã xác nhận trên chuỗi mới")
            else:
                status, issuer = ledger_view.credential_status(credential), ledger_view.credential_issuer(credential)
                ok, message = verify_ledger_transaction(tx, status, issuer, self.authorized_issuers)
                if not ok:
                    code = self._reconciliation_rejection_code(tx, status, issuer)
                elif credential in reserved:
                    ok, code, message = False, "pending_conflict", "Đã có giao dịch chờ cho credential này"
                if ok:
                    origin = group["origins"][0]
                    counts["retained" if origin == "retained" else "restored"] += 1
                    pending.append(tx)
                    reserved.add(credential)
                    record.update(disposition="pending", reason_code="accepted_" + origin,
                                  message="Giữ giao dịch đang chờ" if origin == "retained" else "Hoàn trả từ nhánh cũ")
                else:
                    counts["rejected"] += 1
                    record.update(disposition="rejected", reason_code=code, message=message)
            transactions.append(record)
        return {"pending": pending, "transactions": transactions, "counts": counts}

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
