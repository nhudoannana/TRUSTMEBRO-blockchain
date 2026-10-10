"""Bounded manual queue; default Network and HTTP adapters stay automatic."""
import copy
import threading
import time
import uuid

from blockchain.blockchain import Blockchain
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import is_acceptable_pow
from blockchain.node import Network, Message
from blockchain.transaction import verify_transaction


class ControlledNetwork(Network):
    MAX_MESSAGES = 64
    MAX_ORPHANS = 8
    MAX_BLOCKS = 12
    MAX_PENDING = 32
    ORPHAN_TTL = 120
    delivery_mode = "manual"

    def __init__(self):
        self.lock = threading.RLock()
        self.pending, self.orphans = {}, {}
        self.links = set()
        self.events = []
        self.event_cursor = 0
        self.events_truncated = False
        self.sequence = 0
        self.closed = False
        super().__init__()

    def create_node(self, node_id, host, port, authorized_issuers=None):
        if self.closed or len(self.nodes) >= 3 or node_id in self.nodes:
            raise ValueError("Mạng manual chỉ có ba node độc lập")
        node = super().create_node(node_id, host, port, authorized_issuers)
        self.orphans[node_id] = {}
        for peer in self.nodes:
            if peer != node_id:
                self.links.add(frozenset((peer, node_id)))
        return node

    def event(self, node_id, code, message):
        with self._log_lock:
            self.event_cursor += 1
            self.events.append(dict(sequence=self.event_cursor, node_id=node_id, code=code, message=message))
            if len(self.events) > 200:
                self.events.pop(0)
                self.events_truncated = True

    def log_event(self, node_id, event):
        self.event(node_id, "node_event", event)

    def get_event_log(self, last_n=50):
        with self._log_lock:
            return [e["message"] for e in self.events[-last_n:]]

    def set_link(self, a, b, connected):
        if a not in self.nodes or b not in self.nodes or a == b:
            raise ValueError("Link cần hai node khác nhau trong lab")
        edge = frozenset((a, b))
        self.links.add(edge) if connected else self.links.discard(edge)
        self.event("Network", "link_changed", f"{a} ↔ {b}: {'nối' if connected else 'ngắt'}")

    def blocked_reason(self, sender, recipient):
        if self.closed:
            return "closed"
        if sender not in self.nodes or recipient not in self.nodes or sender == recipient:
            return "unknown_peer"
        if frozenset((sender, recipient)) not in self.links:
            return "disconnected"
        if any(self.nodes[key].status != "ONLINE" for key in (sender, recipient)):
            return "offline"
        return None

    @staticmethod
    def reference(message):
        if message.msg_type == "BLOCK":
            return message.payload.compute_hash()
        if message.msg_type == "TX":
            return getattr(message.payload, "tx_id", None)
        if message.msg_type == "SYNC_RESPONSE":
            return message.payload.get_latest_block().compute_hash()
        return None

    def send(self, from_id, to_id, message):
        with self.lock:
            blocked = self.blocked_reason(from_id, to_id)
            if blocked:
                self.event(from_id, "schedule_blocked", f"{message.msg_type} → {to_id}: {blocked}")
                return False
            ref = self.reference(message)
            target = self.nodes[to_id]
            if ((message.msg_type == "BLOCK" and (ref in target.blockchain.block_pool or ref in self.orphans[to_id]))
                    or (message.msg_type == "TX" and ref in target._seen_tx_ids)
                    or any(e["from"] == from_id and e["to"] == to_id and
                           e["message"].msg_type == message.msg_type and self.reference(e["message"]) == ref
                           for e in self.pending.values())):
                self.event(to_id, "duplicate_suppressed", f"Đã biết hoặc đã xếp hàng {message.msg_type}: {ref}")
                return False
            if len(self.pending) >= self.MAX_MESSAGES:
                self.event(from_id, "message_capacity", f"Không xếp được {message.msg_type} → {to_id}: hàng tin đầy")
                return False
            self.sequence += 1
            key = uuid.uuid4().hex
            self.pending[key] = dict(id=key, sequence=self.sequence, **{"from": from_id, "to": to_id},
                                     message=copy.deepcopy(Message(message.msg_type, from_id, message.payload)))
            self.event(from_id, "scheduled", f"{message.msg_type} → {to_id}, message_id={key}")
            return True

    def broadcast(self, from_id, message):
        for recipient in self.nodes:
            if recipient != from_id:
                self.send(from_id, recipient, message)

    def discard(self, message_id):
        with self.lock:
            if message_id not in self.pending:
                raise KeyError(message_id)
            del self.pending[message_id]
            self.event("Network", "discarded", f"Bỏ message {message_id}")
            return {"code": "discarded", "message": "Đã bỏ tin; nối lại link không hồi sinh tin này."}

    def expire_orphans(self):
        now = time.monotonic()
        for node_id, buffer in self.orphans.items():
            for key, item in list(buffer.items()):
                if now - item["received"] >= self.ORPHAN_TTL:
                    del buffer[key]
                    self.event(node_id, "orphan_expired", f"Chưa biết cha, hết hạn: {key}")

    def admitted_hashes(self):
        return {key for n in self.nodes.values() for key, b in n.blockchain.block_pool.items() if b.height > 0}

    def reject_descendants(self, node_id, parent_hash, reason):
        doomed = {parent_hash}
        while True:
            children = [h for h, item in self.orphans[node_id].items()
                        if item["message"].payload.header.previous_hash in doomed]
            if not children:
                return
            for h in children:
                del self.orphans[node_id][h]
                doomed.add(h)
                self.event(node_id, "invalid_parent", f"Loại orphan {h}: {reason}")

    def _block(self, node, message, arrival):
        block, node_id = message.payload, node.node_id
        key = block.compute_hash()
        if key in node.blockchain.block_pool:
            return dict(code="duplicate", message="Block đã được xác minh trước đó")
        if (block.header.consensus_type != "PoW" or not 1 <= block.header.difficulty <= 3
                or len(block.transactions) > 10 or not is_acceptable_pow(block)
                or block.header.merkle_root != calculate_merkle_root([t.tx_id for t in block.transactions])
                or any(not verify_transaction(t)[0] for t in block.transactions)):
            self.reject_descendants(node_id, key, "Cha thất bại kiểm tra độc lập")
            self.event(node_id, "rejected_block", f"Block {key}: PoW/Merkle/chữ ký hoặc giới hạn không hợp lệ")
            return dict(code="rejected_block", message="Block thất bại kiểm tra độc lập")
        if key not in self.admitted_hashes() and len(self.admitted_hashes()) >= self.MAX_BLOCKS:
            self.event(node_id, "block_capacity", "Đã đủ block của lab")
            return dict(code="block_capacity", message="Lab đã đủ block")
        if block.header.previous_hash not in node.blockchain.block_pool:
            if key in self.orphans[node_id]:
                return dict(code="duplicate", message="Orphan đã được giữ")
            if len(self.orphans[node_id]) >= self.MAX_ORPHANS:
                self.event(node_id, "orphan_capacity", f"Không giữ orphan {key}: buffer đầy")
                return dict(code="orphan_capacity", message="Buffer chưa biết cha đầy")
            self.orphans[node_id][key] = dict(message=copy.deepcopy(message), sequence=arrival,
                                               received=time.monotonic())
            self.event(node_id, "orphan", f"Chưa biết cha {block.header.previous_hash}, giữ {key}; chưa chấm work")
            return dict(code="orphan", message="Chưa biết cha; chưa xác minh nhánh hoặc chấm work")
        ok, reason = node._validate_candidate(block)
        if not ok:
            self.event(node_id, "rejected_block", reason)
            self.reject_descendants(node_id, key, reason)
            return dict(code="rejected_block", message=reason)
        node._handle_message(copy.deepcopy(message))
        if key not in node.blockchain.block_pool:
            return dict(code="rejected_block", message="Node không nhận block")
        self.event(node_id, "accepted_block", f"Đã xác minh block {key}")
        self.broadcast(node_id, Message("BLOCK", node_id, block))
        return dict(code="accepted_block", message="Đã xác minh và xử lý bằng Node validator/selection")

    def retry_orphans(self, node):
        buffer = self.orphans[node.node_id]
        while True:
            ready = [(key, item) for key, item in buffer.items()
                     if item["message"].payload.header.previous_hash in node.blockchain.block_pool]
            if not ready:
                return
            for key, item in sorted(ready, key=lambda pair: pair[1]["sequence"]):
                del buffer[key]
                result = self._block(node, item["message"], item["sequence"])
                self.event(node.node_id, "orphan_retried", f"{key}: {result['code']}")

    def deliver(self, message_id):
        with self.lock:
            self.expire_orphans()
            env = self.pending.get(message_id)
            if env is None:
                raise KeyError(message_id)
            blocked = self.blocked_reason(env["from"], env["to"])
            if blocked:
                self.event(env["to"], "delivery_blocked", blocked)
                return dict(code="blocked", message=f"Tin vẫn đang chờ: {blocked}")
            del self.pending[message_id]
            node, message = self.nodes[env["to"]], env["message"]
            if message.msg_type == "BLOCK":
                result = self._block(node, message, env["sequence"])
            elif message.msg_type == "TX":
                tx = message.payload
                if tx.tx_id in node._seen_tx_ids:
                    result = dict(code="duplicate", message="TxID đã biết")
                elif len(node.mempool.get_transactions()) >= self.MAX_PENDING:
                    result = dict(code="mempool_capacity", message="Mempool đầy")
                elif any(t.payload.get("credential_id") == tx.payload.get("credential_id")
                         for t in node.mempool.get_transactions()):
                    result = dict(code="pending_conflict", message="Đã có TX chờ cho credential")
                else:
                    node._handle_message(copy.deepcopy(message))
                    accepted = tx.tx_id in {t.tx_id for t in node.mempool.get_transactions()}
                    result = dict(code="accepted_tx" if accepted else "rejected_tx",
                                  message="Node đã đối chiếu giao dịch với ledger cục bộ")
                    if accepted:
                        self.broadcast(node.node_id, Message("TX", node.node_id, tx))
            else:
                if message.msg_type == "SYNC_RESPONSE":
                    candidate = message.payload
                    incoming = {b.compute_hash() for b in candidate.chain if b.height > 0}
                    if (len(self.admitted_hashes() | incoming) > self.MAX_BLOCKS
                            or len(candidate.chain) > self.MAX_BLOCKS + 1
                            or any(b.header.consensus_type != "PoW" or not 1 <= b.header.difficulty <= 3
                                   or len(b.transactions) > 10 for b in candidate.chain[1:])):
                        result = dict(code="block_capacity", message="Sync vượt giới hạn lab")
                    else:
                        ok, _, reason = candidate.is_chain_valid(
                            authorized_issuers=node.mempool.authorized_issuers, pos_registry=self.pos_registry)
                        if ok:
                            node._handle_message(copy.deepcopy(message))
                        result = dict(code="sync_processed" if ok else "rejected_sync", message=reason)
                else:
                    node._handle_message(copy.deepcopy(message))
                    result = dict(code="sync_requested", message="Đã xử lý yêu cầu và xếp phản hồi nếu link cho phép")
            self.retry_orphans(node)
            self.event(node.node_id, result["code"], result["message"])
            return result

    def sync_all_nodes(self, *, online_only=False):
        raise ValueError("manual mode cần explicit peer sync và delivery; không dùng coordinator")

    def close(self):
        with self.lock:
            self.closed = True
            self.pending.clear()
            for buffer in self.orphans.values():
                buffer.clear()
            for node in self.nodes.values():
                node.stop()
