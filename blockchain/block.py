"""Module block — định nghĩa BlockHeader và Block.

Mục đích: đóng gói các giao dịch đã xác minh thành một khối bất biến,
liên kết với khối trước qua previous_hash để tạo chuỗi.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from blockchain.hash import sha256_hex
from blockchain.merkle import calculate_merkle_root


@dataclass
class BlockHeader:
    """Header chứa metadata của block, KHÔNG chứa danh sách giao dịch.

    Vì sao tồn tại: tách header ra để tính hash nhanh (chỉ hash các trường nhỏ),
    thay vì hash toàn bộ body chứa hàng nghìn giao dịch.
    """
    version: int
    previous_hash: str
    merkle_root: str
    timestamp: str
    difficulty: int
    nonce: int
    consensus_type: str = "PoW"
    validator_address: str = ""
    validator_signature: str = ""


class Block:
    """Một khối trong blockchain, gồm header và danh sách giao dịch.

    Vì sao tồn tại: block là đơn vị đóng gói — gom nhiều giao dịch
    lại rồi liên kết với block trước, tạo chuỗi bất biến.
    """

    def __init__(
        self,
        transactions: list,
        height: int,
        previous_hash: str,
        difficulty: int = 1,
        nonce: int = 0,
        timestamp: str | None = None,
        version: int = 1,
        consensus_type: str = "PoW",
        validator_address: str = "",
        validator_signature: str = "",
    ):
        self.transactions = list(transactions)
        self.height = height
        self.transaction_count = len(transactions)

        # Tính merkle_root từ danh sách tx_id
        tx_hashes = [tx.tx_id for tx in transactions] if transactions else []
        merkle_root = calculate_merkle_root(tx_hashes)

        self.header = BlockHeader(
            version=version,
            previous_hash=previous_hash,
            merkle_root=merkle_root,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            difficulty=difficulty,
            nonce=nonce,
            consensus_type=consensus_type,
            validator_address=validator_address,
            validator_signature=validator_signature,
        )

    def compute_hash(self) -> str:
        """Tính SHA-256 của header đã chuẩn hoá (không bao gồm validator_signature)."""
        header_dict = {
            "version": self.header.version,
            "previous_hash": self.header.previous_hash,
            "merkle_root": self.header.merkle_root,
            "timestamp": self.header.timestamp,
            "difficulty": self.header.difficulty,
            "nonce": self.header.nonce,
        }
        if self.header.consensus_type == "PoS":
            header_dict["height"] = self.height
            header_dict["consensus_type"] = self.header.consensus_type
            header_dict["validator_address"] = self.header.validator_address

        canonical = json.dumps(header_dict, sort_keys=True, separators=(",", ":"))
        return sha256_hex(canonical)

    def to_dict(self) -> dict:
        """Chuyển block sang dict để hiển thị."""
        d = {
            "height": self.height,
            "hash": self.compute_hash(),
            "previous_hash": self.header.previous_hash,
            "merkle_root": self.header.merkle_root,
            "timestamp": self.header.timestamp,
            "difficulty": self.header.difficulty,
            "nonce": self.header.nonce,
            "version": self.header.version,
            "consensus_type": self.header.consensus_type,
            "transaction_count": self.transaction_count,
        }
        if self.header.consensus_type == "PoS":
            d["validator_address"] = self.header.validator_address
            d["validator_signature"] = self.header.validator_signature
        return d
