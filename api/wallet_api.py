"""api/wallet_api.py — FastAPI application for TRUSTMEBRO Phase 1.

Serves:
  - GET  /api/wallets          → list all wallets (no private keys)
  - POST /api/wallets          → create wallet from JSON {name}
  - GET  /api/wallets/{id}     → get single wallet (no private keys)
  - Static files from ui/      → the integrated frontend
  - GET  /                     → redirects to landing.html

Design decisions:
  - Same-origin serving: FastAPI + StaticFiles mounts ui/ at /ui.
  - CORS enabled for localhost development only.
  - Private keys are never returned; validated in _public() in wallet_store.
  - No Streamlit session state shared; this is a separate process.
  - Input validation: empty name → 422, name >80 chars → 422.
"""

import os
import logging
import uuid
import time
import threading
from contextlib import ExitStack, asynccontextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator
from api.network_store import get_session_info, reset_network
from api import session_store
from api.session_store import current_session, bind_session, SimulationSessionMiddleware
from api.network_store import get_network, submit_signed_transaction, get_mempool_snapshots
from api.network_store import get_network_snapshots, get_reset_count
from blockchain.blockchain import Blockchain, verify_pos_signature
from blockchain.wallet import Wallet
from blockchain.wallet import generate_wallet, sign_message, verify_signature
from blockchain.hash import sha256_hex
from blockchain.merkle import build_merkle_tree, generate_merkle_proof, verify_merkle_proof, calculate_merkle_root
from blockchain.transaction import Credential, Transaction, verify_transaction
from blockchain.block import Block
from blockchain.mining import mine_block, is_acceptable_pow
from blockchain.node import Network
from blockchain.net_node import block_from_json
from api.http_network import HttpLabNetwork

from api.wallet_store import (
    list_wallets,
    get_wallet,
    create_wallet,
    get_private_key_pem,
)

# ── Root dirs ──────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent          # repo root
_UI_DIR   = _BASE_DIR / "ui"

# ── App ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lab_lifespan(_app):
    session_store.registry.start()
    try:
        yield
    finally:
        session_store.registry.shutdown()


app = FastAPI(
    title="TRUSTMEBRO API — Phase 1",
    description="Wallet management for the blockchain education simulation.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lab_lifespan,
)

app.add_middleware(SimulationSessionMiddleware)

# Allow localhost origins during development only.
# In production, tighten allowed_origins to the actual serving domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",           # file:// origin for direct-open HTML (dev only)
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get('/api/health')
def api_health():
    """Public liveness check; no session, network or wallet initialization."""
    return {'status': 'ok'}


@app.get('/api/session/bootstrap')
def api_session_bootstrap():
    """Establish the cookie before page API concurrency, without demo seeding."""
    context = current_session()
    with context.lock:
        return {'context_generation': context.generation, 'reset_count': context.reset_count}


# ── Pydantic models ────────────────────────────────────────────────────────

class WalletCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tên ví không được để trống.")
        if len(v) > 80:
            raise ValueError("Tên ví không được vượt quá 80 ký tự.")
        return v


class WalletResponse(BaseModel):
    id: str
    name: str
    public_key_hex: str
    address: str
    source: str


class CredentialCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    issuer_wallet_id: str
    holder_name: str
    title: str
    issue_date: str

    @field_validator("issuer_wallet_id", "holder_name", "title")
    @classmethod
    def required_text(cls, value, info):
        value = value.strip()
        limit = 80 if info.field_name == "issuer_wallet_id" else 200
        if not value or len(value) > limit:
            raise ValueError(f"{info.field_name}: cần 1–{limit} ký tự.")
        return value

    @field_validator("issue_date")
    @classmethod
    def valid_date(cls, value):
        value = value.strip()
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Ngày cấp phải có định dạng YYYY-MM-DD.")
        return value


class CredentialMetadata(BaseModel):
    credential_id: str
    issuer_name: str
    holder_name: str
    title: str
    issue_date: str
    claims_root: str


class SignedTransactionResponse(BaseModel):
    tx_id: str
    tx_type: str
    sender_public_key: str
    payload: CredentialMetadata
    nonce: str
    timestamp: str
    signature: str


class CredentialResponse(BaseModel):
    credential_id: str
    credential: CredentialMetadata
    issuer_wallet_id: str
    issuer_address: str
    transaction: SignedTransactionResponse


class MempoolSubmitRequest(BaseModel):
    model_config = {"extra": "forbid"}
    credential_id: str
    node_id: str

    @field_validator("credential_id", "node_id")
    @classmethod
    def required_id(cls, value):
        value = value.strip()
        if not value or len(value) > 200:
            raise ValueError("ID cần 1–200 ký tự.")
        return value


class MempoolSubmitResponse(BaseModel):
    credential_id: str
    node_id: str
    tx_id: str
    accepted: bool
    reason: str
    reason_source: Literal["backend", "adapter"]
    reset_count: int
    context_generation: str


class NodeMempoolSnapshot(BaseModel):
    node_id: str
    status: str
    pending_count: int
    transactions: list[dict]


class MempoolSnapshotsResponse(BaseModel):
    nodes: list[NodeMempoolSnapshot]
    reset_count: int
    context_generation: str


class PowMiningRequest(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    node_id: str = Field(min_length=1, max_length=200)


class PowMiningResponse(BaseModel):
    node_id: str
    mined: bool
    reason: str | None
    block: dict | None
    transaction_ids: list[str]
    seconds: float | None
    attempts: int | None
    reset_count: int
    context_generation: str


class PublicValidator(BaseModel):
    name: str
    public_key_hex: str
    address: str
    institution_type: str
    stake: int
    is_active: bool
    eligible: bool
    selection_weight: float


class PosConsensusResponse(BaseModel):
    node_id: str
    status: str
    validators: list[PublicValidator]
    stake_mode: str
    seed: int
    predicted_validator: PublicValidator | None
    prediction_provisional: bool
    target_height: int
    previous_hash: str
    reason: str | None
    reset_count: int
    context_generation: str


class PosMiningResponse(BaseModel):
    node_id: str
    forged: bool
    reason: str | None
    block: dict | None
    transaction_ids: list[str]
    signer: PublicValidator | None
    seconds: float
    elapsed_scope: str
    reset_count: int
    context_generation: str


class NodeStatusRequest(BaseModel):
    model_config = {"extra": "forbid"}
    online: StrictBool


class NetworkNodeSnapshot(BaseModel):
    node_id: str
    status: str
    height: int
    block_count: int
    tip_hash: str | None
    pending_count: int
    chain_valid: bool
    invalid_height: int | None
    validity_reason: str


class NetworkSnapshotResponse(BaseModel):
    nodes: list[NetworkNodeSnapshot]
    reset_count: int
    context_generation: str
    online_nodes_agree: bool
    online_nodes_valid: bool
    online_nodes_synchronized: bool
    all_nodes_synchronized: bool
    events: list[str]


class NetworkSyncResponse(BaseModel):
    completed: bool
    reason: str | None
    reason_source: Literal["backend", "adapter"] | None
    network: NetworkSnapshotResponse


class NodeStatusResponse(BaseModel):
    node_id: str
    changed: bool
    catch_up_requested: bool
    network: NetworkSnapshotResponse


class PresentedCredential(BaseModel):
    model_config = {"extra": "forbid"}
    holder_name: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    issue_date: str = Field(min_length=1, max_length=200)
    issuer_name: str = Field(min_length=1, max_length=200)


class VerifyRequest(MempoolSubmitRequest):
    presented_credential: PresentedCredential | None = None


class VerifyResponse(BaseModel):
    credential_id: str
    node_id: str
    node_status: str
    local_chain_warning: str | None
    chain_status: dict
    presentation_match: bool | None
    mismatched_fields: list[str]
    success: bool
    record_verified: bool
    presented_document_accepted: bool
    reset_count: int
    context_generation: str


class RevokeRequest(PowMiningRequest):
    issuer_wallet_id: str | None = Field(default=None, min_length=1, max_length=80)
    reason: str = Field(default="Expired", min_length=1, max_length=200)


class RevokeResponse(MempoolSubmitResponse):
    pending: bool
    transaction: dict


@app.post("/api/verify", response_model=VerifyResponse, summary="Verify the selected node's local chain and optional presentation")
def api_verify(body: VerifyRequest):
    """Offline local reads can be stale. Presentation text is compared exactly.

    Only VERIFIED/REVOKED metadata is trustworthy for comparison; REVOKED
    still supplies original ISSUE metadata, but can never produce success.
    No signed credential store is used as evidence. success retains its legacy
    meaning (ID-only VERIFIED is true); presented_document_accepted requires
    VERIFIED and an explicitly matching presentation.
    """
    with current_session().lock:
        network = get_network()
        node = network.nodes.get(body.node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại."})
        with node._state_lock:
            checks, status, info = node.blockchain.verify_credential(
                body.credential_id, authorized_issuers=node.mempool.authorized_issuers,
                pos_registry=network.pos_registry)
            mismatches = []
            match = None
            if body.presented_credential is not None and status in ("VERIFIED", "REVOKED"):
                mismatches = [key for key, value in body.presented_credential.model_dump().items() if value != info.get(key)]
                match = not mismatches
            return {"credential_id": body.credential_id, "node_id": node.node_id,
                    "node_status": node.status,
                    "local_chain_warning": "Node OFFLINE: chain cục bộ có thể lỗi thời." if node.status != "ONLINE" else None,
                    "chain_status": {"status": status, "reason": checks[-1][2], "checks": checks, "info": info},
                    "presentation_match": match, "mismatched_fields": mismatches,
                    "success": status == "VERIFIED" and match is not False,
                    "record_verified": status == "VERIFIED",
                    "presented_document_accepted": status == "VERIFIED" and match is True,
                    "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"]}


@app.post("/api/credentials/{credential_id}/revoke", response_model=RevokeResponse, summary="Sign and submit REVOKE; never mine")
def api_revoke(credential_id: str, body: RevokeRequest):
    """Resolve original issuer by public key, never organization name.

    Valid local on-chain evidence is required. Reuse D's admission lock and
    backend reasons; acceptance only means pending until explicitly mined.
    """
    if not credential_id.strip() or len(credential_id) > 200:
        raise HTTPException(422, detail="credential_id cần 1–200 ký tự.")
    with current_session().lock:
        network = get_network()
        node = network.nodes.get(body.node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại."})
        with node._state_lock:
            checks, status, info = node.blockchain.verify_credential(
                credential_id, authorized_issuers=node.mempool.authorized_issuers, pos_registry=network.pos_registry)
            if status == "NOT_FOUND":
                raise HTTPException(404, detail={"code": "credential_not_found", "message": checks[-1][2]})
            if status == "INVALID":
                raise HTTPException(409, detail={"code": "invalid_chain", "message": checks[-1][2]})
            issuer = node.blockchain.credential_issuer(credential_id)
        stored = get_wallet(body.issuer_wallet_id) if body.issuer_wallet_id else next(
            (wallet for wallet in list_wallets() if wallet["public_key_hex"] == issuer), None)
        if body.issuer_wallet_id and stored is None:
            raise HTTPException(404, detail={"code": "wallet_not_found", "message": "Ví không tồn tại hoặc phiên đã reset."})
        if stored is not None and stored["public_key_hex"] != issuer:
            raise HTTPException(403, detail={"code": "issuer_mismatch", "message": "Chỉ Issuer gốc mới có quyền thu hồi credential"})
        private_key = get_private_key_pem(stored["id"]) if stored else None
        if not private_key:
            raise HTTPException(409, detail={"code": "issuer_key_unavailable", "message": "Không có private key của issuer gốc trong phiên này."})
        wallet = Wallet(private_key, stored["public_key_hex"], stored["address"])
        tx = Transaction("REVOKE", wallet.public_key_hex, {"credential_id": credential_id, "reason": body.reason})
        tx.sign(wallet)
        accepted, reason, source = submit_signed_transaction(network, node, tx)
        return {"credential_id": credential_id, "node_id": body.node_id, "tx_id": tx.tx_id,
                "accepted": accepted, "pending": accepted, "reason": reason, "reason_source": source,
                "transaction": tx.to_dict(), "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"]}


# ── API routes ──────────────────────────────────────────────────────────────

@app.get("/api/wallets", response_model=list[WalletResponse], summary="List wallets")
def api_list_wallets():
    """Return all wallets. Private keys are never included."""
    with current_session().lock:
        return list_wallets()


@app.post(
    "/api/wallets",
    response_model=WalletResponse,
    status_code=201,
    summary="Create wallet",
)
def api_create_wallet(body: WalletCreateRequest):
    """Generate a real ECDSA wallet.

    - Returns the public representation (id, name, public_key_hex, address).
    - Private key is generated and stored server-side only.
    - Wallet persists until server restart (in-memory store, Phase 1).
    """
    try:
        with current_session().lock:
            wallet = create_wallet(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return wallet


@app.get(
    "/api/wallets/{wallet_id}",
    response_model=WalletResponse,
    summary="Get wallet by ID",
)
def api_get_wallet(wallet_id: str):
    """Return a single wallet by ID. 404 if not found."""
    with current_session().lock:
        wallet = get_wallet(wallet_id)
    if wallet is None:
        raise HTTPException(status_code=404, detail="Ví không tồn tại.")
    return wallet


# ── Static frontend ────────────────────────────────────────────────────────
# Mount /ui → ui/ directory. Only exposes ui/ contents, not the repo root.

@app.post("/api/credentials", response_model=CredentialResponse, status_code=201,
          summary="Create and sign credential; no mempool submission")
def api_create_credential(body: CredentialCreateRequest):
    """Return public metadata and Transaction.to_dict() (tx_id, public key, signature).

    Claims are outside step C: retain Credential's empty claims_root default.
    Store credential and signed transaction until this session's reset/expiry/restart.
    No submission, broadcasting or mining occurs here.
    """
    with current_session().lock:
        stored = get_wallet(body.issuer_wallet_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Ví không tồn tại. Hãy chọn lại ví ở bước 1.")
        wallet = Wallet(get_private_key_pem(stored["id"]), stored["public_key_hex"], stored["address"])
        credential = Credential(str(uuid.uuid4()), stored["name"], body.holder_name,
                                body.title, body.issue_date)
        tx = Transaction("ISSUE", wallet.public_key_hex, credential.to_onchain_payload())
        tx.sign(wallet)
        current_session().signed_credentials[credential.credential_id] = (credential, tx)
        return {
            "credential_id": tx.payload["credential_id"],
            "credential": tx.payload,
            "issuer_wallet_id": stored["id"],
            "issuer_address": wallet.address,
            "transaction": tx.to_dict(),
        }

@app.get("/api/session", summary="Current browser simulation")
def api_session():
    return get_session_info()


@app.post("/api/mempool", response_model=MempoolSubmitResponse, summary="Submit stored signed credential")
def api_submit_mempool(body: MempoolSubmitRequest):
    """200 includes accepted/rejected result; backend reason is verbatim.

    404 detail.code identifies credential_not_found or node_not_found.
    No replacement payload, signing, extra broadcast or mining.
    """
    with current_session().lock:
        stored = current_session().signed_credentials.get(body.credential_id)
        if stored is None:
            raise HTTPException(404, detail={"code": "credential_not_found", "message": "Hồ sơ đã ký không tồn tại hoặc phiên đã reset. Hãy tạo và ký lại."})
        network = get_network()
        node = network.nodes.get(body.node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại. Hãy chọn lại node."})
        tx = stored[1]
        accepted, reason, source = submit_signed_transaction(network, node, tx)
        return {"credential_id": body.credential_id, "node_id": body.node_id,
                "tx_id": tx.tx_id, "accepted": accepted, "reason": reason,
                "reason_source": source, "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"]}


@app.get("/api/mempool", response_model=MempoolSnapshotsResponse, summary="Real per-node mempool snapshots")
def api_get_mempool():
    """Nodes may differ while queue workers propagate a transaction."""
    return get_mempool_snapshots()


@app.post("/api/session/reset", summary="Reset current browser simulation")
def api_reset_session():
    with current_session().lock:
        reset_network()
        return get_session_info()


@app.get("/api/network", response_model=NetworkSnapshotResponse, summary="Real chain and node snapshots")
def api_network():
    """Height excludes genesis; block_count includes it. Per-node worker locks.

    Agreement uses both height and tip; validity is separately checked with
    the shared PoS registry and each node's authorized issuers. Not global atomicity.
    """
    return get_network_snapshots()


@app.post("/api/network/sync", response_model=NetworkSyncResponse, summary="Sync ONLINE nodes; preserve offline state")
def api_sync_network():
    """Backend sync is synchronous and returns None; outcome is observed afterward.

    The backend chooses the chain. No polling while holding worker/session locks.
    Offline nodes catch up only after their explicit go_online request.
    """
    with current_session().lock:
        try:
            get_network().sync_all_nodes(online_only=True)
        except Exception as exc:
            logging.getLogger(__name__).exception("Network sync failed")
            raise HTTPException(500, detail={"code": "sync_failed", "message": "Backend sync thất bại. Hãy làm mới trạng thái mạng."}) from exc
        snapshot = get_network_snapshots()
        invalid = next((n for n in snapshot["nodes"] if n["status"] == "ONLINE" and not n["chain_valid"]), None)
        completed = snapshot["online_nodes_synchronized"]
        reason = None if completed else (invalid["validity_reason"] if invalid else "Adapter: chưa quan sát các node ONLINE cùng height và tip hash hợp lệ.")
        return {"completed": completed, "reason": reason,
                "reason_source": None if completed else ("backend" if invalid else "adapter"), "network": snapshot}


@app.post("/api/network/nodes/{node_id}/status", response_model=NodeStatusResponse, summary="Explicit online/offline demo control")
def api_node_status(node_id: str, body: NodeStatusRequest):
    """Repeated requests are no-ops. go_online already requests queue-based sync."""
    with current_session().lock:
        node = get_network().nodes.get(node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại."})
        with node._state_lock:
            changed = (node.status == "ONLINE") != body.online
            if changed:
                if body.online:
                    node.go_online()
                else:
                    node.go_offline()
        return {"node_id": node_id, "changed": changed,
                "catch_up_requested": changed and body.online, "network": get_network_snapshots()}


@app.post("/api/mining/pow", response_model=PowMiningResponse, summary="Mine actual pending transactions with Node defaults")
def api_mine_pow(body: PowMiningRequest):
    """Node.mine_pending defaults: difficulty=3, max_txs=10; no client controls.

    block uses Block.to_dict(); height is its index. seconds/attempts come
    directly from mine_block, which hashes consecutive nonces starting at 0.
    A backend rejection returns mined=false and its reason verbatim.
    Mining already validates, removes included TXs and broadcasts the block.
    """
    with current_session().lock:
        node = get_network().nodes.get(body.node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại. Hãy chọn lại node."})
        # Session lock coordinates API/reset; this lock also protects against workers.
        # No other node lock is acquired while mining or broadcasting via queues.
        with node._state_lock:
            try:
                block, result = node.mine_pending()
            except Exception as exc:
                logging.getLogger(__name__).exception("PoW mining failed on %s", node.node_id)
                raise HTTPException(500, detail={"code": "mining_failed", "message": "Backend mining thất bại. Hãy làm mới mempool trước khi thử lại."}) from exc
            return {
                "node_id": node.node_id, "mined": block is not None,
                "reason": result if block is None else None,
                "block": block.to_dict() if block is not None else None,
                "transaction_ids": [tx.tx_id for tx in block.transactions] if block is not None else [],
                "seconds": result["seconds"] if block is not None else None,
                "attempts": result["attempts"] if block is not None else None,
                "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"],
            }


def public_pos_validators(registry):
    """Explicit public projection; caller excludes registry mutation with node locks.

    Weight is a stake ratio among eligible validators, not a frequency promise.
    Never serialize the Validator dataclass: it contains signing keys.
    """
    total = sum(v.stake for v in registry.validators.values() if v.is_active and v.stake > 0)
    return [{"name": v.name, "public_key_hex": v.public_key_hex,
             "address": v.address, "institution_type": v.institution_type,
             "stake": v.stake, "is_active": v.is_active,
             "eligible": v.is_active and v.stake > 0,
             "selection_weight": v.stake / total if v.is_active and v.stake > 0 else 0.0}
            for v in registry.validators.values()]


@app.get("/api/consensus/pos", response_model=PosConsensusResponse)
def api_pos_consensus(node_id: str):
    """Provisional backend prediction for the selected node's current tip."""
    with current_session().lock, ExitStack() as locks:
        network = get_network()
        node = network.nodes.get(node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại. Hãy chọn lại node."})
        # Registry has no lock. Match admission's sorted node lock order, also
        # excluding worker registry reads; queue broadcast takes no peer locks.
        # ponytail: lock all three demo nodes; add a registry lock if network size matters.
        for peer in sorted(network.nodes.values(), key=lambda n: n.node_id):
            locks.enter_context(peer._state_lock)
        registry = network.pos_registry
        validators = public_pos_validators(registry)
        height = len(node.blockchain.chain)
        previous_hash = node.blockchain.get_latest_block().compute_hash()
        predicted = registry.select_validator(height, network.consensus_seed, previous_hash)
        return {"node_id": node_id, "status": node.status,
                "validators": validators, "stake_mode": registry.stake_mode,
                "seed": network.consensus_seed,
                "predicted_validator": next((v for v in validators if predicted and v['address'] == predicted.address), None),
                "prediction_provisional": True, "target_height": height,
                "previous_hash": previous_hash,
                "reason": None if predicted else "Không tìm thấy validator hợp lệ trong mạng PoS",
                "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"]}


@app.post("/api/mining/pos", response_model=PosMiningResponse)
def api_forge_pos(body: PowMiningRequest):
    """Backend chooses, validates and broadcasts once; no client validator.

    seconds measures the entire forge_pos_pending call (including validation,
    local append and queue broadcast), excluding API lock acquisition/response.
    Public signer/stake metadata is captured in the same session as forging.
    """
    with current_session().lock, ExitStack() as locks:
        network = get_network()
        node = network.nodes.get(body.node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại. Hãy chọn lại node."})
        # ponytail: lock all demo nodes as above; no peer propagation waits here.
        for peer in sorted(network.nodes.values(), key=lambda n: n.node_id):
            locks.enter_context(peer._state_lock)
        started = time.perf_counter()
        try:
            block, result = node.forge_pos_pending()
        except Exception as exc:
            logging.getLogger(__name__).exception("PoS forging failed on %s", node.node_id)
            raise HTTPException(500, detail={"code": "mining_failed", "message": "Backend forging thất bại. Hãy làm mới mempool trước khi thử lại."}) from exc
        seconds = time.perf_counter() - started
        validators = public_pos_validators(network.pos_registry)
        return {"node_id": node.node_id, "forged": block is not None,
                "reason": result if block is None else None,
                "block": block.to_dict() if block else None,
                "transaction_ids": [tx.tx_id for tx in block.transactions] if block else [],
                "signer": next((v for v in validators if block and v['address'] == block.header.validator_address), None),
                "seconds": seconds, "elapsed_scope": "forge_pos_pending call",
                "context_generation": current_session().generation, "reset_count": get_session_info()["reset_count"]}


class ExplorerSnapshot(BaseModel):
    node_id: str
    status: str
    tip_height: int
    tip_hash: str | None
    local_chain_warning: str | None
    reset_count: int
    context_generation: str


class ExplorerBlocksResponse(ExplorerSnapshot):
    blocks: list[dict]


class ExplorerBlockResponse(ExplorerSnapshot):
    block: dict
    header: dict
    transactions: list[dict]
    validator: dict | None


def _explorer_snapshot(node_id, height=None):
    """Detached public data; lock order matches PoS API/worker registry access.

    Do not use get_session_info(): it seeds journey wallets on first access.
    Neither header serialization nor signature verification mutates the network.
    """
    with current_session().lock, ExitStack() as locks:
        network = get_network()
        node = network.nodes.get(node_id)
        if node is None:
            raise HTTPException(404, detail={"code": "node_not_found", "message": "Node không tồn tại. Hãy chọn lại node."})
        for peer in sorted(network.nodes.values(), key=lambda n: n.node_id):
            locks.enter_context(peer._state_lock)
        chain = node.blockchain.chain
        snapshot = {"node_id": node.node_id, "status": node.status, "tip_height": node.height,
                    "tip_hash": chain[-1].compute_hash() if chain else None,
                    "local_chain_warning": "Node OFFLINE: bản blockchain cục bộ có thể đã cũ." if node.status == "OFFLINE" else None,
                    "context_generation": current_session().generation, "reset_count": get_reset_count()}
        if height is None:
            snapshot['blocks'] = [block.to_dict() for block in reversed(chain)]
        else:
            block = next((b for b in chain if b.height == height), None)
            if block is None:
                raise HTTPException(404, detail={"code": "block_not_found", "message": "Block không tồn tại trong phiên hiện tại. Hãy làm mới."})
            validator = None
            if block.header.consensus_type == 'PoS':
                matched = network.pos_registry.validators.get(block.header.validator_address)
                if matched and verify_pos_signature(block, network.pos_registry)[0]:
                    validator = {"name": matched.name, "address": matched.address,
                                 "public_key_hex": matched.public_key_hex}
            snapshot.update({"block": block.to_dict(), "header": asdict(block.header),
                             "transactions": [deepcopy(tx.to_dict()) for tx in block.transactions],
                             "validator": validator})
    return snapshot


@app.get('/api/explorer/blocks', response_model=ExplorerBlocksResponse,
         summary="Read the selected guided-demo node's active chain, newest first")
def api_explorer_blocks(node_id: str = 'Node-1'):
    return _explorer_snapshot(node_id)


@app.get('/api/explorer/blocks/{height}', response_model=ExplorerBlockResponse,
         summary="Read one guided-demo block and its public serialized transactions")
def api_explorer_block(height: int, node_id: str = 'Node-1'):
    return _explorer_snapshot(node_id, height)


# Disposable lab keys never enter wallet_store or the shared Network. Expired
# handles are unusable and lazily removed on each key operation. One worker,
# at most 64 keys, 15 minutes each; process restart also discards them.
_LAB_KEY_TTL = 900
_LAB_KEY_LIMIT = 64


def _expire_lab_keys():
    """Caller holds only the lab lock; no session/node/registry lock is needed."""
    now = time.monotonic()
    for handle, (_, expires) in list(current_session().lab_keys.items()):
        if expires <= now:
            del current_session().lab_keys[handle]


class LabKeyResponse(BaseModel):
    key_handle: str
    public_key_hex: str
    address: str
    expires_in_seconds: int
    curve: Literal["secp256k1"] = "secp256k1"


class LabMessageRequest(BaseModel):
    model_config = {"extra": "forbid"}
    message: str = Field(max_length=10000)

    @field_validator("message")
    @classmethod
    def utf8_message(cls, value):
        value.encode("utf-8")  # Reject unpaired surrogates; preserve whitespace/empty text.
        return value


class LabSignRequest(LabMessageRequest):
    key_handle: str = Field(min_length=1, max_length=64)


class LabSignResponse(LabKeyResponse):
    message: str
    signature_hex: str


class LabVerifyRequest(LabMessageRequest):
    public_key_hex: str = Field(max_length=260)
    signature_hex: str = Field(max_length=1024)


class LabVerifyResponse(BaseModel):
    valid: bool


class LabMerkleRequest(BaseModel):
    model_config = {"extra": "forbid"}
    leaves: list[Annotated[str, Field(max_length=2000)]] = Field(max_length=16)
    proof_index: int | None = Field(default=None, ge=0)

    @field_validator("leaves")
    @classmethod
    def utf8_leaves(cls, values):
        for value in values:
            value.encode("utf-8")
        return values


class LabMerkleProof(BaseModel):
    index: int
    siblings: list[tuple[str, Literal["left", "right"]]]
    valid: bool


class LabMerkleResponse(BaseModel):
    leaf_hashes: list[str]
    levels: list[list[str]]
    root: str
    proof: LabMerkleProof | None


class LabConsensusRequest(BaseModel):
    model_config = {"extra": "forbid", "validate_default": True}
    mode: Literal["pow", "pos"]
    holder_name: str = "Người học DEMO-001"
    title: str = "Chứng chỉ Phân tích dữ liệu"
    issue_date: str = "2026-01-01"
    node_online: StrictBool = True
    include_sample: StrictBool = True

    @field_validator("holder_name", "title")
    @classmethod
    def required_text(cls, value, info):
        value.encode("utf-8")
        return CredentialCreateRequest.required_text(value, info)

    @field_validator("issue_date")
    @classmethod
    def valid_date(cls, value):
        return CredentialCreateRequest.valid_date(value)


class LabIssuer(BaseModel):
    name: str
    public_key_hex: str
    address: str


# One-block calculations are stateless: public candidates travel with the client.
# No wallet handle, Network, worker, session lock or registry is needed.
_BLOCK_LAB_MAX_ATTEMPTS = 200000
_BLOCK_LAB_MAX_SECONDS = 3.0
BlockLabHash = Annotated[str, Field(pattern=r'^[0-9a-fA-F]{64}$')]


class LabBlockFields(BaseModel):
    model_config = {"extra": "forbid", "validate_default": True}
    version: Annotated[StrictInt, Field(ge=1, le=2147483647)] = 1
    previous_hash: BlockLabHash = '0' * 64
    difficulty: Annotated[StrictInt, Field(ge=2, le=5)] = 2
    timestamp: str = Field(min_length=1, max_length=80)

    @field_validator('*', mode='before')
    @classmethod
    def utf8_text(cls, value):
        if isinstance(value, str):
            try:
                value.encode('utf-8')
            except UnicodeEncodeError as exc:
                raise HTTPException(422, detail='Dữ liệu lab Block cần văn bản UTF-8 hợp lệ.') from exc
        return value

    @field_validator('timestamp')
    @classmethod
    def valid_timestamp(cls, value):
        parsed = datetime.fromisoformat(value)
        if 'T' not in value or parsed.tzinfo is None:
            raise ValueError('Timestamp cần ISO-8601 có múi giờ, ví dụ 2026-10-04T12:00:00+07:00.')
        return value


class LabBlockBuildRequest(LabBlockFields):
    timestamp: str | None = None
    data: str = Field(max_length=4000)

    @field_validator('timestamp')
    @classmethod
    def valid_timestamp(cls, value):
        return LabBlockFields.valid_timestamp(value) if value is not None else None

class LabBlockHeader(LabBlockFields):
    merkle_root: BlockLabHash
    nonce: Annotated[StrictInt, Field(ge=0, le=9223372036854775807)]
    consensus_type: Literal['PoW'] = 'PoW'
    validator_address: Literal[''] = ''
    validator_signature: Literal[''] = ''


class LabBlockPayload(BaseModel):
    model_config = {"extra": "forbid"}
    credential_id: str = Field(min_length=1, max_length=200)
    lab_data: str = Field(max_length=4000)

    @field_validator('lab_data', mode='before')
    @classmethod
    def utf8_data(cls, value):
        return LabBlockFields.utf8_text(value)


class LabBlockTransaction(SignedTransactionResponse):
    model_config = {"extra": "forbid"}
    tx_id: BlockLabHash
    tx_type: Literal['ISSUE']
    sender_public_key: str = Field(min_length=1, max_length=260)
    payload: LabBlockPayload
    nonce: str = Field(min_length=1, max_length=200)
    timestamp: str = Field(min_length=1, max_length=80)
    signature: str = Field(min_length=1, max_length=1024)


class LabBlockCandidate(BaseModel):
    model_config = {"extra": "forbid"}
    header: LabBlockHeader
    transaction: LabBlockTransaction
    stored_hash: BlockLabHash


class LabBlockMineRequest(BaseModel):
    model_config = {"extra": "forbid"}
    candidate: LabBlockCandidate


class LabBlockEditRequest(LabBlockMineRequest):
    data: str = Field(max_length=4000)

    @field_validator('data', mode='before')
    @classmethod
    def utf8_data(cls, value):
        return LabBlockFields.utf8_text(value)


class LabBlockResponse(BaseModel):
    candidate: LabBlockCandidate
    stage: Literal['built', 'mined', 'incomplete', 'edited']
    computed_hash: str
    computed_transaction_hash: str
    validation: dict
    mining: dict | None
    original_data: str | None = None


def _restore_lab_block(candidate, height=1):
    data = candidate.transaction
    tx = Transaction(data.tx_type, data.sender_public_key, data.payload.model_dump(),
                     nonce=data.nonce, timestamp=data.timestamp)
    tx.tx_id, tx.signature = data.tx_id, data.signature
    header = candidate.header
    block = Block([tx], height, header.previous_hash, difficulty=header.difficulty,
                  nonce=header.nonce, timestamp=header.timestamp, version=header.version)
    block.header.merkle_root = header.merkle_root  # Preserve the supplied stored header for validation.
    return block


def _lab_block_validation(block, stored_hash):
    valid_tx, reason = verify_transaction(block.transactions[0])
    checks = {
        'transaction': {'valid': valid_tx, 'reason': reason},
        'merkle_root': {'valid': block.header.merkle_root == calculate_merkle_root([tx.tx_id for tx in block.transactions]),
                        'reason': 'Đối chiếu Merkle root với tx_id đã ghi.'},
        'stored_hash': {'valid': stored_hash == block.compute_hash(), 'reason': 'Đối chiếu hash đã ghi với hash header.'},
        'pow': {'valid': is_acceptable_pow(block), 'reason': 'Kiểm tra PoW bằng is_acceptable_pow().'},
    }
    return {'valid': all(check['valid'] for check in checks.values()), 'checks': checks}


def _lab_block_result(block, stage, stored_hash, mining=None, original_data=None):
    return {'candidate': {'header': asdict(block.header), 'transaction': block.transactions[0].to_dict(),
                          'stored_hash': stored_hash}, 'stage': stage,
            'computed_hash': block.compute_hash(), 'computed_transaction_hash': block.transactions[0].compute_hash(),
            'validation': _lab_block_validation(block, stored_hash), 'mining': mining,
            'original_data': original_data}


def _new_lab_data_block(data, height, previous_hash, difficulty, timestamp=None, version=1):
    # The ledger requires an ISSUE container and ID, not certificate metadata.
    # This payload is a teaching representation, never submitted to the guided Network.
    wallet = generate_wallet()
    tx = Transaction('ISSUE', wallet.public_key_hex,
                     {'credential_id': str(uuid.uuid4()), 'lab_data': data})
    tx.sign(wallet)
    return Block([tx], height, previous_hash, difficulty=difficulty,
                 timestamp=timestamp, version=version)


def _require_lab_block_integrity(block, candidate):
    checks = _lab_block_validation(block, candidate.stored_hash)['checks']
    for name, check in checks.items():
        if name != 'pow' and not check['valid']:
            raise HTTPException(422, detail=check['reason'])


@app.post('/api/labs/block/build', response_model=LabBlockResponse)
def lab_build_block(body: LabBlockBuildRequest):
    block = _new_lab_data_block(body.data, 1, body.previous_hash, body.difficulty,
                                body.timestamp, body.version)
    return _lab_block_result(block, 'built', block.compute_hash())


@app.post('/api/labs/block/mine', response_model=LabBlockResponse)
def lab_mine_block(body: LabBlockMineRequest):
    block = _restore_lab_block(body.candidate)
    _require_lab_block_integrity(block, body.candidate)
    if not current_session().block_mining_lock.acquire(blocking=False):
        raise HTTPException(429, detail='Lab Block đang đào một ứng viên. Hãy chờ rồi thử lại.')
    try:
        mining = _mine_lab_block_bounded(block)
        return _lab_block_result(block, 'mined' if mining['completed'] else 'incomplete',
                                 block.compute_hash(), mining)
    finally:
        current_session().block_mining_lock.release()


def _mine_lab_block_bounded(block):
    started, attempts = time.perf_counter(), 0
    original_nonce = block.header.nonce
    compute_hash = block.compute_hash

    def bounded_hash():
        nonlocal attempts
        if attempts >= _BLOCK_LAB_MAX_ATTEMPTS or time.perf_counter() - started >= _BLOCK_LAB_MAX_SECONDS:
            raise TimeoutError('Chưa hoàn tất: đã chạm giới hạn số lần băm hoặc thời gian của lab. Có thể tạo ứng viên mới để thử tiếp.')
        attempts += 1
        return compute_hash()

    try:
        # Instrument only this disposable instance; keep the existing nonce loop and SHA-256 implementation.
        block.compute_hash = bounded_hash
        try:
            mining = {**mine_block(block), 'completed': True, 'reason': None}
        except TimeoutError as exc:
            block.header.nonce = attempts - 1 if attempts else original_nonce
            mining = {'completed': False, 'reason': str(exc), 'attempts': attempts,
                      'seconds': time.perf_counter() - started}
        finally:
            del block.compute_hash
        mining.update({'max_attempts': _BLOCK_LAB_MAX_ATTEMPTS, 'max_seconds': _BLOCK_LAB_MAX_SECONDS,
                       'elapsed_scope': 'mine_block nonce search including the lab limit guard'})
        return mining
    except Exception as exc:
        logging.getLogger(__name__).exception('Standalone Block lab mining failed')
        raise HTTPException(500, detail='Backend đào block thất bại. Bạn có thể thử lại ứng viên hoặc tạo ứng viên mới.') from exc


@app.post('/api/labs/block/edit', response_model=LabBlockResponse)
def lab_edit_block(body: LabBlockEditRequest):
    block = _restore_lab_block(body.candidate)
    _require_lab_block_integrity(block, body.candidate)
    if not is_acceptable_pow(block):
        raise HTTPException(409, detail='Chỉ thử sửa dữ liệu sau khi ứng viên đã đạt PoW.')
    original = block.transactions[0].payload['lab_data']
    if body.data == original:
        raise HTTPException(422, detail='Dữ liệu mới phải khác dữ liệu đã ký.')
    block.transactions[0].payload['lab_data'] = body.data
    return _lab_block_result(block, 'edited', body.candidate.stored_hash, original_data=original)


# Public snapshots keep this experiment separate from Block and every Network.
# No retained handle, private key, expiry timer or worker exists to clean up.
_BLOCKCHAIN_LAB_MAX_BLOCKS = 12  # Excludes genesis.


class LabChainHeader(LabBlockHeader):
    difficulty: Annotated[StrictInt, Field(ge=1, le=5)]


class LabChainBlock(BaseModel):
    model_config = {"extra": "forbid"}
    height: Annotated[StrictInt, Field(ge=0, le=12)]
    header: LabChainHeader
    transaction: LabBlockTransaction | None
    stored_hash: BlockLabHash


class LabChainRequest(BaseModel):
    model_config = {"extra": "forbid"}
    chain: list[LabChainBlock] = Field(min_length=1, max_length=13)


class LabChainAddRequest(LabChainRequest):
    data: str = Field(max_length=4000)
    difficulty: Annotated[StrictInt, Field(ge=2, le=5)] = 2
    version: Annotated[StrictInt, Field(ge=1, le=2147483647)] = 1
    timestamp: str | None = Field(default=None, max_length=80)

    @field_validator('data', 'timestamp', mode='before')
    @classmethod
    def utf8_data(cls, value):
        return LabBlockFields.utf8_text(value)

    @field_validator('timestamp')
    @classmethod
    def valid_timestamp(cls, value):
        return LabBlockFields.valid_timestamp(value) if value is not None else None


class LabChainTargetRequest(LabChainRequest):
    height: Annotated[StrictInt, Field(ge=1, le=12)]


class LabChainEditRequest(LabChainTargetRequest):
    data: str = Field(max_length=4000)

    @field_validator('data', mode='before')
    @classmethod
    def utf8_data(cls, value):
        return LabBlockFields.utf8_text(value)


def _chain_lab_record(block, stored_hash=None):
    return {'height': block.height, 'header': asdict(block.header),
            'transaction': block.transactions[0].to_dict() if block.transactions else None,
            'stored_hash': stored_hash if stored_hash is not None else block.compute_hash()}


def _restore_chain_lab(records):
    chain = Blockchain()
    if records[0].model_dump() != _chain_lab_record(chain.chain[0]):
        raise HTTPException(422, detail='Genesis phải giữ nguyên theo backend.')
    for height, record in enumerate(records[1:], 1):
        if record.height != height or record.transaction is None or record.header.difficulty < 2:
            raise HTTPException(422, detail='Block cần đúng vị trí, giao dịch lab và độ khó 2–5.')
        chain.chain.append(_restore_lab_block(record, height))
    return chain


def _chain_lab_result(chain, records=None, mining=None, change=None, candidate=None):
    public = records or [_chain_lab_record(block) for block in chain.chain]
    valid, invalid_height, reason = chain.is_chain_valid()
    snapshots = []
    prefix = Blockchain()
    recorded_prefix = True
    for height, block in enumerate(chain.chain):
        record = public[height]
        if height:
            checks = _lab_block_validation(block, record['stored_hash'])
        else:
            checks = {'valid': True, 'checks': {}}
        link = height == 0 or block.header.previous_hash == chain.chain[height - 1].compute_hash()
        prefix.chain = chain.chain[:height + 1]
        prefix_valid, _, prefix_reason = prefix.is_chain_valid()
        recorded_prefix = recorded_prefix and record['stored_hash'] == block.compute_hash()
        snapshots.append({'height': height, 'computed_hash': block.compute_hash(),
                          'computed_transaction_hash': block.transactions[0].compute_hash() if height else None,
                          'own_validation': checks, 'link_valid': link,
                          'prefix_valid': prefix_valid and recorded_prefix,
                          'prefix_reason': prefix_reason if not prefix_valid else
                          'Hash đã ghi không khớp trong tiền tố.' if not recorded_prefix else prefix_reason})
    if valid and not recorded_prefix:
        valid, reason = False, 'Hash đã ghi không khớp trong chuỗi (kiểm tra bổ sung của lab).'
        invalid_height = next(s['height'] for s in snapshots if not s['prefix_valid'])
    return {'chain': public, 'blocks': snapshots, 'validation': {'valid': valid,
            'invalid_height': invalid_height, 'reason': reason}, 'mining': mining,
            'change': change, 'candidate': candidate, 'max_blocks': _BLOCKCHAIN_LAB_MAX_BLOCKS}


@app.post('/api/labs/blockchain/init')
def lab_init_blockchain():
    return _chain_lab_result(Blockchain())


@app.post('/api/labs/blockchain/validate')
def lab_validate_blockchain(body: LabChainRequest):
    return _chain_lab_result(_restore_chain_lab(body.chain), [r.model_dump() for r in body.chain])


@app.post('/api/labs/blockchain/add')
def lab_add_chain_block(body: LabChainAddRequest):
    chain = _restore_chain_lab(body.chain)
    records = [r.model_dump() for r in body.chain]
    result = _chain_lab_result(chain, records)
    if not result['validation']['valid']:
        raise HTTPException(409, detail=result['validation']['reason'])
    if len(chain.chain) - 1 >= _BLOCKCHAIN_LAB_MAX_BLOCKS:
        raise HTTPException(422, detail='Lab đã đạt giới hạn 12 block ngoài genesis. Đặt lại để thử chuỗi mới.')
    if not current_session().chain_mining_lock.acquire(blocking=False):
        raise HTTPException(429, detail='Lab Blockchain đang đào. Hãy chờ rồi thử lại.')
    try:
        block = _new_lab_data_block(body.data, len(chain.chain),
                                   chain.chain[-1].compute_hash(), body.difficulty,
                                   timestamp=body.timestamp, version=body.version)
        mining = _mine_lab_block_bounded(block)
        candidate = _chain_lab_record(block)
        if mining['completed']:
            chain.chain.append(block)
            records.append(candidate)
        return _chain_lab_result(chain, records, mining=mining, candidate=candidate)
    finally:
        current_session().chain_mining_lock.release()


def _chain_lab_target(body):
    chain = _restore_chain_lab(body.chain)
    if body.height >= len(chain.chain):
        raise HTTPException(404, detail='Không có block ở chiều cao đã chọn.')
    return chain, chain.chain[body.height], [r.model_dump() for r in body.chain]


@app.post('/api/labs/blockchain/edit')
def lab_edit_chain_block(body: LabChainEditRequest):
    chain, block, records = _chain_lab_target(body)
    original = deepcopy(records[body.height])
    if block.transactions[0].payload['lab_data'] == body.data:
        raise HTTPException(422, detail='Dữ liệu mới phải khác dữ liệu hiện tại.')
    block.transactions[0].payload['lab_data'] = body.data
    records[body.height] = _chain_lab_record(block, original['stored_hash'])
    return _chain_lab_result(chain, records, change={'height': body.height,
                             'action': 'edit', 'before': original, 'after': records[body.height]})


@app.post('/api/labs/blockchain/recompute')
def lab_recompute_chain_block(body: LabChainTargetRequest):
    chain, block, records = _chain_lab_target(body)
    original = deepcopy(records[body.height])
    tx = block.transactions[0]
    if tx.tx_id == tx.compute_hash():
        raise HTTPException(409, detail='Chưa có dữ liệu sửa cần tính lại dấu vân tay.')
    tx.tx_id = tx.compute_hash()  # Keep the old signature and nonce; do not repair subsequent links.
    block.header.merkle_root = calculate_merkle_root([tx.tx_id])
    records[body.height] = _chain_lab_record(block)
    return _chain_lab_result(chain, records, change={'height': body.height,
                             'action': 'recompute', 'before': original, 'after': records[body.height]})


class LabConsensusResponse(BaseModel):
    mode: Literal["pow", "pos"]
    node_id: str
    node_status: str
    created: bool
    stage: str
    reason: str | None
    submission: dict | None
    transaction: SignedTransactionResponse | None
    issuer: LabIssuer
    block: dict | None
    transaction_ids: list[str]
    seconds: float | None
    elapsed_scope: str
    backend_timing: dict | None
    attempts: int | None
    signer: PublicValidator | None
    validators: list[PublicValidator]
    stake_mode: str
    seed: int
    pending_count: int
    chain_valid: bool
    validity_reason: str


@app.post("/api/labs/consensus/run", response_model=LabConsensusResponse)
def lab_run_consensus(body: LabConsensusRequest):
    """One disposable Network per run; no shared stores/keys/session locks.

    Fresh single-node networks keep the exercise about consensus, not sync.
    The node lock excludes its worker while capturing registry/block metadata.
    Both modes measure the full Node call, excluding setup and worker teardown.
    Failures report the actual pending count before disposal, never clear it
    to hide rejection. No network or signing handle survives this request.
    """
    network = Network()
    try:
        node = network.create_node(f"Lab-{body.mode.upper()}", "127.0.0.1", 5001)
        with node._state_lock:
            wallet = generate_wallet()
            issuer = {"name": "Trường Đại học A", "public_key_hex": wallet.public_key_hex,
                      "address": wallet.address}
            if not body.node_online:
                node.go_offline()
            tx = None
            submission = None
            if body.include_sample:
                credential = Credential(str(uuid.uuid4()), issuer["name"], body.holder_name,
                                        body.title, body.issue_date)
                tx = Transaction("ISSUE", wallet.public_key_hex, credential.to_onchain_payload())
                tx.sign(wallet)
                accepted, reason = node.submit_transaction(tx)
                submission = {"accepted": accepted, "reason": reason}
            block, result, seconds = None, None, None
            stage = "submission" if submission and not submission["accepted"] else "creation"
            if stage == "submission":
                reason = submission["reason"]
            else:
                started = time.perf_counter()
                block, result = node.mine_pending() if body.mode == "pow" else node.forge_pos_pending()
                seconds = time.perf_counter() - started
                reason = result if block is None else None
            validators = public_pos_validators(network.pos_registry)
            valid, _, validity_reason = node.blockchain.is_chain_valid(pos_registry=network.pos_registry)
            return {"mode": body.mode, "node_id": node.node_id, "node_status": node.status,
                    "created": block is not None, "stage": "complete" if block else stage,
                    "reason": reason, "submission": submission,
                    "transaction": tx.to_dict() if tx else None, "issuer": issuer,
                    "block": block.to_dict() if block else None,
                    "transaction_ids": [t.tx_id for t in block.transactions] if block else [],
                    "seconds": seconds,
                    "elapsed_scope": "mine_pending call" if body.mode == "pow" else "forge_pos_pending call",
                    "backend_timing": result if block else None,
                    "attempts": result.get("attempts") if block and body.mode == "pow" else None,
                    "signer": next((v for v in validators if block and v["address"] == block.header.validator_address), None),
                    "validators": validators, "stake_mode": network.pos_registry.stake_mode,
                    "seed": network.consensus_seed,
                    "pending_count": len(node.mempool.get_transactions()),
                    "chain_valid": valid, "validity_reason": validity_reason}
    except Exception as exc:
        logging.getLogger(__name__).exception("Disposable consensus lab failed")
        raise HTTPException(500, detail="Backend tạo block lab thất bại. Mạng lab đã được dọn; thử một lượt mới.") from exc
    finally:
        # Release the node lock before join so its worker can finish.
        for node in network.nodes.values():
            node.stop()


# Unlike the single-call comparison, this lab needs state across actions.
class LabAttackRequest(BaseModel):
    """Fixed experiments, no client-supplied wallets, paths or networks."""
    model_config = {'extra': 'forbid'}
    scenario: Literal['tamper', 'impersonation', 'replay']
    edited_title: str = Field(default='Chứng chỉ đã bị sửa', min_length=1, max_length=200)

    @field_validator('edited_title')
    @classmethod
    def validate_title(cls, value):
        value = value.strip()
        if not value or value == 'Chứng chỉ mẫu lab':
            raise ValueError('Tiêu đề sửa phải không trống và khác tiêu đề mẫu.')
        return value


@app.post('/api/labs/attacks/run')
def lab_run_attack(body: LabAttackRequest):
    """One disposable node, two submissions, no mining or retained handles.

    The trusted issuer set is explicit. Each outcome comes from the existing
    verifier/admission; the hash gate precedes ECDSA in verify_transaction.
    Session middleware pins the request; workers are stopped before returning.
    """
    network = Network()
    try:
        issuer, attacker = generate_wallet(), generate_wallet()
        node = network.create_node('Attack-Node', '127.0.0.1', 5001,
                                   authorized_issuers={issuer.public_key_hex})
        credential = Credential(str(uuid.uuid4()), 'Đơn vị phát hành mẫu',
                                'Người học mẫu', 'Chứng chỉ mẫu lab', '2026-01-01')
        baseline = Transaction('ISSUE', issuer.public_key_hex, credential.to_onchain_payload())
        baseline.sign(issuer)

        def verification(tx):
            valid, reason = verify_transaction(tx)
            # All transactions here have the valid fixed type/payload/key and
            # a signature. Only the existing hash gate can skip ECDSA.
            return {'valid': valid, 'reason': reason,
                    'computed_hash': tx.compute_hash(),
                    'signature_checked': tx.tx_id == tx.compute_hash()}

        with node._state_lock:
            before = verification(baseline)
            accepted, reason = node.submit_transaction(baseline)
            if not before['valid'] or not accepted:
                raise HTTPException(409, detail=reason if not accepted else before['reason'])
            attack = deepcopy(baseline)
            if body.scenario == 'tamper':
                attack.payload['title'] = body.edited_title
            elif body.scenario == 'impersonation':
                payload = deepcopy(baseline.payload)
                payload['credential_id'] = str(uuid.uuid4())
                attack = Transaction('ISSUE', attacker.public_key_hex, payload)
                attack.sign(attacker)
            after = verification(attack)
            attack_accepted, attack_reason = node.submit_transaction(attack)
            layer = None
            if not attack_accepted:
                if not after['valid']:
                    layer = 'transaction_hash' if not after['signature_checked'] else 'signature'
                elif attack.sender_public_key not in node.mempool.authorized_issuers:
                    layer = 'issuer_authorization'
                elif attack.tx_id in {tx.tx_id for tx in node.mempool.get_transactions()}:
                    layer = 'duplicate_submission'
                else:
                    layer = 'admission'
            def public(wallet):
                return {'public_key_hex': wallet.public_key_hex, 'address': wallet.address}
            return {'scenario': body.scenario, 'context_generation': current_session().generation,
                    'node_id': node.node_id, 'authorized_issuer': public(issuer),
                    'attacker': public(attacker) if body.scenario == 'impersonation' else None,
                    'baseline': {'transaction': baseline.to_dict(), 'verification': before,
                                 'submission': {'accepted': accepted, 'reason': reason}},
                    'attack': {'transaction': attack.to_dict(), 'verification': after,
                               'submission': {'accepted': attack_accepted, 'reason': attack_reason}},
                    'failure_layer': layer, 'pending_count': len(node.mempool.get_transactions())}
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger(__name__).exception('Disposable attack lab failed')
        raise HTTPException(500, detail='Thí nghiệm backend thất bại. Mạng tạm đã được dọn; hãy thử lại.') from exc
    finally:
        for node in network.nodes.values():
            node.stop()


# Opaque handles, bounded lifetime/capacity and independent locks match lab keys.
_LAB_NETWORK_TTL = 900
_LAB_NETWORK_LIMIT = 8


def _close_lab_network(handle, kind=None):
    """Caller holds lab lock, no node lock; workers can finish before join."""
    entry = current_session().lab_networks.get(handle)
    if entry is None:
        return False
    if kind is not None and entry['kind'] != kind:
        raise HTTPException(404, detail="Handle không thuộc loại lab này.")
    del current_session().lab_networks[handle]
    entry['timer'].cancel()
    if hasattr(entry['network'], 'close'):
        entry['network'].close()
    else:
        for node in entry['network'].nodes.values():
            node.stop()
    return True


def _expire_lab_network(handle, context=None):
    # Timer threads receive the owning context; they never resolve a cookie.
    with bind_session(context or current_session()):
        with current_session().lab_network_lock:
            entry = current_session().lab_networks.get(handle)
            if entry and entry['expires'] <= time.monotonic():
                _close_lab_network(handle)


def close_lab_networks():
    """Close the bound context's network labs; app shutdown closes all contexts."""
    with current_session().lab_network_lock:
        for handle in list(current_session().lab_networks):
            _close_lab_network(handle)


def _get_lab_network(handle, kind='network'):
    entry = current_session().lab_networks.get(handle)
    if entry is not None and entry['kind'] != kind:
        raise HTTPException(404, detail="Handle không thuộc loại lab này.")
    _expire_lab_network(handle)
    entry = current_session().lab_networks.get(handle)
    if entry is None:
        raise HTTPException(404, detail="Mạng lab đã reset hoặc hết hạn. Khởi tạo lab mới.")
    return entry


class LabNetworkNodeSnapshot(NetworkNodeSnapshot):
    verification: dict | None
    local_chain_warning: str | None
    host: str | None = None
    port: int | None = None


class LabNetworkSnapshot(BaseModel):
    transport: Literal['queue', 'http'] = 'queue'
    context_generation: str
    lab_handle: str
    expires_in_seconds: int
    credential_id: str | None
    transaction: SignedTransactionResponse | None
    issuer: LabIssuer | None
    mining: dict | None
    nodes: list[LabNetworkNodeSnapshot]
    online_nodes_agree: bool
    online_nodes_valid: bool
    online_nodes_synchronized: bool
    all_nodes_synchronized: bool
    events: list[str]


def _lab_network_snapshot(handle, entry):
    """Lab lock coordinates reset/API; node locks coordinate queue workers.

    These are consistent per-node reads, not one globally atomic snapshot.
    Verification is ID-only on each actual chain; the stored TX is no proof.
    """
    network, tx = entry['network'], entry['tx']
    rows = []
    for node in network.nodes.values():
        if entry.get('transport') == 'http':
            from urllib.parse import urlencode
            rows.append(network.request(node.node_id, '/snapshot?' + urlencode(
                {'credential_id': tx.payload['credential_id']} if tx else {})))
            continue
        with node._state_lock:
            valid, invalid_height, reason = node.blockchain.is_chain_valid(
                pos_registry=network.pos_registry, authorized_issuers=node.mempool.authorized_issuers)
            verification = None
            if tx:
                checks, status, info = node.blockchain.verify_credential(
                    tx.payload['credential_id'], pos_registry=network.pos_registry,
                    authorized_issuers=node.mempool.authorized_issuers)
                verification = {'status': status, 'checks': checks, 'info': info,
                                'reason': info.get('reason') or next((c[2] for c in checks if not c[1]), status)}
            rows.append({'node_id': node.node_id, 'status': node.status,
                         'height': node.height, 'block_count': len(node.blockchain.chain),
                         'tip_hash': node.blockchain.get_latest_block().compute_hash(),
                         'pending_count': len(node.mempool.get_transactions()),
                         'chain_valid': valid, 'invalid_height': invalid_height, 'validity_reason': reason,
                         'verification': verification,
                         'local_chain_warning': 'Node OFFLINE đọc chuỗi cục bộ có thể cũ. NOT_FOUND không chứng minh hồ sơ vô hiệu.'
                         if node.status != 'ONLINE' else None})
    online = [row for row in rows if row['status'] == 'ONLINE']
    agree = bool(online) and len({(row['height'], row['tip_hash']) for row in online}) == 1
    valid = bool(online) and all(row['chain_valid'] for row in online)
    return {'lab_handle': handle, 'transport': entry.get('transport', 'queue'),
            'context_generation': current_session().generation,
            'expires_in_seconds': max(0, int(entry['expires'] - time.monotonic())),
            'credential_id': tx.payload['credential_id'] if tx else None,
            'transaction': tx.to_dict() if tx else None, 'issuer': entry['issuer'], 'mining': entry['mining'],
            'nodes': rows, 'online_nodes_agree': agree, 'online_nodes_valid': valid,
            'online_nodes_synchronized': agree and valid,
            'all_nodes_synchronized': len(online) == 3 and agree and valid,
            'events': network.get_event_log()}


def _initialize_lab_network(kind, transport='queue'):
    """Caller holds this context's lab lock. Both retained labs reuse this lifecycle."""
    for handle in list(current_session().lab_networks):
        _expire_lab_network(handle)
    if len(current_session().lab_networks) >= _LAB_NETWORK_LIMIT:
        raise HTTPException(429, detail="Đã đủ mạng lab tạm. Reset lab không dùng hoặc chờ hết hạn.")
    if transport == 'http' and any(e.get('transport') == 'http' for e in current_session().lab_networks.values()):
        raise HTTPException(429, detail='Phiên này đã có một mạng HTTP. Đặt lại mạng đó trước khi mở mạng mới.')
    network = HttpLabNetwork(_mine_lab_block_bounded) if transport == 'http' else Network()
    handle = str(uuid.uuid4())
    timer = threading.Timer(_LAB_NETWORK_TTL, _expire_lab_network, args=(handle, current_session()))
    timer.daemon = True
    entry = {'kind': kind, 'transport': transport, 'network': network, 'tx': None, 'issuer': None, 'submitted': False,
             'mining': None, 'expires': time.monotonic() + _LAB_NETWORK_TTL, 'timer': timer}
    try:
        if transport == 'queue':
            for i in range(1, 4):
                network.create_node(f'Node-{i}', '127.0.0.1', 5000 + i)
        current_session().lab_networks[handle] = entry
        timer.start()
        return handle, entry
    except Exception as exc:
        timer.cancel()
        current_session().lab_networks.pop(handle, None)
        if hasattr(network, 'close'):
            network.close()
        else:
            for node in network.nodes.values():
                node.stop()
        raise HTTPException(500, detail="Không khởi tạo được mạng lab; worker tạm đã được dọn.") from exc


class LabNetworkRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    transport: Literal['queue', 'http'] = 'queue'


@app.post('/api/labs/network', status_code=201, response_model=LabNetworkSnapshot)
def lab_initialize_network(body: LabNetworkRequest | None = Body(default=None)):
    # ponytail: serialize at most eight lab sessions; per-handle locks if throughput matters.
    with current_session().lab_network_lock:
        handle, entry = _initialize_lab_network('network', body.transport if body else 'queue')
        try:
            return _lab_network_snapshot(handle, entry)
        except Exception:
            _close_lab_network(handle)
            raise


@app.get('/api/labs/network/{handle}', response_model=LabNetworkSnapshot)
def lab_read_network(handle: str):
    with current_session().lab_network_lock:
        return _lab_network_snapshot(handle, _get_lab_network(handle))


@app.post('/api/labs/network/{handle}/reset')
def lab_reset_network(handle: str):
    with current_session().lab_network_lock:
        return {'cleared': _close_lab_network(handle, 'network')}


@app.post('/api/labs/network/{handle}/nodes/{node_id}/status')
def lab_node_status(handle: str, node_id: str, body: NodeStatusRequest):
    with current_session().lab_network_lock:
        entry = _get_lab_network(handle)
        if node_id != 'Node-3':
            raise HTTPException(404, detail="Lab này chỉ điều khiển trạng thái Node-3.")
        if entry.get('transport') == 'http':
            result = entry['network'].request(node_id, '/status', {'online': body.online})
            return {'changed': result['changed'], 'catch_up_requested': False,
                    'snapshot': _lab_network_snapshot(handle, entry)}
        node = entry['network'].nodes[node_id]
        with node._state_lock:
            changed = (node.status == 'ONLINE') != body.online
            if changed:
                node.go_online() if body.online else node.go_offline()
        return {'changed': changed, 'catch_up_requested': changed and body.online,
                'snapshot': _lab_network_snapshot(handle, entry)}


def _mine_lab_sample(entry):
    """Same sample signing/admission/mining for both retained lab scenarios."""
    node = entry['network'].nodes['Node-1']
    if entry['tx'] is None:
        wallet = generate_wallet()
        entry['issuer'] = {'name': 'Trường Đại học A', 'public_key_hex': wallet.public_key_hex,
                           'address': wallet.address}
        credential = Credential(str(uuid.uuid4()), entry['issuer']['name'], 'Người học DEMO-001',
                                'Chứng chỉ Phân tích dữ liệu', '2026-01-01')
        tx = Transaction('ISSUE', wallet.public_key_hex, credential.to_onchain_payload())
        tx.sign(wallet)
        entry['tx'] = tx
    if entry.get('transport') == 'http':
        network = entry['network']
        if not entry['submitted']:
            result = network.request('Node-1', '/submit_tx', entry['tx'].to_dict())
            if not result['ok']:
                return None, result['reason']
            entry['submitted'] = True
        result = network.request('Node-1', '/mine', {'difficulty': 3, 'max_txs': 10})
        if not result['ok']:
            return None, result['reason']
        block = block_from_json(result['block'])
        result = {k: result[k] for k in ('nonce', 'attempts', 'seconds', 'block_hash')}
        entry['mining'] = {'block': block.to_dict(), **result}
        return block, result
    with node._state_lock:
        if not entry['submitted']:
            accepted, reason = node.submit_transaction(entry['tx'])
            if not accepted:
                return None, reason
            entry['submitted'] = True
        try:
            block, result = node.mine_pending()
        except Exception as exc:
            logging.getLogger(__name__).exception('Network lab mining failed')
            raise HTTPException(500, detail="Backend mining lab thất bại; giao dịch vẫn chờ. Làm mới hoặc reset riêng lab.") from exc
        if block:
            entry['mining'] = {'block': block.to_dict(), **result}
        return block, result


@app.post('/api/labs/network/{handle}/mine')
def lab_network_mine(handle: str):
    with current_session().lab_network_lock:
        entry = _get_lab_network(handle)
        if entry['mining'] is not None:
            raise HTTPException(409, detail="Lab đã tạo block mẫu. Reset riêng lab để thử lại từ đầu.")
        block, result = _mine_lab_sample(entry)
        # Release Node-1 before reading other worker locks.
        return {'mined': block is not None, 'reason': result if block is None else None,
                'block': block.to_dict() if block else None, 'snapshot': _lab_network_snapshot(handle, entry)}


@app.post('/api/labs/network/{handle}/sync')
def lab_sync_network(handle: str):
    with current_session().lab_network_lock:
        entry = _get_lab_network(handle)
        try:
            sync_results = entry['network'].sync_all_nodes(online_only=True)
        except Exception as exc:
            logging.getLogger(__name__).exception('Network lab synchronization failed')
            raise HTTPException(500, detail="Backend sync lab thất bại. Làm mới trạng thái trước khi thử lại.") from exc
        snapshot = _lab_network_snapshot(handle, entry)
        invalid = next((n for n in snapshot['nodes'] if n['status'] == 'ONLINE' and not n['chain_valid']), None)
        reason = None if snapshot['all_nodes_synchronized'] else (
            invalid['validity_reason'] if invalid else 'Adapter: chưa quan sát đủ ba node ONLINE cùng height/tip; node OFFLINE không được sync.')
        response = {'completed': snapshot['all_nodes_synchronized'], 'reason': reason, 'snapshot': snapshot}
        if entry.get('transport') == 'http':
            response['node_results'] = sync_results
        return response


class LabTamperEditRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    title: str

    @field_validator('title')
    @classmethod
    def required_title(cls, value, info):
        value.encode('utf-8')
        return CredentialCreateRequest.required_text(value, info)


class LabTamperNodeSnapshot(LabNetworkNodeSnapshot):
    stored_tip_hash: str
    local_title: str | None


class LabTamperSnapshot(LabNetworkSnapshot):
    lab_id: str
    original_title: str | None
    edited_title: str | None
    prepared: bool
    ready: bool
    tampered: bool
    restored: bool
    reason: str | None
    nodes: list[LabTamperNodeSnapshot]


def _tamper_lab_snapshot(handle, entry):
    data = _lab_network_snapshot(handle, entry)
    original_title = entry['tx'].payload['title'] if entry['tx'] else None
    for row in data['nodes']:
        # Block has no cached hash attribute: this is its unchanged header hash.
        row['stored_tip_hash'] = row['tip_hash']
        row['local_title'] = row['verification']['info'].get('title') if row['verification'] else None
    ready = bool(entry['mining']) and data['all_nodes_synchronized'] and all(
        row['height'] >= 1 and row['verification']['status'] == 'VERIFIED'
        and row['local_title'] == original_title for row in data['nodes'])
    node2 = next(row for row in data['nodes'] if row['node_id'] == 'Node-2')
    invalid = next((row for row in data['nodes'] if not row['chain_valid']), None)
    unverified = next((row for row in data['nodes'] if row['verification'] and row['verification']['status'] != 'VERIFIED'), None)
    data.update({'lab_id': handle, 'original_title': original_title,
                 'edited_title': entry.get('edited_title'), 'prepared': entry['mining'] is not None,
                 'ready': ready,
                 'tampered': node2['local_title'] is not None and node2['local_title'] != original_title,
                 'restored': ready and entry.get('edited_title') is not None,
                 'reason': None if ready else (entry.get('prepare_failure') or
                     (invalid['validity_reason'] if invalid else unverified['verification']['reason'] if unverified
                      else 'Adapter: chưa quan sát đủ ba node ONLINE cùng tip, chuỗi hợp lệ và VERIFIED.'))})
    return data


@app.post('/api/labs/tamper', status_code=201, response_model=LabTamperSnapshot)
def lab_prepare_tamper():
    with current_session().lab_network_lock:
        handle, entry = _initialize_lab_network('tamper')
        try:
            block, reason = _mine_lab_sample(entry)
            entry['prepare_failure'] = reason if block is None else None
            return _tamper_lab_snapshot(handle, entry)
        except Exception:
            # No handle was returned; prevent an unreachable network leaking workers.
            _close_lab_network(handle)
            raise


@app.get('/api/labs/tamper/{lab_id}', response_model=LabTamperSnapshot)
def lab_observe_tamper(lab_id: str):
    with current_session().lab_network_lock:
        return _tamper_lab_snapshot(lab_id, _get_lab_network(lab_id, 'tamper'))


@app.post('/api/labs/tamper/{lab_id}/edit', response_model=LabTamperSnapshot)
def lab_edit_tamper(lab_id: str, body: LabTamperEditRequest):
    with current_session().lab_network_lock, ExitStack() as locks:
        entry = _get_lab_network(lab_id, 'tamper')
        # Same sorted lock order as sync; workers hold only their own node lock.
        for peer in sorted(entry['network'].nodes.values(), key=lambda n:n.node_id):
            locks.enter_context(peer._state_lock)
        if not _tamper_lab_snapshot(lab_id, entry)['ready']:
            raise HTTPException(409, detail="Chờ ba node VERIFIED và hợp lệ, hoặc đồng bộ để phục hồi trước khi sửa tiếp.")
        node = entry['network'].nodes['Node-2']
        target = node.blockchain.chain[1]
        if target.height != 1 or len(target.transactions) != 1 or target.transactions[0].tx_type != 'ISSUE':
            raise HTTPException(409, detail="Không có ISSUE mẫu tại Block #1 của Node-2.")
        tx = target.transactions[0]
        if tx.tx_id != entry['tx'].tx_id or tx.payload.get('credential_id') != entry['tx'].payload['credential_id']:
            raise HTTPException(409, detail="Giao dịch tại đích không khớp ISSUE mẫu của lab.")
        if body.title == tx.payload['title']:
            raise HTTPException(422, detail="Tiêu đề chưa thay đổi. Hãy sửa bản cục bộ của Node-2.")
        # Copy the local graph (chain + block_pool aliases); never mutate peer objects.
        local_chain = deepcopy(node.blockchain)
        local_chain.chain[1].transactions[0].payload['title'] = body.title
        node.blockchain = local_chain
        entry['edited_title'] = body.title
        # No sign/hash assignment, mining, broadcast, or automatic repair.
        return _tamper_lab_snapshot(lab_id, entry)


@app.post('/api/labs/tamper/{lab_id}/sync', response_model=LabTamperSnapshot)
def lab_recover_tamper(lab_id: str):
    with current_session().lab_network_lock:
        entry = _get_lab_network(lab_id, 'tamper')
        if entry.get('edited_title') is None:
            raise HTTPException(409, detail="Lab chưa sửa dữ liệu. Hãy quan sát bản gốc rồi sửa Node-2 trước.")
        try:
            entry['network'].sync_all_nodes(online_only=True)
        except Exception as exc:
            logging.getLogger(__name__).exception('Tamper lab synchronization failed')
            raise HTTPException(500, detail="Backend sync lab thất bại. Dữ liệu chưa được xác nhận phục hồi.") from exc
        return _tamper_lab_snapshot(lab_id, entry)


@app.delete('/api/labs/tamper/{lab_id}')
def lab_close_tamper(lab_id: str):
    with current_session().lab_network_lock:
        return {'cleared': _close_lab_network(lab_id, 'tamper')}


@app.post("/api/labs/signatures/keys", status_code=201, response_model=LabKeyResponse)
def lab_create_key():
    """Generate disposable secp256k1 keys; private keys stay in this process."""
    with current_session().lab_key_lock:
        _expire_lab_keys()
        if len(current_session().lab_keys) >= _LAB_KEY_LIMIT:
            raise HTTPException(429, detail="Lab đã đủ khóa tạm. Reset khóa không dùng hoặc chờ hết hạn.")
        wallet = generate_wallet()
        handle = str(uuid.uuid4())
        current_session().lab_keys[handle] = (wallet, time.monotonic() + _LAB_KEY_TTL)
        return {"key_handle": handle, "public_key_hex": wallet.public_key_hex,
                "address": wallet.address, "expires_in_seconds": _LAB_KEY_TTL}


@app.post("/api/labs/signatures/keys/{key_handle}/reset")
def lab_reset_key(key_handle: str):
    """Idempotently delete this key only; never reset journey/session state."""
    with current_session().lab_key_lock:
        _expire_lab_keys()
        return {"cleared": current_session().lab_keys.pop(key_handle, None) is not None}


@app.post("/api/labs/signatures/sign", response_model=LabSignResponse)
def lab_sign(body: LabSignRequest):
    """Existing Wallet signing: ECDSA(SHA-256(UTF-8 message)), DER signature hex."""
    with current_session().lab_key_lock:
        _expire_lab_keys()
        entry = current_session().lab_keys.get(body.key_handle)
        if entry is None:
            raise HTTPException(404, detail="Khóa lab không tồn tại hoặc đã hết hạn. Tạo khóa tạm mới.")
        wallet, expires = entry
        return {"key_handle": body.key_handle, "public_key_hex": wallet.public_key_hex,
                "address": wallet.address, "message": body.message,
                "signature_hex": sign_message(body.message, wallet.private_key_pem),
                "expires_in_seconds": max(0, int(expires - time.monotonic()))}


@app.post("/api/labs/signatures/verify", response_model=LabVerifyResponse)
def lab_verify_signature(body: LabVerifyRequest):
    """Verification needs only public data, even after deleting the lab key."""
    return {"valid": verify_signature(body.message, body.signature_hex, body.public_key_hex)}


@app.post("/api/labs/merkle", response_model=LabMerkleResponse)
def lab_merkle(body: LabMerkleRequest):
    """Text leaves use SHA-256 UTF-8; parents hash concatenated hex strings.

    Existing tree code duplicates odd final hashes. Empty tree root is
    SHA-256(""). This is an unsalted text exercise, not a claims tree or block.
    Proofs reuse the same existing tree implementation, solely for this lab.
    """
    if body.proof_index is not None and body.proof_index >= len(body.leaves):
        raise HTTPException(422, detail="Chỉ số proof phải trỏ đến một lá có thật.")
    hashes = [sha256_hex(value) for value in body.leaves]
    levels = build_merkle_tree(hashes)
    root = levels[-1][0]
    proof = None
    if body.proof_index is not None:
        siblings = generate_merkle_proof(hashes, body.proof_index)
        proof = {"index": body.proof_index, "siblings": siblings,
                 "valid": verify_merkle_proof(hashes[body.proof_index], siblings, root)}
    return {"leaf_hashes": hashes, "levels": levels, "root": root, "proof": proof}


if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR)), name="ui")


@app.get("/landing.html", include_in_schema=False)
def landing():
    """Serve only the intended landing file; never mount the repository root."""
    return FileResponse(_BASE_DIR / "landing.html")


@app.get("/", include_in_schema=False)
def root():
    """Start at the landing page; mode choice links to the integrated frontend."""
    return RedirectResponse(url="/landing.html")
