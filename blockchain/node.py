"""Module node — Full Node và Network (mạng ngang hàng mô phỏng).

Mục đích: mỗi Node giữ bản sao blockchain và mempool riêng,
nhận giao dịch/block qua inbox và tự xác minh trước khi chấp nhận,
mô phỏng tính phi tập trung — không ai tin ai, mọi node tự kiểm tra.
"""

import copy
import queue
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime

from blockchain.block import Block
from blockchain.blockchain import Blockchain, calculate_chain_work, block_work
from blockchain.mempool import Mempool
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import mine_block, is_valid_pow, is_acceptable_pow, MIN_POW_DIFFICULTY


@dataclass
class Message:
    """Thông điệp trao đổi giữa các node.

    Vì sao tồn tại: trong mạng P2P, node giao tiếp qua message —
    mỗi loại message kích hoạt một quy trình xử lý khác nhau.
    """
    msg_type: str       # "TX", "BLOCK", "SYNC_REQUEST", "SYNC_RESPONSE"
    sender_id: str      # node_id của người gửi
    payload: object     # Transaction, Block, Blockchain, …


class Node:
    """Full Node — giữ blockchain, mempool riêng và xử lý message bằng thread.

    Vì sao tồn tại: mỗi node là một thực thể độc lập, tự xác minh
    mọi thứ nhận được — đây là nền tảng của tính phi tập trung.
    """

    def __init__(self, node_id: str, host: str, port: int,
                 network: "Network", authorized_issuers: set[str] | None = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.status = "ONLINE"

        self.blockchain = Blockchain()
        self.mempool = Mempool(authorized_issuers)
        self.network = network

        self.inbox: queue.Queue = queue.Queue()
        self._seen_tx_ids: set[str] = set()

        # Thread xử lý message — chạy song song thật
        self._state_lock = threading.RLock()
        self._running = True
        self._worker = threading.Thread(
            target=self._process_loop, daemon=True, name=f"worker-{node_id}",
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop the inbox worker; safe to call more than once."""
        self._running = False
        self._worker.join(timeout=1.0)

    @property
    def height(self) -> int:
        """Chiều cao chuỗi = số block - 1 (genesis = 0)."""
        return len(self.blockchain.chain) - 1

    # ── API công khai (gọi từ main thread / UI) ──

    def submit_transaction(self, tx) -> tuple[bool, str]:
        """Nhận transaction từ bên ngoài, verify, thêm mempool, broadcast.

        Vì sao tồn tại: đây là điểm nhập cho giao dịch mới —
        node đầu tiên kiểm tra rồi lan truyền cho toàn mạng.
        """
        with self._state_lock:
            if self.status != "ONLINE":
                return False, f"{self.node_id} đang OFFLINE"

            # Dùng blockchain thật làm ledger_view (thay DummyLedger từ Bước 5)
            ok, reason = self.mempool.add_transaction(tx, self.blockchain)
            if not ok:
                self.network.log_event(self.node_id, f"TX REJECT: {reason}")
                return False, reason

            self._seen_tx_ids.add(tx.tx_id)
            self.network.log_event(
                self.node_id, f"TX ACCEPT: {tx.tx_id[:16]}… → broadcast to peers"
            )

            # Chuyển tiếp cho tất cả peer
            msg = Message("TX", self.node_id, tx)
            self.network.broadcast(self.node_id, msg)
            return True, "Accepted — đã thêm vào Mempool và broadcast"

    def _validate_candidate(self, block):
        """Kiểm tra cả nhánh ứng viên trước khi thay đổi chain/pool."""
        for branch in [self.blockchain.chain, *self.blockchain.side_branches]:
            for i, parent in enumerate(branch):
                if parent.compute_hash() == block.header.previous_hash:
                    candidate = Blockchain()
                    candidate.chain = branch[:i + 1] + [block]
                    ok, _, reason = candidate.is_chain_valid(
                        pos_registry=self.network.pos_registry,
                        authorized_issuers=self.mempool.authorized_issuers,
                    )
                    return ok, reason
        return False, "Không tìm thấy block cha trong nhánh đã biết"

    def mine_pending(self, max_txs: int = 10, difficulty: int = 3) -> tuple:
        """Lấy Tx từ Mempool, tạo Block, mine (PoW), broadcast.

        Vì sao tồn tại: đây là luồng chính tạo block mới —
        gom giao dịch chờ, đóng gói, chứng minh công sức tính toán,
        rồi phát cho mạng để đạt đồng thuận.

        Returns:
            (block, mining_result) nếu thành công, (None, lý_do) nếu thất bại.
        """
        with self._state_lock:
            if self.status != "ONLINE":
                return None, "Node đang OFFLINE"

            txs = self.mempool.get_transactions()[:max_txs]
            if not txs:
                return None, "Mempool trống — không có TX để mine"

            prev_hash = self.blockchain.get_latest_block().compute_hash()
            height = len(self.blockchain.chain)

            block = Block(
                transactions=list(txs), height=height,
                previous_hash=prev_hash, difficulty=difficulty,
            )

            self.network.log_event(
                self.node_id,
                f"⛏️ Mining started: {len(txs)} TXs, difficulty={difficulty}",
            )

            result = mine_block(block)

            self.network.log_event(
                self.node_id,
                f"⛏️ Block mined! height={height}, nonce={result['nonce']:,}, "
                f"attempts={result['attempts']:,}, time={result['seconds']:.4f}s",
            )

            ok, reason = self._validate_candidate(block)
            if not ok:
                return None, reason

            # Thêm vào chain của chính mình
            self.blockchain.add_block(block)

            # Xoá Tx đã đóng gói khỏi Mempool
            tx_ids = [tx.tx_id for tx in txs]
            self.mempool.remove_transactions(tx_ids)

            self.network.log_event(
                self.node_id,
                f"✅ Block added. Height: {self.height}. "
                f"Mempool remaining: {len(self.mempool.get_transactions())}",
            )

            # Broadcast block cho peers
            msg = Message("BLOCK", self.node_id, block)
            self.network.broadcast(self.node_id, msg)

            self.network.log_event(self.node_id, "📡 Block broadcast to peers")

            return block, result

    def forge_pos_pending(self, validator=None, seed: int | None = None, max_txs: int = 10) -> tuple:
        """Lấy Tx từ Mempool, tạo Block PoS, ký số bởi Validator chính danh, broadcast.

        Áp dụng cho mô hình Consortium TRUSTMEBRO:
        - Validator đại diện cho cơ sở giáo dục / tổ chức kiểm định được bầu chọn.
        - Không tốn tài nguyên đào PoW (difficulty=0, nonce=0).
        - Toàn mạng xác thực chữ ký số và cập nhật sổ cái tức thì.

        Returns:
            (block, result_dict) nếu thành công, (None, lý_do) nếu thất bại.
        """
        with self._state_lock:
            if self.status != "ONLINE":
                return None, "Node đang OFFLINE"

            txs = self.mempool.get_transactions()[:max_txs]
            if not txs:
                return None, "Mempool trống — không có TX để tạo khối PoS"

            prev_hash = self.blockchain.get_latest_block().compute_hash()
            height = len(self.blockchain.chain)

            pos_reg = getattr(self.network, "pos_registry", None)
            if not pos_reg:
                from blockchain.pos import create_trustprofile_consortium
                pos_reg = create_trustprofile_consortium()
                self.network.pos_registry = pos_reg

            if seed is None:
                seed = self.network.consensus_seed
            if seed != self.network.consensus_seed:
                return None, "Seed phải khớp cấu hình đồng thuận của mạng"

            # Nếu không truyền validator cụ thể, tự động chọn validator chính danh theo thuật toán
            if validator is None:
                validator = pos_reg.select_validator(height=height, seed=seed, previous_hash=prev_hash)
                if not validator:
                    return None, "Không tìm thấy validator hợp lệ trong mạng PoS"

            # Đo thời gian tạo và ký khối; không suy ra điện năng từ thời gian.
            started = time.perf_counter()
            block = pos_reg.forge_block(
                validator=validator,
                transactions=list(txs),
                height=height,
                previous_hash=prev_hash,
            )

            ok, reason = pos_reg.verify_pos_block(block, height, seed, prev_hash)
            if not ok:
                return None, reason

            result = {
                "consensus": "PoS",
                "validator_name": validator.name,
                "validator_address": validator.address,
                "height": height,
                "block_hash": block.compute_hash(),
                "tx_count": len(txs),
                "seconds": time.perf_counter() - started,
            }

            self.network.log_event(
                self.node_id,
                f"🪙 PoS Block forged by '{validator.name}'! height={height}, txs={len(txs)}, "
                f"hash={result['block_hash'][:16]}…",
            )

            ok, reason = self._validate_candidate(block)
            if not ok:
                return None, reason

            # Thêm vào chuỗi của chính mình
            self.blockchain.add_block(block)

            # Xoá Tx đã đóng gói khỏi Mempool
            tx_ids = [tx.tx_id for tx in txs]
            self.mempool.remove_transactions(tx_ids)

            self.network.log_event(
                self.node_id,
                f"✅ PoS Block added. Height: {self.height}. "
                f"Mempool remaining: {len(self.mempool.get_transactions())}",
            )

            # Broadcast cho các peer
            msg = Message("BLOCK", self.node_id, block)
            self.network.broadcast(self.node_id, msg)
            self.network.log_event(self.node_id, "📡 PoS Block broadcast to peers")

            return block, result

    def request_sync(self) -> None:
        """Yêu cầu đồng bộ chain từ các peer.

        Vì sao tồn tại: node mới tham gia hoặc vừa online lại
        cần lấy chuỗi dài nhất hợp lệ từ mạng để bắt kịp.
        """
        msg = Message("SYNC_REQUEST", self.node_id, None)
        self.network.broadcast(self.node_id, msg)
        self.network.log_event(self.node_id, "SYNC_REQUEST → all peers")

    def go_online(self) -> None:
        """Bật node lên trạng thái ONLINE và tự động kích hoạt đồng bộ chuỗi."""
        with self._state_lock:
            self.status = "ONLINE"
            self.network.log_event(self.node_id, "Status → ONLINE (Tự động kích hoạt SYNC_REQUEST)")
            self.request_sync()

    def go_offline(self) -> None:
        """Tắt node — message đến sẽ bị Network bỏ qua."""
        with self._state_lock:
            self.status = "OFFLINE"
            while not self.inbox.empty():
                try:
                    self.inbox.get_nowait()
                except queue.Empty:
                    break
            self.network.log_event(self.node_id, "Status → OFFLINE")

    # ── Vòng lặp xử lý message (chạy trong thread riêng) ──

    def _process_loop(self):
        """Liên tục lấy message từ inbox và xử lý."""
        while self._running:
            try:
                msg = self.inbox.get(timeout=0.3)
                if self.status == "ONLINE":
                    self._handle_message(msg)
            except queue.Empty:
                continue

    def _handle_message(self, msg: Message):
        """Phân loại và xử lý message theo loại."""
        if msg.msg_type == "TX":
            self._handle_tx(msg)
        elif msg.msg_type == "BLOCK":
            self._handle_block(msg)
        elif msg.msg_type == "SYNC_REQUEST":
            self._handle_sync_request(msg)
        elif msg.msg_type == "SYNC_RESPONSE":
            self._handle_sync_response(msg)

    # ── TX handler ──

    def _handle_tx(self, msg: Message):
        """Nhận TX từ peer: verify, thêm mempool. Không forward lại."""
        with self._state_lock:
            tx = msg.payload
            if tx.tx_id in self._seen_tx_ids:
                return
            self._seen_tx_ids.add(tx.tx_id)

            # Dùng blockchain thật làm ledger_view
            ok, reason = self.mempool.add_transaction(tx, self.blockchain)
            if ok:
                self.network.log_event(
                    self.node_id,
                    f"TX ACCEPT (relay from {msg.sender_id}): {tx.tx_id[:16]}…",
                )
            else:
                self.network.log_event(
                    self.node_id,
                    f"TX REJECT (relay from {msg.sender_id}): {reason}",
                )

    # ── BLOCK handler — consensus ──

    def _handle_block(self, msg: Message):
        """Nhận block từ peer: kiểm tra toàn bộ rồi accept, lưu side branch hoặc reorg.

        Vì sao tồn tại: mỗi node phải tự kiểm tra mọi block nhận được —
        không tin tưởng miner. Đây là bản chất trustless.

        Kiểm tra theo thứ tự:
        1. Merkle root khớp danh sách TX.
        2. Proof of Work hợp lệ.
        3. Mỗi TX: chữ ký hợp lệ.
        4. Kiểm tra previous_hash:
           - Nối tiếp tip: thêm vào chain chính.
           - Nối vào block cũ: lưu thành side branch.
             Nếu nhánh phụ có tổng PoW (sum 16^d) > chuỗi chính -> REORG & hoàn trả TX về Mempool!
        """
        with self._state_lock:
            block = msg.payload
            # Height phải nối tiếp block cha, kể cả trên nhánh phụ.
            parent = self.blockchain.block_pool.get(block.header.previous_hash)
            if parent is None:
                self.request_sync()
                return
            if block.height != parent.height + 1:
                self.network.log_event(self.node_id, "❌ BLOCK REJECTED: height không nối tiếp block cha")
                return

            # 1. Kiểm tra merkle_root
            tx_hashes = [tx.tx_id for tx in block.transactions]
            expected_root = calculate_merkle_root(tx_hashes)
            if block.header.merkle_root != expected_root:
                self.network.log_event(
                    self.node_id,
                    f"❌ BLOCK REJECTED from {msg.sender_id}: "
                    f"merkle_root không khớp danh sách TX",
                )
                return

            # 2. Kiểm tra tính hợp lệ của cơ chế đồng thuận (PoW hoặc PoS)
            if block.header.consensus_type == "PoS":
                pos_reg = getattr(self.network, "pos_registry", None)
                if not pos_reg:
                    from blockchain.pos import create_trustprofile_consortium
                    pos_reg = create_trustprofile_consortium()
                    self.network.pos_registry = pos_reg

                seed = getattr(self.network, "consensus_seed", 42)
                ok, reason = pos_reg.verify_pos_block(
                    block,
                    height=block.height,
                    seed=seed,
                    previous_hash=block.header.previous_hash,
                )
                if not ok:
                    self.network.log_event(
                        self.node_id,
                        f"❌ PoS BLOCK REJECTED from {msg.sender_id}: {reason}",
                    )
                    return
            else:
                # Kiểm tra Proof of Work (+ difficulty tối thiểu, chống né đồng thuận bằng difficulty=0)
                if not is_acceptable_pow(block):
                    self.network.log_event(
                        self.node_id,
                        f"❌ BLOCK REJECTED from {msg.sender_id}: "
                        f"PoW không hợp lệ (difficulty={block.header.difficulty}, "
                        f"tối thiểu {MIN_POW_DIFFICULTY}, cần đủ số '0' đầu)",
                    )
                    return

            ok, reason = self._validate_candidate(block)
            if not ok:
                self.network.log_event(self.node_id, f"❌ BLOCK REJECTED: {reason}")
                return

            my_tip = self.blockchain.get_latest_block().compute_hash()
            if block.header.previous_hash == my_tip:
                self.blockchain.add_block(block)
                tx_ids = [tx.tx_id for tx in block.transactions]
                self.mempool.remove_transactions(tx_ids)

                self.network.log_event(
                    self.node_id,
                    f"✅ BLOCK ACCEPTED from {msg.sender_id}: "
                    f"height {block.height}, {len(block.transactions)} TXs, "
                    f"work={block_work(block.header.difficulty):,}. "
                    f"My height: {self.height}, total_work={self.blockchain.total_work():,}",
                )
                return

            # Trường hợp 2: previous_hash khác my_tip -> Xử lý Fork / Side Branch
            success, fork_msg, candidate_branch = self.blockchain.add_side_branch_block(block)
            if not success or candidate_branch is None:
                self.network.log_event(
                    self.node_id,
                    f"⚠️ STALE/ORPHAN block from {msg.sender_id}: "
                    f"prev_hash không tìm thấy trong pool → triggering sync",
                )
                self.request_sync()
                return

            # Tính tổng công việc PoW của 2 nhánh
            work_candidate = calculate_chain_work(candidate_branch)
            work_current = self.blockchain.total_work()

            if work_candidate > work_current:
                # REORGANIZATION: Nhánh phụ có tổng công việc PoW lớn hơn
                reverted_txs, disconnected_blocks = self.blockchain.reorganize(candidate_branch)

                # Hoàn trả các giao dịch ở nhánh cũ về Mempool
                for r_tx in reverted_txs:
                    self.mempool.add_transaction(r_tx, self.blockchain)

                # Loại bỏ các giao dịch đã được đóng gói trong nhánh mới khỏi Mempool
                for b in candidate_branch:
                    self.mempool.remove_transactions([t.tx_id for t in b.transactions])

                self.network.log_event(
                    self.node_id,
                    f"🔄 REORG COMPLETED: Chuyển sang nhánh mới có tổng PoW lớn hơn! "
                    f"(Work: {work_candidate:,} > {work_current:,}). "
                    f"Đã gỡ {len(disconnected_blocks)} block, hoàn trả {len(reverted_txs)} TX về Mempool. "
                    f"Height mới: {self.height}",
                )
            else:
                self.network.log_event(
                    self.node_id,
                    f"🔱 FORK STORED: Đã lưu nhánh phụ tại height {block.height} "
                    f"(Work nhánh phụ: {work_candidate:,} ≤ Chuỗi chính: {work_current:,}). "
                    f"Giữ nguyên chuỗi chính.",
                )

    # ── SYNC handlers ──

    def _handle_sync_request(self, msg: Message):
        """Peer yêu cầu chain → gửi bản sao chain hiện tại."""
        with self._state_lock:
            chain_copy = copy.deepcopy(self.blockchain)
            response = Message("SYNC_RESPONSE", self.node_id, chain_copy)
            self.network.send(self.node_id, msg.sender_id, response)
            self.network.log_event(
                self.node_id,
                f"SYNC_RESPONSE → {msg.sender_id} (height {self.height}, work {self.blockchain.total_work():,})",
            )

    def _handle_sync_response(self, msg: Message, prefer_equal: bool = False):
        """Nhận chain từ peer — chấp nhận nếu có tổng công việc PoW lớn hơn và hợp lệ.

        Điểm mô phỏng: PoW dùng 16^difficulty, PoS dùng 1 điểm/khối.
        prefer_equal chỉ dùng cho nút Sync all để chọn thống nhất khi bằng điểm.
        Khi chuyển chuỗi, các TX ở chuỗi cũ được hoàn trả lại Mempool.
        """
        with self._state_lock:
            peer_bc = msg.payload
            ok, _, reason = peer_bc.is_chain_valid(
                pos_registry=self.network.pos_registry,
                authorized_issuers=self.mempool.authorized_issuers,
            )
            if not ok:
                self.network.log_event(self.node_id, f"CHAIN REJECTED from {msg.sender_id}: {reason}")
                return
            peer_work = peer_bc.total_work()
            my_work = self.blockchain.total_work()
            current_ok, _, _ = self.blockchain.is_chain_valid(
                pos_registry=self.network.pos_registry,
                authorized_issuers=self.mempool.authorized_issuers,
            )
            if current_ok and (peer_work < my_work or (peer_work == my_work and not prefer_equal)):
                self.network.log_event(
                    self.node_id,
                    f"SYNC SKIP from {msg.sender_id}: peer work {peer_work:,}, my work {my_work:,}",
                )
                return

            reverted_txs, disconnected_blocks = self.blockchain.reorganize(peer_bc.chain)
            for r_tx in reverted_txs:
                self.mempool.add_transaction(r_tx, self.blockchain)
            for b in self.blockchain.chain:
                self.mempool.remove_transactions([t.tx_id for t in b.transactions])

            self.network.log_event(
                self.node_id,
                f"🔄 CHAIN SYNCED & REORG from {msg.sender_id}: "
                f"Height: {self.height}, Total Work: {self.blockchain.total_work():,}, "
                f"Hoàn trả {len(reverted_txs)} TX về Mempool.",
            )




class Network:
    """Mạng ngang hàng mô phỏng — kết nối các Node với nhau.

    Vì sao tồn tại: trong blockchain thật, node giao tiếp qua TCP/IP.
    Ở đây dùng queue để mô phỏng — mỗi node nhận message qua inbox,
    giữ nguyên nguyên lý: mọi node bình đẳng, tự xác minh.
    """

    def __init__(self, pos_registry=None, consensus_seed: int = 42):
        self.nodes: dict[str, Node] = {}
        self._event_log: list[str] = []
        self._log_lock = threading.Lock()
        self.consensus_seed = consensus_seed
        if pos_registry is None:
            from blockchain.pos import create_trustprofile_consortium
            self.pos_registry = create_trustprofile_consortium()
        else:
            self.pos_registry = pos_registry

    def create_node(self, node_id: str, host: str, port: int,
                    authorized_issuers: set[str] | None = None) -> Node:
        """Tạo và đăng ký node mới vào mạng."""
        node = Node(node_id, host, port, self, authorized_issuers)
        self.nodes[node_id] = node
        self.log_event(node_id, f"Registered at {host}:{port}")
        return node

    def send(self, from_id: str, to_id: str, message: Message) -> bool:
        """Gửi message trực tiếp đến 1 node."""
        if to_id in self.nodes:
            target = self.nodes[to_id]
            if target.status == "ONLINE":
                target.inbox.put(copy.deepcopy(message))
                return True
        return False

    def broadcast(self, from_id: str, message: Message) -> None:
        """Gửi message cho tất cả node khác đang ONLINE."""
        for node_id, node in self.nodes.items():
            if node_id != from_id and node.status == "ONLINE":
                node.inbox.put(copy.deepcopy(message))

    def log_event(self, node_id: str, event: str) -> None:
        """Ghi log thread-safe, có timestamp và node_id."""
        with self._log_lock:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._event_log.append(f"[{ts}] [{node_id}] {event}")

    def get_event_log(self, last_n: int = 50) -> list[str]:
        """Trả về n dòng log gần nhất."""
        with self._log_lock:
            return list(self._event_log[-last_n:])

    def clear_event_log(self) -> None:
        """Xoá toàn bộ log."""
        with self._log_lock:
            self._event_log.clear()

    def sync_all_nodes(self, *, online_only: bool = False) -> None:
        """Reuse chain selection; online_only leaves offline nodes untouched.

        Default keeps the existing UI behavior of bringing all nodes online.
        Workers acquire only their own lock; hold all locks in ID order here.
        """
        with ExitStack() as locks:
            for node in sorted(self.nodes.values(), key=lambda n: n.node_id):
                locks.enter_context(node._state_lock)
            nodes = [n for n in self.nodes.values() if not online_only or n.status == "ONLINE"]
            best_node = None
            best_work = -1
            for node in nodes:
                if not online_only:
                    node.status = "ONLINE"
                ok, _, _ = node.blockchain.is_chain_valid(
                    pos_registry=self.pos_registry,
                    authorized_issuers=node.mempool.authorized_issuers,
                )
                if not ok:
                    continue
                w = node.blockchain.total_work()
                if w > best_work or (w == best_work and (best_node is None or node.height > best_node.height)):
                    best_work = w
                    best_node = node

            if best_node:
                with best_node._state_lock:
                    best_chain = copy.deepcopy(best_node.blockchain)
                for node in nodes:
                    if node.node_id != best_node.node_id:
                        node._handle_sync_response(
                            Message("SYNC_RESPONSE", best_node.node_id, copy.deepcopy(best_chain)),
                            prefer_equal=True,
                        )
                self.log_event("Network", f"🔄 SYNC ALL: Đã đồng bộ các node được chọn theo {best_node.node_id} (Height {best_node.height})")

