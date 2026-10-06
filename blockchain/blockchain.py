"""Module blockchain — quản lý chuỗi các block.

Mục đích: duy trì danh sách block theo thứ tự, kiểm tra tính hợp lệ
toàn chuỗi (hash liên kết, Merkle root) để phát hiện giả mạo.
"""

from blockchain.block import Block, BlockHeader
from blockchain.hash import sha256_hex
from blockchain.merkle import (
    calculate_merkle_root, generate_merkle_proof, verify_merkle_proof,
)
from blockchain.mining import is_valid_pow, is_acceptable_pow, MIN_POW_DIFFICULTY
from blockchain.transaction import verify_transaction, verify_ledger_transaction
from blockchain.wallet import verify_signature


def block_work(difficulty: int) -> int:
    """Tính công việc Proof of Work của 1 block: 16^difficulty."""
    return 16 ** max(0, difficulty)


def calculate_chain_work(chain: list[Block]) -> int:
    """Tính điểm chọn nhánh cho chuỗi mô phỏng PoW/PoS.

    PoW dùng 16^difficulty; mỗi block PoS có 1 điểm cố định. Đây là
    quy tắc chọn nhánh của mô phỏng hỗn hợp, không phải đồng thuận PoS production.
    """
    return sum(1 if b.header.consensus_type == "PoS" else block_work(b.header.difficulty)
               for b in chain if b.height > 0)


def verify_pos_signature(block: Block, pos_registry) -> tuple[bool, str]:
    """Xác minh chữ ký ECDSA của Validator trên block PoS.

    Kiểm tra: validator_address có trong registry và chữ ký khớp
    hash header (chữ ký KHÔNG nằm trong hash nên phải verify riêng).
    Không kiểm tra "Validator chính danh tại slot" — việc đó cần seed/stake
    tại thời điểm tạo block (xem PoSRegistry.verify_pos_block).
    """
    if block.header.consensus_type != "PoS":
        return False, "Loại đồng thuận không phải PoS"
    if block.header.difficulty != 0 or block.header.nonce != 0:
        return False, "PoS phải có difficulty=0 và nonce=0"
    if pos_registry is None:
        return False, "CHƯA xác minh ECDSA: thiếu PoS registry đáng tin cậy"
    addr = block.header.validator_address
    sig = block.header.validator_signature
    if not addr or not sig:
        return False, "Khối PoS thiếu chữ ký số hoặc địa chỉ của Validator"
    validator = pos_registry.validators.get(addr)
    if validator is None:
        return False, f"Validator '{addr[:16]}…' không có trong danh bạ Consortium"
    if not verify_signature(block.compute_hash(), sig, validator.public_key_hex):
        return False, "Chữ ký ECDSA của Validator không hợp lệ (sai khoá hoặc block bị sửa)"
    return True, "OK"


class Blockchain:
    """Chuỗi block liên kết qua hash, bắt đầu từ Genesis Block.

    Vì sao tồn tại: blockchain là sổ cái bất biến — mỗi block khoá chặt
    block trước bằng hash, sửa một block buộc phải sửa tất cả block sau.
    """

    def __init__(self):
        genesis = self._create_genesis()
        self.chain: list[Block] = [genesis]
        self.side_branches: list[list[Block]] = []
        self.block_pool: dict[str, Block] = {genesis.compute_hash(): genesis}

    def _create_genesis(self) -> Block:
        """Tạo Genesis Block — block đầu tiên, previous_hash toàn số 0.

        Vì sao tồn tại: mọi blockchain cần một điểm khởi đầu cố định
        mà tất cả node đều đồng ý, không phụ thuộc block trước.
        """
        return Block(
            transactions=[],
            height=0,
            previous_hash="0" * 64,
            timestamp="2026-01-01T00:00:00+00:00",
        )

    def total_work(self) -> int:
        """Tổng công việc PoW của chuỗi chính hiện tại."""
        return calculate_chain_work(self.chain)

    def add_block(self, block: Block) -> None:
        """Thêm block vào cuối chuỗi chính."""
        self.chain.append(block)
        self.block_pool[block.compute_hash()] = block

    def add_side_branch_block(self, block: Block) -> tuple[bool, str, list[Block] | None]:
        """Thêm một block phân nhánh (fork/side branch) vào bộ lưu trữ.

        Returns:
            (success, message, candidate_branch)
        """
        block_hash = block.compute_hash()
        self.block_pool[block_hash] = block

        # 1. Thử nối vào một side_branch đã có
        for branch in self.side_branches:
            if branch[-1].compute_hash() == block.header.previous_hash:
                branch.append(block)
                return True, f"Nối block vào nhánh phụ đã có (chiều dài {len(branch)})", branch

        # 2. Thử nối vào một block cũ trong self.chain
        for idx, main_block in enumerate(self.chain):
            if main_block.compute_hash() == block.header.previous_hash:
                new_branch = list(self.chain[:idx + 1])
                new_branch.append(block)
                self.side_branches.append(new_branch)
                return True, f"Tạo nhánh rẽ mới từ Block {idx}", new_branch

        return False, "Không tìm thấy block cha (orphan block)", None

    def reorganize(self, new_branch: list[Block]) -> tuple[list, list[Block]]:
        """Thực hiện tái tổ chức chuỗi (Chain Reorganization) sang new_branch.

        Returns:
            (reverted_transactions, disconnected_blocks)
        """
        common_idx = -1
        min_len = min(len(self.chain), len(new_branch))
        for i in range(min_len):
            if self.chain[i].compute_hash() == new_branch[i].compute_hash():
                common_idx = i
            else:
                break

        disconnected_blocks = self.chain[common_idx + 1:] if common_idx != -1 else list(self.chain[1:])
        connected_blocks = new_branch[common_idx + 1:] if common_idx != -1 else list(new_branch[1:])

        new_tx_ids = set()
        for b in connected_blocks:
            for tx in b.transactions:
                new_tx_ids.add(tx.tx_id)

        reverted_txs = []
        for b in disconnected_blocks:
            for tx in b.transactions:
                if tx.tx_id not in new_tx_ids:
                    reverted_txs.append(tx)

        old_chain = list(self.chain)
        self.side_branches = [b for b in self.side_branches if b != new_branch]
        self.side_branches.append(old_chain)
        self.chain = list(new_branch)
        self.block_pool.update({b.compute_hash(): b for b in self.chain})

        return reverted_txs, disconnected_blocks

    def get_latest_block(self) -> Block:
        """Trả về block mới nhất (cuối chuỗi).

        Vì sao tồn tại: khi tạo block mới, cần hash của block cuối
        để gán vào previous_hash, duy trì liên kết chuỗi.
        """
        return self.chain[-1]

    def is_chain_valid(self, pos_registry=None, authorized_issuers=None) -> tuple[bool, int | None, str]:
        """Kiểm tra tính hợp lệ toàn chuỗi, trả về block sai đầu tiên.

        Vì sao tồn tại: bất kỳ node nào cũng phải tự kiểm tra toàn chuỗi
        trước khi tin tưởng — đây là bản chất trustless của blockchain.

        Kiểm tra:
        1. merkle_root khớp danh sách giao dịch thực tế trong block.
        2. previous_hash của mỗi block khớp hash block trước.
        3. Đồng thuận PoW/PoS hợp lệ (trừ Genesis).
        4. Hash, chữ ký, quyền issuer và trạng thái giao dịch theo thứ tự.

        Returns:
            (True, None, "Chain hợp lệ") hoặc
            (False, chỉ_số_block_sai, lý_do).
        """
        if not self.chain or self.chain[0].compute_hash() != self._create_genesis().compute_hash():
            return False, 0, "Genesis không khớp mạng mô phỏng"
        states = {}
        issuers = {}
        seen_tx_ids = set()
        for i in range(len(self.chain)):
            block = self.chain[i]
            if block.height != i:
                return False, i, f"Block {i}: height không khớp vị trí trong chuỗi"

            # 1. Kiểm tra merkle_root khớp giao dịch
            tx_hashes = [tx.tx_id for tx in block.transactions]
            expected_root = calculate_merkle_root(tx_hashes)
            if block.header.merkle_root != expected_root:
                return (
                    False, i,
                    f"Block {i}: merkle_root không khớp danh sách giao dịch "
                    f"(header={block.header.merkle_root[:16]}…, "
                    f"expected={expected_root[:16]}…)"
                )

            for tx in block.transactions:
                cred_id = tx.payload.get("credential_id") if isinstance(tx.payload, dict) else None
                if not isinstance(cred_id, str):
                    return False, i, "Thiếu credential_id hợp lệ"
                if tx.tx_id in seen_tx_ids:
                    return False, i, "Transaction bị replay (trùng tx_id)"
                ok, why = verify_ledger_transaction(
                    tx, states.get(cred_id), issuers.get(cred_id), authorized_issuers,
                )
                if not ok:
                    return False, i, f"Block {i}: {why}"
                seen_tx_ids.add(tx.tx_id)
                if tx.tx_type == "ISSUE":
                    states[cred_id] = "ACTIVE"
                    issuers[cred_id] = tx.sender_public_key
                else:
                    states[cred_id] = "REVOKED"

            # 2–3 chỉ áp dụng cho block sau genesis
            if i > 0:
                # 2. Kiểm tra previous_hash
                prev_hash_expected = self.chain[i - 1].compute_hash()
                if block.header.previous_hash != prev_hash_expected:
                    return (
                        False, i,
                        f"Block {i}: previous_hash không khớp hash Block {i - 1} "
                        f"(stored={block.header.previous_hash[:16]}…, "
                        f"expected={prev_hash_expected[:16]}…)"
                    )

                if block.header.consensus_type not in ("PoW", "PoS"):
                    return False, i, "Loại đồng thuận không hỗ trợ"
                # 3. Kiểm tra tính hợp lệ của cơ chế đồng thuận (PoW hoặc PoS)
                if block.header.consensus_type == "PoS":
                    ok_sig, why = verify_pos_signature(block, pos_registry)
                    if not ok_sig:
                        return False, i, f"Block {i}: {why}"
                else:
                    if not is_acceptable_pow(block):
                        block_hash = block.compute_hash()
                        if block.header.difficulty < MIN_POW_DIFFICULTY:
                            why = f"difficulty={block.header.difficulty} < mức tối thiểu {MIN_POW_DIFFICULTY}"
                        else:
                            why = f"cần {block.header.difficulty} ký tự '0' đầu"
                        return (
                            False, i,
                            f"Block {i}: Proof of Work không hợp lệ "
                            f"(hash={block_hash[:16]}…, {why})"
                        )

        return (True, None, "Chain hợp lệ")

    # ── Ledger View (thay DummyLedger bằng dữ liệu thật từ chain) ──

    def credential_status(self, credential_id: str) -> str | None:
        """Quét toàn bộ chain, trả trạng thái credential: ACTIVE / REVOKED / None.

        Vì sao tồn tại: Mempool cần kiểm tra trạng thái credential trước
        khi chấp nhận ISSUE (chưa tồn tại) hoặc REVOKE (đang ACTIVE).
        Đây là ledger_view thật, thay thế DummyLedger ở Bước 5.
        """
        status = None
        for block in self.chain:
            for tx in block.transactions:
                cred = tx.payload.get("credential_id")
                if cred == credential_id:
                    if tx.tx_type == "ISSUE":
                        status = "ACTIVE"
                    elif tx.tx_type == "REVOKE":
                        status = "REVOKED"
        return status

    def credential_issuer(self, credential_id: str) -> str | None:
        """Tìm public key của Issuer đã cấp credential.

        Vì sao tồn tại: khi REVOKE, cần xác minh người gửi
        chính là Issuer gốc — không ai khác được phép thu hồi.
        """
        for block in self.chain:
            for tx in block.transactions:
                if (tx.tx_type == "ISSUE"
                        and tx.payload.get("credential_id") == credential_id):
                    return tx.sender_public_key
        return None

    # ── Verify Credential (12 bước) ──

    def verify_credential(
        self, credential_id: str, authorized_issuers: set[str] | None = None,
        pos_registry=None,
    ) -> tuple[list[tuple[str, bool, str]], str, dict]:
        """Xác minh credential qua 12 bước, trả kết quả từng bước.

        Vì sao tồn tại: Verifier cần kiểm chứng toàn bộ đường đi của
        credential — từ TX đến block đến chuỗi — để tin tưởng tuyệt đối
        mà không cần tin ai cả (trustless verification).

        Returns:
            (steps, final_status, info)
            - steps: list[(tên_bước, passed, chi_tiết)]
            - final_status: "VERIFIED" | "REVOKED" | "NOT_FOUND" | "INVALID"
            - info: dict thông tin credential, block, TX
        """
        steps: list[tuple[str, bool, str]] = []
        info: dict = {}

        # ── Tìm TX ISSUE và REVOKE trong chain ──
        issue_tx = None
        issue_block = None
        issue_block_idx = None
        revoke_tx = None
        revoke_block_idx = None

        for idx, block in enumerate(self.chain):
            for tx in block.transactions:
                cid = tx.payload.get("credential_id")
                if cid == credential_id:
                    if tx.tx_type == "ISSUE" and issue_tx is None:
                        issue_tx = tx
                        issue_block = block
                        issue_block_idx = idx
                    elif tx.tx_type == "REVOKE" and revoke_tx is None:
                        revoke_tx = tx
                        revoke_block_idx = idx

        # ── Bước 1: Credential tồn tại ──
        if issue_tx is None:
            steps.append((
                "Credential tồn tại", False,
                f"Không tìm thấy credential '{credential_id}' trong blockchain",
            ))
            return steps, "NOT_FOUND", info
        steps.append((
            "Credential tồn tại", True,
            f"Tìm thấy trong Block {issue_block_idx}",
        ))

        # Thu thập info
        info = {
            "credential_id": credential_id,
            "issuer_name": issue_tx.payload.get("issuer_name", "—"),
            "holder_name": issue_tx.payload.get("holder_name", "—"),
            "title": issue_tx.payload.get("title", "—"),
            "issue_date": issue_tx.payload.get("issue_date", "—"),
            "claims_root": issue_tx.payload.get("claims_root", "—"),
            "issuer_public_key": issue_tx.sender_public_key,
            "issue_tx_id": issue_tx.tx_id,
            "issue_block_height": issue_block.height,
            "issue_block_hash": issue_block.compute_hash(),
            "issue_merkle_root": issue_block.header.merkle_root,
        }
        if revoke_tx:
            info["revoke_tx_id"] = revoke_tx.tx_id
            info["revoke_block_height"] = revoke_block_idx
            info["revoke_reason"] = revoke_tx.payload.get("reason", "—")

        # ── Bước 2: TX tồn tại ──
        steps.append(("TX tồn tại", True, f"tx_id: {issue_tx.tx_id[:24]}…"))

        # ── Bước 3: TX hash đúng ──
        if issue_tx.compute_hash() == issue_tx.tx_id:
            steps.append(("TX hash đúng", True, "tx_id khớp compute_hash()"))
        else:
            steps.append(("TX hash đúng", False, "tx_id ≠ compute_hash() — dữ liệu bị sửa"))
            return steps, "INVALID", info

        # ── Bước 4: Chữ ký Issuer ──
        sig_ok, sig_reason = verify_transaction(issue_tx)
        if sig_ok:
            steps.append(("Chữ ký Issuer hợp lệ", True, "ECDSA signature verified"))
        else:
            steps.append(("Chữ ký Issuer hợp lệ", False, sig_reason))
            return steps, "INVALID", info

        # ── Bước 5: Issuer trong registry ──
        if authorized_issuers:
            if issue_tx.sender_public_key in authorized_issuers:
                steps.append(("Issuer trong registry", True, "Issuer được phép"))
            else:
                steps.append(("Issuer trong registry", False, "Issuer không nằm trong danh sách"))
                return steps, "INVALID", info
        else:
            steps.append(("Issuer trong registry", True, "Bỏ qua (registry mở)"))

        # ── Bước 6: Block chứa TX ──
        steps.append((
            "Block chứa TX tồn tại", True,
            f"Block {issue_block_idx}, height {issue_block.height}",
        ))

        # ── Bước 7: Merkle Proof ──
        tx_hashes = [t.tx_id for t in issue_block.transactions]
        tx_index = tx_hashes.index(issue_tx.tx_id)
        root = calculate_merkle_root(tx_hashes)
        proof = generate_merkle_proof(tx_hashes, tx_index)
        proof_ok = verify_merkle_proof(issue_tx.tx_id, proof, root)
        if proof_ok and root == issue_block.header.merkle_root:
            steps.append((
                "Merkle Proof khớp Root", True,
                f"Proof: {len(proof)} hash, khớp Merkle Root của block",
            ))
        else:
            steps.append(("Merkle Proof khớp Root", False, "Proof/Root không khớp"))
            return steps, "INVALID", info

        # ── Bước 8: Block hash đúng ──
        block_hash = issue_block.compute_hash()
        steps.append(("Block hash đúng", True, f"hash: {block_hash[:24]}…"))

        # ── Bước 9: previous_hash đúng ──
        if issue_block_idx > 0:
            exp_prev = self.chain[issue_block_idx - 1].compute_hash()
            if issue_block.header.previous_hash == exp_prev:
                steps.append(("previous_hash đúng", True, "Khớp hash block trước"))
            else:
                steps.append(("previous_hash đúng", False, "Không khớp"))
                return steps, "INVALID", info
        else:
            steps.append(("previous_hash đúng", True, "Genesis block"))

        # ── Bước 10: Cơ chế đồng thuận hợp lệ (PoW hoặc PoS) ──
        if issue_block_idx == 0:
            steps.append(("Đồng thuận khối hợp lệ", True, "Genesis block"))
        elif issue_block.header.consensus_type == "PoS":
            addr16 = issue_block.header.validator_address[:16]
            ok_sig, why = verify_pos_signature(issue_block, pos_registry)
            if not ok_sig:
                steps.append(("Đồng thuận PoS hợp lệ", False, why))
                return steps, "INVALID", info
            steps.append((
                "Đồng thuận PoS hợp lệ", True,
                f"Validator: {addr16}… (Chữ ký số ECDSA verified)",
            ))
        elif is_acceptable_pow(issue_block):
            steps.append((
                "Đồng thuận PoW hợp lệ", True,
                f"difficulty={issue_block.header.difficulty}, "
                f"nonce={issue_block.header.nonce:,}",
            ))
        else:
            steps.append(("Đồng thuận PoW hợp lệ", False, "Block không thoả mãn PoW"))
            return steps, "INVALID", info

        # ── Bước 11: Blockchain hợp lệ ──
        chain_ok, _, chain_reason = self.is_chain_valid(pos_registry=pos_registry, authorized_issuers=authorized_issuers)
        if chain_ok:
            steps.append((
                "Blockchain hợp lệ", True,
                f"Toàn bộ {len(self.chain)} block hợp lệ",
            ))
        else:
            steps.append(("Blockchain hợp lệ", False, chain_reason))
            return steps, "INVALID", info

        # ── Bước 12: Trạng thái hiện tại ──
        status = self.credential_status(credential_id)
        if status == "ACTIVE":
            steps.append(("Trạng thái", True, "✅ ACTIVE"))
            return steps, "VERIFIED", info
        elif status == "REVOKED":
            detail = "🔴 REVOKED"
            if revoke_block_idx is not None:
                detail += f" tại Block {revoke_block_idx}"
            steps.append(("Trạng thái", False, detail))
            return steps, "REVOKED", info
        else:
            steps.append(("Trạng thái", False, "Trạng thái không xác định"))
            return steps, "INVALID", info

    def verify_selective_claim(
        self,
        credential_id: str,
        claim_name: str,
        claim_value: str,
        salt: str,
        proof: list[tuple[str, str]],
        pos_registry=None,
    ) -> tuple[bool, str, dict]:
        """Xác minh một claim riêng lẻ bằng Proof of Inclusion với claims_root trên chain.

        Verifier kiểm chứng tính toàn vẹn của claim mà không thấy bất kỳ claim nào khác.
        LƯU Ý: Đây là Proof of Inclusion qua Merkle Proof, KHÔNG PHẢI Zero-Knowledge Proof (ZKP).

        Returns:
            (is_valid, reason, info)
        """
        from blockchain.claim_merkle import verify_claim_inclusion_proof

        # Chain phải hợp lệ trước khi tin bất kỳ dữ liệu nào đọc từ nó
        chain_ok, _, chain_reason = self.is_chain_valid(pos_registry=pos_registry)
        if not chain_ok:
            return False, f"Blockchain không hợp lệ: {chain_reason}", {}

        status = self.credential_status(credential_id)
        if status != "ACTIVE":
            return False, f"Credential '{credential_id}' không ở trạng thái ACTIVE (trạng thái: {status or 'NOT_FOUND'})", {}

        target_tx = None
        target_block = None
        for block in self.chain:
            for tx in block.transactions:
                if tx.tx_type == "ISSUE" and tx.payload.get("credential_id") == credential_id:
                    target_tx = tx
                    target_block = block
                    break
            if target_tx:
                break

        if not target_tx:
            return False, f"Không tìm thấy transaction phát hành của credential '{credential_id}'", {}

        # Transaction phải còn nguyên vẹn (chữ ký + tx_id khớp hash) trước khi
        # tin bất kỳ trường nào trong payload của nó — trước đây bỏ qua bước
        # này nên claims_root có thể bị sửa sau khi phát hành mà vẫn "xác minh
        # thành công" miễn kẻ tấn công tự tạo proof khớp root giả của họ.
        tx_ok, tx_reason = verify_transaction(target_tx)
        if not tx_ok:
            return False, f"Transaction phát hành đã bị giả mạo: {tx_reason}", {}

        claims_root = target_tx.payload.get("claims_root")
        if not claims_root:
            return False, f"Credential '{credential_id}' không có claims_root trên blockchain (payload cũ)", {}

        ok = verify_claim_inclusion_proof(claim_name, claim_value, salt, proof, claims_root)
        if ok:
            return True, f"Xác minh thành công: Claim '{claim_name}={claim_value}' thuộc credential (Proof of Inclusion)", {
                "credential_id": credential_id,
                "claim_name": claim_name,
                "claim_value": claim_value,
                "claims_root": claims_root,
                "block_height": target_block.height,
            }
        else:
            return False, "Merkle Proof không khớp claims_root — dữ liệu claim hoặc salt không chính xác", {
                "credential_id": credential_id,
                "claims_root": claims_root,
            }

