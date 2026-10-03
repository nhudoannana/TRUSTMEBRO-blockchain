"""api/wallet_store.py — In-memory wallet store for TRUSTMEBRO Phase 1.

Scope and assumptions:
- Wallets persist only for the duration of the server process.
- Server restart clears all wallets (no file persistence yet).
- Thread-safe via threading.Lock.
- Private keys are held server-side only; never exposed via API responses.
- Demo issuer wallets are pre-seeded on first access (clearly labeled as demo data).

Limitations (known, not hidden):
- In-memory only; restart loses data.
- No user auth; any API client can list/create wallets.
"""

import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from blockchain.wallet import Wallet, generate_wallet


@dataclass
class WalletEntry:
    """A wallet entry stored server-side.

    private_key_pem is NEVER sent in API responses.
    """
    id: str
    name: str
    public_key_hex: str
    address: str
    source: str          # "demo" | "user"
    _private_key_pem: str = field(repr=False)  # underscore = intentionally not serialized


_lock = threading.Lock()
_store: dict[str, WalletEntry] = {}
_seeded = False


def _seed_demo_wallets() -> None:
    """Pre-seed two demo issuer wallets.

    These are labeled 'demo' in source field. Keys are generated fresh each
    process start, so they are not real institutional keys.
    Called once under _lock the first time the store is accessed.
    """
    for name in ["Trường Đại học A", "Trung tâm Đào tạo B"]:
        w: Wallet = generate_wallet()
        entry = WalletEntry(
            id=f"WALLET-DEMO-{str(uuid.uuid4())[:8].upper()}",
            name=name,
            public_key_hex=w.public_key_hex,
            address=w.address,
            source="demo",
            _private_key_pem=w.private_key_pem,
        )
        _store[entry.id] = entry


def _ensure_seeded() -> None:
    global _seeded
    with _lock:
        if not _seeded:
            _seed_demo_wallets()
            _seeded = True


def reset_wallets() -> None:
    """Clear all wallets and allow fresh demo keys on next access."""
    global _seeded
    with _lock:
        _store.clear()
        _seeded = False


def list_wallets() -> list[dict]:
    """Return all wallets as safe public dicts (no private key)."""
    _ensure_seeded()
    with _lock:
        return [_public(e) for e in _store.values()]


def get_wallet(wallet_id: str) -> Optional[dict]:
    """Return one wallet by ID (no private key), or None if not found."""
    _ensure_seeded()
    with _lock:
        entry = _store.get(wallet_id)
        return _public(entry) if entry else None


def create_wallet(name: str) -> dict:
    """Generate a real ECDSA wallet and store it.

    Returns the public representation (no private key).
    Raises ValueError if name is empty.
    """
    name = name.strip()
    if not name:
        raise ValueError("Tên ví không được để trống.")
    if len(name) > 80:
        raise ValueError("Tên ví không được vượt quá 80 ký tự.")

    _ensure_seeded()

    w: Wallet = generate_wallet()
    entry = WalletEntry(
        id=f"WALLET-{str(uuid.uuid4())[:8].upper()}",
        name=name,
        public_key_hex=w.public_key_hex,
        address=w.address,
        source="user",
        _private_key_pem=w.private_key_pem,
    )
    with _lock:
        _store[entry.id] = entry

    return _public(entry)


def get_private_key_pem(wallet_id: str) -> Optional[str]:
    """Internal use only — retrieve private key for signing.

    Call under session_lock; never include this value in an API response.
    """
    with _lock:
        entry = _store.get(wallet_id)
        return entry._private_key_pem if entry else None


def _public(entry: WalletEntry) -> dict:
    """Convert WalletEntry to a safe public dict, excluding private key."""
    return {
        "id": entry.id,
        "name": entry.name,
        "public_key_hex": entry.public_key_hex,
        "address": entry.address,
        "source": entry.source,
    }
