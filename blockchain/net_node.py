"""Module net_node — Full Node giao tiếp qua HTTP thật.

Mục đích: chạy node trên một cổng TCP thật (CLI riêng hoặc thread thuộc
web lab). Giao tiếp bằng HTTP POST với payload JSON.
Giữ nguyên chế độ queue hiện có cho mô phỏng trong Streamlit.

Không dùng pickle, không chia sẻ private key qua mạng,
không có server trung tâm — mỗi node tự xác minh mọi thứ.
"""

import copy
import json
import secrets
import threading
import time
import urllib.request
import urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from blockchain.block import Block, BlockHeader
from blockchain.blockchain import Blockchain
from blockchain.mempool import Mempool
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import mine_block, is_valid_pow, is_acceptable_pow, MIN_POW_DIFFICULTY
from blockchain.transaction import Transaction, Credential, verify_transaction


# ── Serialization helpers ──

def tx_to_json(tx: Transaction) -> dict:
    """Chuyển Transaction thành dict JSON-safe."""
    return tx.to_dict()


def tx_from_json(d: dict) -> Transaction:
    """Tái tạo Transaction từ dict JSON."""
    tx = Transaction(
        tx_type=d["tx_type"],
        sender_public_key=d["sender_public_key"],
        payload=d["payload"],
        nonce=d["nonce"],
        timestamp=d["timestamp"],
    )
    tx.signature = d.get("signature")
    tx.tx_id = d.get("tx_id", tx.compute_hash())
    return tx


def block_to_json(block: Block) -> dict:
    """Chuyển Block thành dict JSON-safe."""
    return {
        "height": block.height,
        "transaction_count": block.transaction_count,
        "transactions": [tx_to_json(tx) for tx in block.transactions],
        "header": {
            "version": block.header.version,
            "previous_hash": block.header.previous_hash,
            "merkle_root": block.header.merkle_root,
            "timestamp": block.header.timestamp,
            "difficulty": block.header.difficulty,
            "nonce": block.header.nonce,
            "consensus_type": block.header.consensus_type,
            "validator_address": block.header.validator_address,
            "validator_signature": block.header.validator_signature,
        },
    }


def block_from_json(d: dict) -> Block:
    """Tái tạo Block từ dict JSON."""
    txs = [tx_from_json(td) for td in d["transactions"]]
    h = d["header"]
    block = Block.__new__(Block)
    block.transactions = txs
    block.height = d["height"]
    block.transaction_count = d["transaction_count"]
    block.header = BlockHeader(
        version=h["version"],
        previous_hash=h["previous_hash"],
        merkle_root=h["merkle_root"],
        timestamp=h["timestamp"],
        difficulty=h["difficulty"],
        nonce=h["nonce"],
        consensus_type=h.get("consensus_type", "PoW"),
        validator_address=h.get("validator_address", ""),
        validator_signature=h.get("validator_signature", ""),
    )
    return block


def chain_to_json(blockchain: Blockchain) -> list[dict]:
    """Serialize toàn bộ chain thành list JSON."""
    return [block_to_json(b) for b in blockchain.chain]


def chain_from_json(blocks_json: list[dict]) -> Blockchain:
    """Tái tạo Blockchain từ list block JSON."""
    bc = Blockchain.__new__(Blockchain)
    bc.chain = []
    bc.block_pool = {}
    bc.side_branches = []
    for bd in blocks_json:
        block = block_from_json(bd)
        bc.chain.append(block)
        bc.block_pool[block.compute_hash()] = block
    return bc


# ── NetNode: node chạy trong tiến trình riêng ──

class NetNode:
    """Full node giao tiếp qua HTTP thật.

    Mỗi instance có HTTP server riêng; có thể chạy trong cùng process của lab.
    Tự xác minh mọi TX, Block và quy tắc ledger.
    """

    def __init__(self, node_id: str, host: str, port: int,
                 peers: list[tuple[str, str, int]],
                 authorized_issuers: set[str] | None = None, *, miner=mine_block):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers = peers  # [(peer_id, peer_host, peer_port), ...]

        self.blockchain = Blockchain()
        self.mempool = Mempool(authorized_issuers)
        self.status = "ONLINE"
        self._miner = miner

        self._seen_msg_ids: set[str] = set()
        self._seen_tx_ids: set[str] = set()
        self._lock = threading.RLock()
        self._log: list[str] = []
        self._log_lock = threading.Lock()

        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None

    # ── Logging ──

    def log(self, event: str):
        """Ghi log thread-safe."""
        with self._log_lock:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            entry = f"[{ts}] [{self.node_id}] {event}"
            self._log.append(entry)
            try:
                print(entry)
            except UnicodeEncodeError:
                print(entry.encode("ascii", errors="replace").decode("ascii"))

    def get_log(self, last_n: int = 100) -> list[str]:
        with self._log_lock:
            return list(self._log[-last_n:])

    # ── HTTP Server ──

    def start(self):
        """Khởi động HTTP server trên port đã chỉ định."""
        node = self

        class Handler(BaseHTTPRequestHandler):
            def _safe_response(self, code, result):
                """Send JSON response safely."""
                try:
                    body = json.dumps(result).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    pass

            def _read_json(self):
                """Read and parse JSON body."""
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                if not body or length == 0:
                    return {}
                return json.loads(body.decode("utf-8"))

            def do_POST(self):
                try:
                    data = self._read_json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._safe_response(400, {"error": "invalid json"})
                    return

                try:
                    if self.path == "/status":
                        if type(data.get('online')) is not bool:
                            self._safe_response(422, {'error': 'online must be boolean'})
                            return
                        with node._lock:
                            changed = (node.status == 'ONLINE') != data['online']
                            node.status = 'ONLINE' if data['online'] else 'OFFLINE'
                        node.log(f"HTTP status: {node.status}")
                        result = {'ok': True, 'changed': changed, 'catch_up_requested': False}
                    elif node.status != 'ONLINE':
                        result = {'ok': False, 'reason': 'Node OFFLINE'}
                    elif self.path == "/message":
                        result = node._handle_message(data)
                    elif self.path == "/submit_tx":
                        result = node._api_submit_tx(data)
                    elif self.path == "/mine":
                        result = node._api_mine(data)
                    elif self.path == "/sync":
                        result = node._api_sync()
                    else:
                        self._safe_response(404, {"error": "not found"})
                        return
                    self._safe_response(200, result)
                except Exception as e:
                    node.log(f"❌ Handler error on {self.path}: {e}")
                    self._safe_response(500, {"ok": False, "error": str(e)})

            def do_GET(self):
                try:
                    if self.path == "/status":
                        result = node._api_status()
                    elif self.path.startswith('/snapshot?'):
                        from urllib.parse import parse_qs, urlsplit
                        credential_id = parse_qs(urlsplit(self.path).query).get('credential_id', [None])[0]
                        result = node._api_snapshot(credential_id)
                    elif self.path == "/log":
                        result = {"log": node.get_log()}
                    else:
                        self._safe_response(404, {"error": "not found"})
                        return
                    self._safe_response(200, result)
                except Exception as e:
                    node.log(f"❌ Handler error on {self.path}: {e}")
                    self._safe_response(500, {"ok": False, "error": str(e)})

            def log_message(self, format, *args):
                pass  # Tắt log HTTP mặc định

        self._server = HTTPServer((self.host, self.port), Handler)
        self.port = self._server.server_address[1]  # port=0 reserves an OS-owned ephemeral port.
        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name=f"http-{self.node_id}",
        )
        self._server_thread.start()
        self.log(f"HTTP server started on {self.host}:{self.port}")

    def stop(self):
        """Dừng HTTP server."""
        if self._server:
            if self._server_thread and self._server_thread.is_alive():
                self._server.shutdown()
                self._server_thread.join(timeout=5)
            self._server.server_close()
            self.log("HTTP server stopped")

    # ── Gửi message cho peer ──

    def _send_to_peer(self, peer_host: str, peer_port: int, msg: dict,
                      timeout: float = 3.0) -> dict | None:
        """Gửi JSON message qua HTTP POST. Trả về response hoặc None nếu lỗi."""
        url = f"http://{peer_host}:{peer_port}/message"
        try:
            data = json.dumps(msg).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                OSError, TimeoutError, json.JSONDecodeError) as e:
            self.log(f"⚠️ Cannot reach {peer_host}:{peer_port}: {type(e).__name__}")
            return None

    def _broadcast(self, msg: dict):
        """Gửi message cho tất cả peer, bỏ qua peer không kết nối được."""
        for peer_id, peer_host, peer_port in self.peers:
            self._send_to_peer(peer_host, peer_port, msg)

    # ── API endpoints ──

    def _api_submit_tx(self, tx_dict: dict) -> dict:
        """Nhận TX từ client, verify, thêm mempool, broadcast cho peers."""
        tx = tx_from_json(tx_dict)
        with self._lock:
            ok, reason = self.mempool.add_transaction(tx, self.blockchain)
            if not ok:
                self.log(f"TX REJECT: {reason}")
                return {"ok": False, "reason": reason}

            self._seen_tx_ids.add(tx.tx_id)
            self.log(f"TX ACCEPT: {tx.tx_id[:16]}…")

        # Broadcast cho peers
        msg_id = secrets.token_hex(8)
        self._seen_msg_ids.add(msg_id)
        msg = {
            "msg_type": "TX",
            "msg_id": msg_id,
            "sender_id": self.node_id,
            "payload": tx_to_json(tx),
        }
        self._broadcast(msg)
        return {"ok": True, "reason": "Accepted", "tx_id": tx.tx_id}

    def _api_mine(self, params: dict) -> dict:
        """Lấy TX từ mempool, tạo block, mine PoW, broadcast."""
        difficulty = params.get("difficulty", 2)
        max_txs = params.get("max_txs", 10)

        with self._lock:
            txs = self.mempool.get_transactions()[:max_txs]
            if not txs:
                return {"ok": False, "reason": "Mempool trống"}

            prev_hash = self.blockchain.get_latest_block().compute_hash()
            height = len(self.blockchain.chain)

            block = Block(
                transactions=list(txs), height=height,
                previous_hash=prev_hash, difficulty=difficulty,
            )

            self.log(f"⛏️ Mining: {len(txs)} TXs, difficulty={difficulty}")

        # Mine ngoài lock
        result = self._miner(block)
        if result.get('completed') is False:
            return {'ok': False, 'reason': result['reason'], 'mining': result}

        with self._lock:
            # Verify sau khi mine
            current_tip = self.blockchain.get_latest_block().compute_hash()
            if block.header.previous_hash != current_tip:
                return {"ok": False, "reason": "Chain đã thay đổi trong lúc mine"}

            candidate = copy.deepcopy(self.blockchain)
            candidate.add_block(block)
            valid, _, reason = candidate.is_chain_valid(authorized_issuers=self.mempool.authorized_issuers)
            if not valid:
                return {'ok': False, 'reason': reason}
            self.blockchain.add_block(block)
            tx_ids = [tx.tx_id for tx in txs]
            self.mempool.remove_transactions(tx_ids)

            self.log(
                f"⛏️ Block mined! height={height}, nonce={result['nonce']:,}, "
                f"hash={result['block_hash'][:16]}…"
            )

        # Broadcast block
        msg_id = secrets.token_hex(8)
        self._seen_msg_ids.add(msg_id)
        msg = {
            "msg_type": "BLOCK",
            "msg_id": msg_id,
            "sender_id": self.node_id,
            "payload": block_to_json(block),
        }
        self._broadcast(msg)

        return {
            "ok": True,
            "height": height,
            "nonce": result["nonce"],
            "attempts": result["attempts"],
            "seconds": result["seconds"],
            "block_hash": result["block_hash"],
            "block": block_to_json(block),
        }

    def _api_sync(self) -> dict:
        """Yêu cầu chain từ các peer, chấp nhận chain dài hơn và hợp lệ."""
        self.log("SYNC: requesting chains from peers")
        best_chain = None
        best_work = self.blockchain.total_work()

        for peer_id, peer_host, peer_port in self.peers:
            msg_id = secrets.token_hex(8)
            self._seen_msg_ids.add(msg_id)
            msg = {
                "msg_type": "SYNC_REQUEST",
                "msg_id": msg_id,
                "sender_id": self.node_id,
                "payload": None,
            }
            resp = self._send_to_peer(peer_host, peer_port, msg)
            if resp and resp.get("chain"):
                try:
                    peer_bc = chain_from_json(resp["chain"])
                    ok, _, reason = peer_bc.is_chain_valid(authorized_issuers=self.mempool.authorized_issuers)
                    if ok:
                        pw = peer_bc.total_work()
                        if pw > best_work:
                            best_work = pw
                            best_chain = peer_bc
                            self.log(f"SYNC: better chain from {peer_id} (work={pw})")
                except Exception as e:
                    self.log(f"SYNC: error parsing chain from {peer_id}: {e}")

        if best_chain:
            with self._lock:
                # Hoàn trả TX cũ về mempool
                old_tx_ids = set()
                for b in self.blockchain.chain[1:]:
                    for tx in b.transactions:
                        old_tx_ids.add(tx.tx_id)

                new_tx_ids = set()
                for b in best_chain.chain[1:]:
                    for tx in b.transactions:
                        new_tx_ids.add(tx.tx_id)

                reverted = old_tx_ids - new_tx_ids
                for b in self.blockchain.chain[1:]:
                    for tx in b.transactions:
                        if tx.tx_id in reverted:
                            self.mempool.add_transaction(tx, best_chain)

                self.blockchain = best_chain
                # Xóa TX đã confirmed khỏi mempool
                for b in best_chain.chain[1:]:
                    self.mempool.remove_transactions([tx.tx_id for tx in b.transactions])

                self.log(f"SYNC: chain updated, height={len(best_chain.chain)-1}")
            return {"ok": True, "height": len(best_chain.chain) - 1}

        self.log("SYNC: no better chain found")
        return {"ok": False, "reason": "No better chain found"}

    def _api_status(self) -> dict:
        """Trả về trạng thái hiện tại của node."""
        with self._lock:
            tip = self.blockchain.get_latest_block()
            return {
                "node_id": self.node_id,
                "host": self.host,
                "port": self.port,
                "status": self.status,
                "height": len(self.blockchain.chain) - 1,
                "tip_hash": tip.compute_hash(),
                "mempool_size": len(self.mempool.get_transactions()),
                "chain_work": self.blockchain.total_work(),
            }

    def _api_snapshot(self, credential_id):
        """Public local-chain observation, also available while disconnected."""
        with self._lock:
            valid, invalid_height, reason = self.blockchain.is_chain_valid(
                pos_registry=None, authorized_issuers=self.mempool.authorized_issuers)
            verification = None
            if credential_id:
                checks, status, info = self.blockchain.verify_credential(credential_id,
                    pos_registry=None, authorized_issuers=self.mempool.authorized_issuers)
                verification = {'status': status, 'checks': checks, 'info': info,
                    'reason': info.get('reason') or next((c[2] for c in checks if not c[1]), status)}
            status = self._api_status()
            return {'node_id': self.node_id, 'status': self.status, 'height': status['height'],
                    'block_count': len(self.blockchain.chain), 'tip_hash': status['tip_hash'],
                    'pending_count': status['mempool_size'], 'chain_valid': valid,
                    'invalid_height': invalid_height, 'validity_reason': reason, 'verification': verification,
                    'local_chain_warning': 'Node OFFLINE đọc chuỗi cục bộ có thể cũ. NOT_FOUND không chứng minh hồ sơ vô hiệu.'
                    if self.status != 'ONLINE' else None, 'host': self.host, 'port': self.port}

    # ── Message handler (nhận từ peer qua HTTP) ──

    def _handle_message(self, msg: dict) -> dict:
        """Xử lý message JSON từ peer. Trả về response dict."""
        msg_type = msg.get("msg_type")
        msg_id = msg.get("msg_id", "")
        sender_id = msg.get("sender_id", "unknown")

        # Chống broadcast lặp
        if msg_id and msg_id in self._seen_msg_ids:
            return {"ok": True, "info": "already seen"}
        if msg_id:
            self._seen_msg_ids.add(msg_id)

        if msg_type == "TX":
            return self._handle_peer_tx(msg)
        elif msg_type == "BLOCK":
            return self._handle_peer_block(msg)
        elif msg_type == "SYNC_REQUEST":
            return self._handle_sync_request(msg)
        else:
            return {"ok": False, "reason": f"Unknown msg_type: {msg_type}"}

    def _handle_peer_tx(self, msg: dict) -> dict:
        """Nhận TX từ peer: verify, thêm mempool."""
        tx = tx_from_json(msg["payload"])
        with self._lock:
            if tx.tx_id in self._seen_tx_ids:
                return {"ok": True, "info": "already seen"}
            self._seen_tx_ids.add(tx.tx_id)

            ok, reason = self.mempool.add_transaction(tx, self.blockchain)
            if ok:
                self.log(f"TX ACCEPT (relay from {msg['sender_id']}): {tx.tx_id[:16]}…")
            else:
                self.log(f"TX REJECT (relay from {msg['sender_id']}): {reason}")
            return {"ok": ok, "reason": reason}

    def _handle_peer_block(self, msg: dict) -> dict:
        """Nhận block từ peer: verify merkle, PoW, TX signatures, ledger."""
        block = block_from_json(msg["payload"])
        sender_id = msg.get("sender_id", "unknown")

        with self._lock:
            # Kiểm tra merkle_root
            tx_hashes = [tx.tx_id for tx in block.transactions]
            expected_root = calculate_merkle_root(tx_hashes)
            if block.header.merkle_root != expected_root:
                self.log(f"❌ BLOCK REJECTED from {sender_id}: merkle_root không khớp")
                return {"ok": False, "reason": "merkle_root mismatch"}

            # Kiểm tra PoW
            if block.header.consensus_type == "PoW":
                if not is_acceptable_pow(block):
                    self.log(f"❌ BLOCK REJECTED from {sender_id}: PoW không hợp lệ")
                    return {"ok": False, "reason": "invalid PoW"}

            # Kiểm tra TX signatures
            for tx in block.transactions:
                ok, reason = verify_transaction(tx)
                if not ok:
                    self.log(f"❌ BLOCK REJECTED from {sender_id}: TX invalid: {reason}")
                    return {"ok": False, "reason": f"TX invalid: {reason}"}

            # Kiểm tra previous_hash
            my_tip = self.blockchain.get_latest_block().compute_hash()
            if block.header.previous_hash != my_tip:
                self.log(f"⚠️ BLOCK from {sender_id}: prev_hash mismatch, triggering sync")
                return {"ok": False, "reason": "previous_hash mismatch, need sync"}

            # Kiểm tra height
            expected_height = len(self.blockchain.chain)
            if block.height != expected_height:
                self.log(f"❌ BLOCK REJECTED from {sender_id}: height mismatch")
                return {"ok": False, "reason": "height mismatch"}

            # Kiểm tra ledger rules cho từng TX
            for tx in block.transactions:
                cred_id = tx.payload.get("credential_id", "")
                status = self.blockchain.credential_status(cred_id)
                issuer = self.blockchain.credential_issuer(cred_id)
                ai = self.mempool.authorized_issuers
                from blockchain.transaction import verify_ledger_transaction
                ok, reason = verify_ledger_transaction(tx, status, issuer, ai)
                if not ok:
                    self.log(f"❌ BLOCK REJECTED from {sender_id}: ledger: {reason}")
                    return {"ok": False, "reason": f"ledger: {reason}"}

            # Reuse full chain validation too (including consensus and intra-block ledger order).
            candidate = copy.deepcopy(self.blockchain)
            candidate.add_block(block)
            valid, _, reason = candidate.is_chain_valid(authorized_issuers=self.mempool.authorized_issuers)
            if not valid:
                return {'ok': False, 'reason': reason}
            # Accept
            self.blockchain.add_block(block)
            tx_ids = [tx.tx_id for tx in block.transactions]
            self.mempool.remove_transactions(tx_ids)

            self.log(
                f"✅ BLOCK ACCEPTED from {sender_id}: "
                f"height {block.height}, {len(block.transactions)} TXs"
            )
            return {"ok": True, "height": block.height}

    def _handle_sync_request(self, msg: dict) -> dict:
        """Peer yêu cầu chain → gửi bản sao."""
        with self._lock:
            return {"ok": True, "chain": chain_to_json(self.blockchain)}
