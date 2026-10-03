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
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, field_validator
from api.network_store import session_lock, get_session_info, reset_network
from api.network_store import signed_credentials
from api.network_store import get_network, submit_signed_transaction, get_mempool_snapshots
from api.network_store import get_network_snapshots
from blockchain.wallet import Wallet
from blockchain.wallet import generate_wallet, sign_message, verify_signature
from blockchain.hash import sha256_hex
from blockchain.merkle import build_merkle_tree, generate_merkle_proof, verify_merkle_proof
from blockchain.transaction import Credential, Transaction

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
app = FastAPI(
    title="TRUSTMEBRO API — Phase 1",
    description="Wallet management for the blockchain education simulation.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

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


class NodeMempoolSnapshot(BaseModel):
    node_id: str
    status: str
    pending_count: int
    transactions: list[dict]


class MempoolSnapshotsResponse(BaseModel):
    nodes: list[NodeMempoolSnapshot]
    reset_count: int


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
    with session_lock:
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
                    "reset_count": get_session_info()["reset_count"]}


@app.post("/api/credentials/{credential_id}/revoke", response_model=RevokeResponse, summary="Sign and submit REVOKE; never mine")
def api_revoke(credential_id: str, body: RevokeRequest):
    """Resolve original issuer by public key, never organization name.

    Valid local on-chain evidence is required. Reuse D's admission lock and
    backend reasons; acceptance only means pending until explicitly mined.
    """
    if not credential_id.strip() or len(credential_id) > 200:
        raise HTTPException(422, detail="credential_id cần 1–200 ký tự.")
    with session_lock:
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
                "transaction": tx.to_dict(), "reset_count": get_session_info()["reset_count"]}


# ── API routes ──────────────────────────────────────────────────────────────

@app.get("/api/wallets", response_model=list[WalletResponse], summary="List wallets")
def api_list_wallets():
    """Return all wallets. Private keys are never included."""
    with session_lock:
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
        with session_lock:
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
    with session_lock:
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
    Store credential and signed transaction until shared reset/server restart.
    No submission, broadcasting or mining occurs here.
    """
    with session_lock:
        stored = get_wallet(body.issuer_wallet_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Ví không tồn tại. Hãy chọn lại ví ở bước 1.")
        wallet = Wallet(get_private_key_pem(stored["id"]), stored["public_key_hex"], stored["address"])
        credential = Credential(str(uuid.uuid4()), stored["name"], body.holder_name,
                                body.title, body.issue_date)
        tx = Transaction("ISSUE", wallet.public_key_hex, credential.to_onchain_payload())
        tx.sign(wallet)
        signed_credentials[credential.credential_id] = (credential, tx)
        return {
            "credential_id": tx.payload["credential_id"],
            "credential": tx.payload,
            "issuer_wallet_id": stored["id"],
            "issuer_address": wallet.address,
            "transaction": tx.to_dict(),
        }

@app.get("/api/session", summary="Shared demo session")
def api_session():
    return get_session_info()


@app.post("/api/mempool", response_model=MempoolSubmitResponse, summary="Submit stored signed credential")
def api_submit_mempool(body: MempoolSubmitRequest):
    """200 includes accepted/rejected result; backend reason is verbatim.

    404 detail.code identifies credential_not_found or node_not_found.
    No replacement payload, signing, extra broadcast or mining.
    """
    with session_lock:
        stored = signed_credentials.get(body.credential_id)
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
                "reason_source": source, "reset_count": get_session_info()["reset_count"]}


@app.get("/api/mempool", response_model=MempoolSnapshotsResponse, summary="Real per-node mempool snapshots")
def api_get_mempool():
    """Nodes may differ while queue workers propagate a transaction."""
    return get_mempool_snapshots()


@app.post("/api/session/reset", summary="Reset shared demo session")
def api_reset_session():
    with session_lock:
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
    with session_lock:
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
    with session_lock:
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
    with session_lock:
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
                "reset_count": get_session_info()["reset_count"],
            }


def public_pos_validators(registry):
    """Explicit public projection; caller holds session and node locks.

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
    with session_lock, ExitStack() as locks:
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
                "reset_count": get_session_info()["reset_count"]}


@app.post("/api/mining/pos", response_model=PosMiningResponse)
def api_forge_pos(body: PowMiningRequest):
    """Backend chooses, validates and broadcasts once; no client validator.

    seconds measures the entire forge_pos_pending call (including validation,
    local append and queue broadcast), excluding API lock acquisition/response.
    Public signer/stake metadata is captured in the same session as forging.
    """
    with session_lock, ExitStack() as locks:
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
                "reset_count": get_session_info()["reset_count"]}


# Disposable lab keys never enter wallet_store or the shared Network. Expired
# handles are unusable and lazily removed on each key operation. One worker,
# at most 64 keys, 15 minutes each; process restart also discards them.
_LAB_KEY_TTL = 900
_LAB_KEY_LIMIT = 64
_lab_keys: dict[str, tuple[Wallet, float]] = {}
_lab_key_lock = threading.RLock()


def _expire_lab_keys():
    """Caller holds only the lab lock; no session/node/registry lock is needed."""
    now = time.monotonic()
    for handle, (_, expires) in list(_lab_keys.items()):
        if expires <= now:
            del _lab_keys[handle]


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


@app.post("/api/labs/signatures/keys", status_code=201, response_model=LabKeyResponse)
def lab_create_key():
    """Generate disposable secp256k1 keys; private keys stay in this process."""
    with _lab_key_lock:
        _expire_lab_keys()
        if len(_lab_keys) >= _LAB_KEY_LIMIT:
            raise HTTPException(429, detail="Lab đã đủ khóa tạm. Reset khóa không dùng hoặc chờ hết hạn.")
        wallet = generate_wallet()
        handle = str(uuid.uuid4())
        _lab_keys[handle] = (wallet, time.monotonic() + _LAB_KEY_TTL)
        return {"key_handle": handle, "public_key_hex": wallet.public_key_hex,
                "address": wallet.address, "expires_in_seconds": _LAB_KEY_TTL}


@app.post("/api/labs/signatures/keys/{key_handle}/reset")
def lab_reset_key(key_handle: str):
    """Idempotently delete this key only; never reset journey/session state."""
    with _lab_key_lock:
        _expire_lab_keys()
        return {"cleared": _lab_keys.pop(key_handle, None) is not None}


@app.post("/api/labs/signatures/sign", response_model=LabSignResponse)
def lab_sign(body: LabSignRequest):
    """Existing Wallet signing: ECDSA(SHA-256(UTF-8 message)), DER signature hex."""
    with _lab_key_lock:
        _expire_lab_keys()
        entry = _lab_keys.get(body.key_handle)
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
