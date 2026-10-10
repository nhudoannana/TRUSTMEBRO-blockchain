"""Cookie-owned, bounded Fork/Reorg backend; no frontend or HTTP repair."""
import copy
import re
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictInt, StrictStr, StrictBool, AfterValidator, field_validator

from api.session_store import current_session
from blockchain.block import Block
from blockchain.blockchain import Blockchain, calculate_chain_work, block_work
from blockchain.fork_transport import ControlledNetwork
from blockchain.node import Message
from blockchain.transaction import Transaction
from blockchain.wallet import generate_wallet

router = APIRouter(prefix="/api/labs/fork", tags=["fork"])
NodeId = Literal["Node-1", "Node-2", "Node-3"]


def hex_hash(value):
    if re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("Hash cần 64 ký tự hexadecimal")
    return value.lower()


Hex64 = Annotated[StrictStr, AfterValidator(hex_hash)]


class EmptyRequest(BaseModel):
    model_config = {"extra": "forbid"}


class Revision(EmptyRequest):
    expected_revision: StrictInt = Field(ge=0)


class LinkChange(EmptyRequest):
    a: NodeId
    b: NodeId
    connected: StrictBool


class LinksRequest(Revision):
    changes: list[LinkChange] = Field(min_length=1, max_length=3)


class StatusRequest(Revision):
    status: Literal["ONLINE", "OFFLINE"]


class TransactionRequest(Revision):
    node_id: NodeId
    label: StrictStr = Field(min_length=1, max_length=120)

    @field_validator("label")
    @classmethod
    def valid_label(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Nhãn không được trống")
        value.encode("utf-8")
        return value


class MineRequest(Revision):
    node_id: NodeId
    parent_hash: Hex64
    difficulty: StrictInt = Field(ge=1, le=3)
    tx_ids: list[Hex64] = Field(max_length=10)

    @field_validator("tx_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("TxID không được trùng")
        return values


class MessageRequest(Revision):
    message_id: StrictStr = Field(min_length=1, max_length=64)


class SyncRequest(Revision):
    node_id: NodeId


class ScenarioRequest(Revision):
    scenario: Literal["E1", "E2", "E4", "E5"]


def conflict(code, message):
    raise HTTPException(409, detail={"code": code, "message": message})


class ForkLab:
    def __init__(self):
        self.network = ControlledNetwork()
        self.issuer = generate_wallet()
        self.transactions = {}
        self.revision = 0
        for key in ("Node-1", "Node-2", "Node-3"):
            self.network.create_node(key, "manual", 0, {self.issuer.public_key_hex})

    def online(self, key):
        node = self.network.nodes[key]
        if node.status != "ONLINE":
            conflict("offline", "Node đang offline")
        return node

    def transaction(self, key, label):
        node = self.online(key)
        if len(self.transactions) >= 32 or len(node.mempool.get_transactions()) >= 32:
            conflict("transaction_capacity", "Lab tối đa 32 giao dịch và 32 pending/node")
        tx = Transaction("ISSUE", self.issuer.public_key_hex,
                         {"credential_id": uuid.uuid4().hex, "label": label})
        tx.sign(self.issuer)
        ok, reason = node.submit_transaction(tx)
        if not ok:
            conflict("transaction_rejected", reason)
        self.transactions[tx.tx_id] = tx
        return tx

    def mine(self, key, parent_hash, difficulty, tx_ids, entry):
        from api.wallet_api import _mine_lab_block_bounded
        node = self.online(key)
        if len(self.network.admitted_hashes()) >= self.network.MAX_BLOCKS:
            conflict("block_capacity", "Lab tối đa 12 block không phải genesis")
        branch = node.blockchain.branch_to_tip(parent_hash)
        if branch is None:
            conflict("unknown_parent", "Miner phải biết và xác minh parent")
        parent = Blockchain()
        parent.chain = branch
        valid, _, reason = parent.is_chain_valid(
            pos_registry=self.network.pos_registry, authorized_issuers=node.mempool.authorized_issuers)
        if not valid:
            conflict("invalid_parent", reason)
        if any(tx_id not in self.transactions for tx_id in tx_ids):
            conflict("unknown_transaction", "TxID phải được ký và sở hữu bởi lab này")
        txs = [copy.deepcopy(self.transactions[tx_id]) for tx_id in tx_ids]
        block = Block(txs, branch[-1].height + 1, parent_hash, difficulty=difficulty)
        mining = _mine_lab_block_bounded(block)
        if time.monotonic() >= entry["expires"] or self.network.closed:
            raise HTTPException(404, detail="Lab hết hạn hoặc đã reset; không publish kết quả đào")
        if not mining["completed"]:
            self.network.event(key, "mining_incomplete", mining["reason"])
            return {"code": "mining_incomplete", "message": mining["reason"], "mining": mining}
        valid, reason = node._validate_candidate(block)
        if not valid:
            self.network.event(key, "candidate_rejected", reason)
            return {"code": "candidate_rejected", "message": reason, "mining": mining}
        result = self.network._block(node, Message("BLOCK", key, block), self.network.sequence + 1)
        self.network.retry_orphans(node)
        return {**result, "block_hash": block.compute_hash(), "mining": mining}

    def snapshot(self, handle, entry):
        network = self.network
        network.expire_orphans()
        rows = []
        for key, node in network.nodes.items():
            with node._state_lock:
                bc = node.blockchain
                valid, _, reason = bc.is_chain_valid(
                    pos_registry=network.pos_registry, authorized_issuers=node.mempool.authorized_issuers)
                active = {b.compute_hash() for b in bc.chain}
                blocks = [{"hash": h, "parent_hash": b.header.previous_hash, "height": b.height,
                           "difficulty": b.header.difficulty, "work": block_work(b.header.difficulty) if b.height else 0,
                           "tx_ids": [t.tx_id for t in b.transactions],
                           "classification": "active" if h in active else "stale"}
                          for h, b in bc.block_pool.items()]
                branches, seen = [], set()
                for tip in [bc.chain[-1]] + [path[-1] for path in bc.side_branches if path]:
                    h = tip.compute_hash()
                    if h in seen:
                        continue
                    seen.add(h)
                    path = bc.branch_to_tip(h)
                    if not path:
                        continue
                    candidate = Blockchain()
                    candidate.chain = path
                    ok, _, _ = candidate.is_chain_valid(
                        pos_registry=network.pos_registry, authorized_issuers=node.mempool.authorized_issuers)
                    branches.append(dict(tip_hash=h, path_hashes=[b.compute_hash() for b in path],
                                         chain_work=calculate_chain_work(path), valid=ok, selected=h == bc.chain[-1].compute_hash()))
                credentials = {t.payload["credential_id"] for t in self.transactions.values()}
                rows.append(dict(node_id=key, status=node.status, state_revision=node.state_revision,
                                 height=node.height, tip_hash=bc.chain[-1].compute_hash(), chain_work=bc.total_work(),
                                 chain_valid=valid, validity_reason=reason, blocks=blocks, branches=branches,
                                 mempool=[t.to_dict() for t in node.mempool.get_transactions()],
                                 credential_states={c: {"status": bc.credential_status(c), "issuer": bc.credential_issuer(c),
                                                       "confirmed_tx_ids": [t.tx_id for b in bc.chain for t in b.transactions
                                                                            if t.payload.get("credential_id") == c]}
                                                    for c in credentials},
                                 orphans=[dict(hash=h, parent_hash=item["message"].payload.header.previous_hash,
                                               sequence=item["sequence"], classification="orphan",
                                               expires_in_seconds=max(0, int(network.ORPHAN_TTL - (time.monotonic()-item["received"]))))
                                          for h, item in network.orphans[key].items()],
                                 last_transition=copy.deepcopy(node.last_transition)))
        return dict(context_generation=current_session().generation, lab_handle=handle, revision=self.revision,
                    expires_in_seconds=max(0, int(entry["expires"] - time.monotonic())), delivery_mode="manual",
                    tie_policy="keep_valid_current", nodes=rows,
                    links=[{"a": a, "b": b, "connected": frozenset((a, b)) in network.links}
                           for a, b in (("Node-1","Node-2"), ("Node-1","Node-3"), ("Node-2","Node-3"))],
                    pending_messages=[dict(id=e["id"], sequence=e["sequence"], **{"from": e["from"], "to": e["to"]},
                                           kind=e["message"].msg_type, reference=network.reference(e["message"]),
                                           blocked_reason=network.blocked_reason(e["from"], e["to"]))
                                      for e in network.pending.values()],
                    events=copy.deepcopy(network.events), event_cursor=network.event_cursor,
                    events_truncated=network.events_truncated)


def load_scenario(lab, scenario, entry):
    network = lab.network
    if lab.transactions or network.admitted_hashes() or network.pending:
        conflict("scenario_requires_empty", "Nạp kịch bản cần lab mới; reset handle cũ trước")
    completed = []

    def mine(key, difficulty, txs=()):
        parent = network.nodes[key].blockchain.chain[-1].compute_hash()
        result = lab.mine(key, parent, difficulty, [t.tx_id for t in txs], entry)
        if result["code"] != "accepted_block":
            raise ValueError(result["message"])
        completed.append(dict(operation="mine", node_id=key, block_hash=result["block_hash"],
                              mining=result["mining"]))
        return result["block_hash"]

    def message(block_hash, recipient):
        return next(e["id"] for e in network.pending.values()
                    if e["to"] == recipient and e["message"].msg_type == "BLOCK"
                    and network.reference(e["message"]) == block_hash)

    try:
        if scenario == "E1":
            a = lab.transaction("Node-1", "E1 — nhánh A")
            a_hash = mine("Node-1", 2, [a])
            network.deliver(message(a_hash, "Node-2"))
            b = lab.transaction("Node-3", "E1 — nhánh B")
            b_hash = mine("Node-3", 2, [b])
            network.set_link("Node-1", "Node-3", False)
            network.set_link("Node-2", "Node-3", False)
            continuation = dict(message_id=message(b_hash, "Node-1"),
                                reconnect=[dict(a=a, b="Node-3", connected=True) for a in ("Node-1", "Node-2")],
                                next_steps=["Nối lại link", "Giao B tới Node-1: hòa work giữ A",
                                            "Đào thêm trên B ở Node-3 rồi giao: tổng work lớn hơn thắng"])
        elif scenario in ("E2", "E4"):
            for a, b in (("Node-1","Node-2"), ("Node-1","Node-3"), ("Node-2","Node-3")):
                network.set_link(a, b, False)
            a = lab.transaction("Node-1", scenario + " — nhánh A")
            mine("Node-1", 2 if scenario == "E2" else 1, [a])
            if scenario == "E2":
                mine("Node-1", 2)
                mine("Node-1", 2)
            b = lab.transaction("Node-3", scenario + " — nhánh B")
            b_hash = mine("Node-3", 3 if scenario == "E2" else 2, [b])
            network.set_link("Node-1", "Node-3", True)
            if scenario == "E4":
                network.send("Node-3", "Node-1", Message("TX", "Node-3", b))
                tx_message = next(e["id"] for e in network.pending.values() if e["message"].msg_type == "TX")
                network.deliver(tx_message)
            network.send("Node-3", "Node-1", Message("BLOCK", "Node-3", network.nodes["Node-3"].blockchain.chain[-1]))
            continuation = dict(message_id=message(b_hash, "Node-1"),
                                next_steps=["Giao B tới Node-1; xem work và transition thật"],
                                detached_tx_id=a.tx_id, credential_id=a.payload["credential_id"])
        else:
            network.set_link("Node-1", "Node-3", False)
            network.set_link("Node-2", "Node-3", False)
            tx = lab.transaction("Node-1", "E5 — parent")
            parent = mine("Node-1", 1, [tx])
            child = mine("Node-1", 1)
            continuation = dict(parent_message_id=message(parent, "Node-2"),
                                child_message_id=message(child, "Node-2"),
                                next_steps=["Giao child trước: chưa biết cha", "Giao parent: retry và full validation"])
        network.event("Network", "scenario_ready", f"{scenario}: dừng trước hành động quyết định")
        return dict(code="scenario_ready", message="Đã nạp bằng miner, validator và delivery thật",
                    continuation=continuation, setup_completed_steps=completed)
    except Exception as exc:
        network.event("Network", "scenario_incomplete", str(exc))
        return dict(code="scenario_incomplete", message=f"Nạp chưa hoàn tất: {exc}",
                    continuation=None, setup_completed_steps=completed)


@contextmanager
def owned_entry(handle):
    from api.wallet_api import _get_lab_network
    context = current_session()
    # Same lifecycle lock as existing labs; serializes bounded actions with reset/expiry.
    with context.lab_network_lock:
        entry = _get_lab_network(handle, "fork")
        with entry["network"].lock:
            yield entry


@router.post("", status_code=201)
def create_fork(body: EmptyRequest):
    from api.wallet_api import _LAB_NETWORK_TTL, _LAB_NETWORK_LIMIT, _expire_lab_network
    context = current_session()
    with context.lab_network_lock:
        for handle in list(context.lab_networks):
            _expire_lab_network(handle)
        if len(context.lab_networks) >= _LAB_NETWORK_LIMIT:
            raise HTTPException(429, detail="Đã đủ lab tạm; reset lab không dùng")
        lab = ForkLab()
        handle = context.fork_owner + "." + uuid.uuid4().hex
        timer = threading.Timer(_LAB_NETWORK_TTL, _expire_lab_network, args=(handle, context))
        timer.daemon = True
        entry = dict(kind="fork", transport="queue", network=lab.network, lab=lab,
                     expires=time.monotonic()+_LAB_NETWORK_TTL, timer=timer)
        try:
            context.lab_networks[handle] = entry
            snapshot = lab.snapshot(handle, entry)
            timer.start()
            return snapshot
        except Exception:
            context.lab_networks.pop(handle, None)
            timer.cancel()
            lab.network.close()
            raise


@router.get("/{handle}")
def get_fork(handle: str):
    with owned_entry(handle) as entry:
        return entry["lab"].snapshot(handle, entry)


@router.delete("/{handle}")
def delete_fork(handle: str):
    from api.wallet_api import _close_lab_network
    with current_session().lab_network_lock:
        if not handle.startswith(current_session().fork_owner + "."):
            raise HTTPException(404, detail="Handle không thuộc phiên lab này")
        entry = current_session().lab_networks.get(handle)
        if entry is None:
            # Idempotent deletion does not disclose whether another session owns it.
            return {"cleared": False}
        return {"cleared": _close_lab_network(handle, "fork")}


def mutate(handle, body, operation, node_id=None):
    with owned_entry(handle) as entry:
        lab, network = entry["lab"], entry["network"]
        if body.expected_revision != lab.revision:
            conflict("stale_revision", "State đã đổi; GET snapshot mới, không tự retry mutation")
        before = {key: n.state_revision for key, n in network.nodes.items()}
        result = dict(code="updated", message="Đã cập nhật state thật")
        if operation == "links":
            pairs = [frozenset((c.a, c.b)) for c in body.changes]
            if any(c.a == c.b for c in body.changes) or len(set(pairs)) != len(pairs):
                conflict("invalid_links", "Link cần hai node khác nhau; không lặp cặp")
            for c in body.changes:
                network.set_link(c.a, c.b, c.connected)
        elif operation == "status":
            network.nodes[node_id].status = body.status
            network.event(node_id, "status_changed", f"Node → {body.status}; không tự đồng bộ")
        elif operation == "transactions":
            tx = lab.transaction(body.node_id, body.label)
            result = dict(code="accepted_tx", message="Đã ký và Node nhận TX", transaction=tx.to_dict())
        elif operation == "mine":
            result = lab.mine(body.node_id, body.parent_hash, body.difficulty, body.tx_ids, entry)
        elif operation in ("deliver", "discard"):
            try:
                result = getattr(network, operation)(body.message_id)
            except KeyError:
                conflict("unknown_message", "Tin đã giao/bỏ hoặc không thuộc lab này")
        elif operation == "sync":
            previous_ids = set(network.pending)
            lab.online(body.node_id).request_sync()
            scheduled = len(set(network.pending) - previous_ids)
            result = dict(code="sync_scheduled" if scheduled else "sync_not_scheduled",
                          message="Đã xếp yêu cầu; cần giao request và response" if scheduled else
                                  "Không xếp tin mới; xem pending/events về link, offline, trùng hoặc giới hạn",
                          scheduled_count=scheduled)
        elif operation == "scenario":
            result = load_scenario(lab, body.scenario, entry)
        if time.monotonic() >= entry["expires"]:
            raise HTTPException(404, detail="Lab đã hết hạn")
        lab.revision += 1
        changed = [n for key, n in network.nodes.items() if n.state_revision != before[key]]
        transition = copy.deepcopy(changed[-1].last_transition) if changed else None
        return dict(action_id=uuid.uuid4().hex, revision=lab.revision,
                    outcome={"code": result["code"], "message": result["message"]}, transition=transition,
                    snapshot=lab.snapshot(handle, entry), **{k: v for k, v in result.items() if k not in ("code","message")})


@router.post("/{handle}/links")
def links(handle: str, body: LinksRequest):
    return mutate(handle, body, "links")


@router.post("/{handle}/nodes/{node_id}/status")
def status(handle: str, node_id: NodeId, body: StatusRequest):
    return mutate(handle, body, "status", node_id)


@router.post("/{handle}/transactions")
def transaction(handle: str, body: TransactionRequest):
    return mutate(handle, body, "transactions")


@router.post("/{handle}/mine")
def mine(handle: str, body: MineRequest):
    return mutate(handle, body, "mine")


@router.post("/{handle}/deliver")
def deliver(handle: str, body: MessageRequest):
    return mutate(handle, body, "deliver")


@router.post("/{handle}/discard")
def discard(handle: str, body: MessageRequest):
    return mutate(handle, body, "discard")


@router.post("/{handle}/sync")
def sync(handle: str, body: SyncRequest):
    return mutate(handle, body, "sync")


@router.post("/{handle}/scenario")
def scenario(handle: str, body: ScenarioRequest):
    return mutate(handle, body, "scenario")
