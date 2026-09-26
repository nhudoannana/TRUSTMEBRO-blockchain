"""Module pos — Thuật toán đồng thuận Proof of Stake (PoS) và cơ chế phạt Slashing.

Mục đích:
- Mô phỏng cơ chế đồng thuận PoS không dùng bài toán băm tốn điện (PoW).
- Validator nắm giữ điểm cổ phần mô phỏng (Simulated Stake) — KHÔNG mô phỏng tiền mã hoá thật.
- Lựa chọn Validator tạo block ngẫu nhiên có trọng số theo stake: P(v) ~ stake(v).
- Tính lặp lại được (reproducible) bằng seed cố định để dễ dàng demo và kiểm thử.
- Node kiểm tra chữ ký số ECDSA của Validator và kiểm tra tính chính danh (Rightful Proposer).
- Phát hiện tấn công 'Nothing at Stake' (ký hai block khác nhau cùng height) và thực thi
  cơ chế phạt Slashing: tịch thu một phần cổ phần của validator gian lận.
"""

import json
import random
from dataclasses import dataclass
from blockchain.block import Block
from blockchain.transaction import verify_transaction
from blockchain.wallet import sign_message, verify_signature


@dataclass
class Validator:
    """Đại diện cho một Validator trong mạng PoS (Tổ chức Giáo dục / Kiểm định trong TRUSTMEBRO).

    LƯU Ý: Stake ở đây là 'Điểm cổ phần bảo chứng mô phỏng' (Reputation / Guarantee Stake),
    TUYỆT ĐỐI KHÔNG PHẢI tiền tệ hay cryptocurrency thật.
    """
    name: str
    address: str
    public_key_hex: str
    private_key_pem: str
    stake: int                    # Điểm cổ phần bảo chứng hiệu lực hiện tại
    is_active: bool = True
    slashed_amount: int = 0       # Tổng số stake đã bị phạt tịch thu
    institution_type: str = "Tổ chức Thành viên"  # "Đại học Trọng điểm", "Tổ chức Kiểm định", "Doanh nghiệp"
    reputation_score: int = 100
    description: str = ""
    base_stake: int = 0           # Điểm uy tín ban đầu theo thẩm quyền pháp nhân (Static Tier)
    credentials_issued: int = 0   # Số lượng Credential hợp lệ đã phát hành trên chuỗi

    def __post_init__(self):
        if self.base_stake == 0 and self.stake > 0:
            self.base_stake = self.stake


class PoSRegistry:
    """Hệ thống đăng ký, quản lý Validator, bầu chọn và xử phạt Slashing."""

    def __init__(self, default_mode: str = "HYBRID", bonus_per_credential: int = 15):
        self.validators: dict[str, Validator] = {}
        self.stake_mode = default_mode  # "TIERED" | "CUMULATIVE" | "HYBRID"
        self.bonus_per_credential = bonus_per_credential
        # Bằng chứng ký kép đã xử lý — chống replay (phạt lặp lại cùng 1 cặp block)
        self.slashed_evidence: set[frozenset[str]] = set()

    def reset_demo_stakes(self):
        """Khôi phục điểm demo, giữ danh tính và khóa để xác minh block cũ."""
        self.slashed_evidence.clear()
        for validator in self.validators.values():
            validator.slashed_amount = 0
            validator.is_active = True
            validator.stake = self.get_effective_stake(validator)

    def register_validator(
        self,
        name: str,
        wallet,
        stake: int,
        institution_type: str = "Tổ chức Thành viên",
        reputation_score: int = 100,
        description: str = "",
    ) -> Validator:
        """Đăng ký một validator mới vào hệ thống với số điểm cổ phần mô phỏng."""
        v = Validator(
            name=name,
            address=wallet.address,
            public_key_hex=wallet.public_key_hex,
            private_key_pem=wallet.private_key_pem,
            stake=max(0, stake),
            base_stake=max(0, stake),
            is_active=True,
            slashed_amount=0,
            institution_type=institution_type,
            reputation_score=reputation_score,
            description=description,
            credentials_issued=0,
        )
        self.validators[v.address] = v
        return v

    def get_effective_stake(self, validator: Validator, mode: str | None = None) -> int:
        """Tính toán điểm Stake hiệu lực của một Validator theo mô hình được lựa chọn:
        - TIERED: Dựa trên cấp bậc kiểm định/pháp nhân ban đầu (Static Tiered Reputation).
        - CUMULATIVE: Tích lũy theo số lượng văn bằng hợp lệ đã phát hành lên chuỗi (Proof of Contribution).
        - HYBRID: Lai ghép = Base Stake + (Số văn bằng * Điểm thưởng) - Điểm phạt Slashing.
        """
        mode = mode or self.stake_mode
        if not validator.is_active:
            return 0

        if mode == "TIERED":
            calc = validator.base_stake - validator.slashed_amount
        elif mode == "CUMULATIVE":
            # Mỗi bằng hợp lệ đóng góp vào hệ sinh thái được cộng điểm thưởng
            calc = 10 + (validator.credentials_issued * self.bonus_per_credential) - validator.slashed_amount
        else:  # "HYBRID" (Khuyến nghị chuẩn cho TRUSTMEBRO)
            calc = validator.base_stake + (validator.credentials_issued * self.bonus_per_credential) - validator.slashed_amount

        return max(0, calc)

    def sync_with_blockchain(self, blockchain, mode: str | None = None) -> dict:
        """Tự động quét toàn bộ chuỗi blockchain, đếm số Credential phát hành hợp lệ (giao dịch ISSUE)
        của từng trường/tổ chức và cập nhật lại điểm Stake hiệu lực theo thời gian thực.
        """
        if mode:
            self.stake_mode = mode

        # Reset số đếm credentials
        for v in self.validators.values():
            v.credentials_issued = 0

        # Quét tất cả các block trên chuỗi chính
        for block in getattr(blockchain, "chain", []):
            for tx in getattr(block, "transactions", []):
                tx_type = getattr(tx, "tx_type", "")
                if tx_type == "ISSUE":
                    sender_pk = getattr(tx, "sender_public_key", "")
                    if not verify_transaction(tx)[0]:
                        continue
                    for validator in self.validators.values():
                        if sender_pk == validator.public_key_hex:
                            validator.credentials_issued += 1
                            break

        # Cập nhật lại thuộc tính stake của từng validator
        results = {}
        for v in self.validators.values():
            v.stake = self.get_effective_stake(v, mode=self.stake_mode)
            if v.stake <= 0 and v.slashed_amount > 0:
                v.is_active = False
            results[v.address] = {
                "name": v.name,
                "credentials_issued": v.credentials_issued,
                "base_stake": v.base_stake,
                "effective_stake": v.stake,
                "is_active": v.is_active,
            }
        return results

    def total_active_stake(self) -> int:
        """Tổng số điểm cổ phần của các validator đang hoạt động."""
        return sum(v.stake for v in self.validators.values() if v.is_active and v.stake > 0)

    def select_validator(
        self,
        height: int,
        seed: int = 42,
        previous_hash: str = "",
    ) -> Validator | None:
        """Lựa chọn ngẫu nhiên có trọng số theo cổ phần (Stake-Weighted Selection).

        Sử dụng PRNG xác định dựa trên (seed, height, previous_hash)
        để bảo đảm kết quả demo có thể lặp lại được 100% (reproducible).

        Xác suất chọn: P(v) = stake(v) / total_stake
        """
        active_list = [v for v in self.validators.values() if v.is_active and v.stake > 0]
        if not active_list:
            return None

        # Sắp xếp danh sách cố định theo địa chỉ để không phụ thuộc thứ tự dict
        active_list.sort(key=lambda x: x.address)

        total_stake = sum(v.stake for v in active_list)
        if total_stake == 0:
            return None

        # Khởi tạo PRNG xác định với seed cố định
        deterministic_state = f"{seed}:{height}:{previous_hash}"
        rng = random.Random(deterministic_state)

        # Lựa chọn có trọng số (weighted selection)
        weights = [v.stake for v in active_list]
        selected = rng.choices(active_list, weights=weights, k=1)[0]
        return selected

    def forge_block(
        self,
        validator: Validator,
        transactions: list,
        height: int,
        previous_hash: str,
    ) -> Block:
        """Validator được chọn tạo và ký số lên khối (Block Forging).

        Không cần đào PoW (difficulty=0, nonce=0).
        Block được chứng thực bằng chữ ký số ECDSA của Validator.
        """
        block = Block(
            transactions=list(transactions),
            height=height,
            previous_hash=previous_hash,
            difficulty=0,
            nonce=0,
            consensus_type="PoS",
            validator_address=validator.address,
        )

        # Tính hash của block header (chưa có chữ ký)
        block_hash = block.compute_hash()

        # Ký số block hash bằng private key của Validator
        signature = sign_message(block_hash, validator.private_key_pem)
        block.header.validator_signature = signature

        return block

    def verify_pos_block(
        self,
        block: Block,
        height: int,
        seed: int = 42,
        previous_hash: str = "",
    ) -> tuple[bool, str]:
        """Node xác minh tính hợp lệ của Block PoS:
        1. Kiểm tra block có đúng loại consensus 'PoS' không.
        2. Kiểm tra tính chính danh: người ký có đúng là Validator được chọn tại slot này không.
        3. Kiểm tra chữ ký số ECDSA của Validator.
        """
        if block.header.consensus_type != "PoS":
            return False, f"Loại đồng thuận không phải PoS (nhận: {block.header.consensus_type})"

        if block.header.difficulty != 0 or block.header.nonce != 0:
            return False, "PoS phải có difficulty=0 và nonce=0"

        if block.height != height:
            return False, f"Chiều cao block không khớp (block={block.height}, kỳ vọng={height})"

        # 1. Xác định Validator chính danh được thuật toán chọn
        expected_validator = self.select_validator(height, seed=seed, previous_hash=previous_hash)
        if not expected_validator:
            return False, "Không có validator nào đủ điều kiện (tổng stake = 0)"

        if block.header.validator_address != expected_validator.address:
            return False, (
                f"Validator không chính danh: Block do '{block.header.validator_address[:16]}…' ký, "
                f"nhưng Validator được chọn tại height {height} là '{expected_validator.name}' "
                f"({expected_validator.address[:16]}…)"
            )

        # 2. Kiểm tra chữ ký số ECDSA
        block_hash = block.compute_hash()
        if not block.header.validator_signature:
            return False, "Block PoS thiếu chữ ký của Validator"

        sig_ok = verify_signature(
            block_hash,
            block.header.validator_signature,
            expected_validator.public_key_hex,
        )
        if not sig_ok:
            return False, "Chữ ký số của Validator không hợp lệ (sai khoá hoặc block bị sửa)"

        return True, f"Hợp lệ — Ký bởi Validator chính danh '{expected_validator.name}'"

    def detect_and_slash(
        self,
        block1: Block,
        block2: Block,
        slash_ratio: float = 0.5,
    ) -> tuple[bool, str, dict]:
        """Phát hiện tấn công 'Nothing at Stake' (Double-Signing) và thực thi Slashing.

        Điều kiện vi phạm:
        - block1.height == block2.height
        - block1.compute_hash() != block2.compute_hash() (2 nội dung khối khác nhau)
        - block1.validator_address == block2.validator_address (cùng 1 validator ký cả 2)
        - Chữ ký của cả 2 block đều hợp lệ

        Hình phạt:
        - Tịch thu một tỷ lệ cổ phần (mặc định 50%).
        - Nếu stake còn lại <= 0, hủy kích hoạt (deactivate) validator.
        """
        # Tỷ lệ phạt phải nằm trong (0, 1] — tránh giá trị âm (làm TĂNG stake) hoặc > 100%
        if not (0 < slash_ratio <= 1):
            return False, f"slash_ratio không hợp lệ ({slash_ratio}) — phải trong khoảng (0, 1]", {}

        # Kiểm tra cùng height
        if block1.height != block2.height:
            return False, "Hai block khác height — không cấu thành vi phạm ký kép", {}

        hash1 = block1.compute_hash()
        hash2 = block2.compute_hash()

        # Kiểm tra hai block khác nhau
        if hash1 == hash2:
            return False, "Hai block giống hệt nhau — không có vi phạm", {}

        # Kiểm tra cùng validator
        val_addr = block1.header.validator_address
        if not val_addr or val_addr != block2.header.validator_address:
            return False, "Hai block do hai validator khác nhau ký — không vi phạm equivocation", {}

        validator = self.validators.get(val_addr)
        if not validator:
            return False, f"Không tìm thấy validator '{val_addr}' trong danh bạ", {}

        # Kiểm tra chữ ký cả 2 block
        sig1_ok = verify_signature(hash1, block1.header.validator_signature, validator.public_key_hex)
        sig2_ok = verify_signature(hash2, block2.header.validator_signature, validator.public_key_hex)

        if not (sig1_ok and sig2_ok):
            return False, "Một trong hai chữ ký không hợp lệ — bằng chứng gian lận giả", {}

        # Chống replay: mỗi cặp bằng chứng chỉ được phạt 1 lần
        evidence_key = frozenset({hash1, hash2})
        if evidence_key in self.slashed_evidence:
            return False, "Bằng chứng ký kép này đã được xử lý — không phạt lặp lại", {}
        self.slashed_evidence.add(evidence_key)

        # THỰC THI SLASHING
        old_stake = validator.stake
        slash_amount = int(old_stake * slash_ratio)
        validator.stake -= slash_amount
        validator.slashed_amount += slash_amount

        if validator.stake <= 0:
            validator.is_active = False

        report = {
            "validator_name": validator.name,
            "validator_address": validator.address,
            "height": block1.height,
            "block1_hash": hash1,
            "block2_hash": hash2,
            "old_stake": old_stake,
            "slashed_amount": slash_amount,
            "remaining_stake": validator.stake,
            "is_active": validator.is_active,
            "slash_ratio_percent": int(slash_ratio * 100),
        }

        msg = (
            f"🚨 SLASHING THÀNH CÔNG! Validator '{validator.name}' vi phạm ký kép "
            f"(Double-Signing / Nothing at Stake) tại height {block1.height}. "
            f"Đã phạt tịch thu {slash_amount:,} điểm stake ({int(slash_ratio * 100)}%). "
            f"Stake còn lại: {validator.stake:,}."
        )

        return True, msg, report


def create_trustprofile_consortium() -> PoSRegistry:
    """Khởi tạo Liên minh Đồng thuận TRUSTMEBRO Consortium (PoS / Reputation Stake).

    LƯU Ý: Tên các tổ chức dưới đây là hoàn toàn hư cấu, chỉ dùng cho mục đích
    minh họa / học thuật — không đại diện cho bất kỳ tổ chức thật nào.

    Các Validator mô phỏng đại diện cho 3 hạng tổ chức trong hệ sinh thái kiểm định:
    - 🏛️ Trường Đại học A: 500 điểm (50% trọng số)
    - 🏫 Trường Đại học B: 300 điểm (30% trọng số)
    - 🏢 Tổ chức Kiểm định C: 200 điểm (20% trọng số)
    """
    from blockchain.wallet import generate_wallet

    reg = PoSRegistry()

    w1 = generate_wallet()
    reg.register_validator(
        name="🏛️ Trường Đại học A",
        wallet=w1,
        stake=500,
        institution_type="Đại học Kỹ thuật",
        reputation_score=99,
        description="Trường đại học kỹ thuật minh họa — bảo chứng văn bằng kỹ sư & cử nhân công nghệ (hư cấu).",
    )

    w2 = generate_wallet()
    reg.register_validator(
        name="🏫 Trường Đại học B",
        wallet=w2,
        stake=300,
        institution_type="Học viện Đa ngành",
        reputation_score=98,
        description="Học viện đa ngành minh họa — bảo chứng văn bằng khoa học & công nghệ (hư cấu).",
    )

    w3 = generate_wallet()
    reg.register_validator(
        name="🏢 Tổ chức Kiểm định C",
        wallet=w3,
        stake=200,
        institution_type="Tổ chức Kiểm định",
        reputation_score=95,
        description="Liên minh kiểm định minh họa — bảo chứng hồ sơ năng lực nghề nghiệp & chứng chỉ kỹ năng (hư cấu).",
    )

    return reg



