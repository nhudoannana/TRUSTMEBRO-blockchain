"""api/wallet_store.py — In-memory wallet store for TRUSTMEBRO Phase 1.

Scope and assumptions:
- Wallets persist only for the duration of the server process.
- Server restart clears all wallets (no file persistence yet).
- Thread-safe via threading.Lock.
- Private keys are held server-side only; never exposed via API responses.
- Demo issuer wallets are pre-seeded on first access (clearly labeled as demo data).

Limitations (known, not hidden):
- In-memory only; restart loses data.
- No user auth; the cookie scopes a temporary simulation, not a login.
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


class WalletStore:
    """Private/public wallet state belonging to one browser simulation."""
    def __init__(self):
        self._lock = threading.Lock()
        self._store = {}
        self._seeded = False

    def _seed_demo_wallets(self) -> None:
        """Pre-seed two demo issuer wallets.

        These are labeled 'demo' in source field. Keys are generated fresh each
        session initialization/reset, so they are not real institutional keys.
        Called once under self._lock the first time the store is accessed.
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
            self._store[entry.id] = entry


    def _ensure_seeded(self) -> None:
        with self._lock:
            if not self._seeded:
                self._seed_demo_wallets()
                self._seeded = True


    def reset_wallets(self) -> None:
        """Clear all wallets and allow fresh demo keys on next access."""
        with self._lock:
            self._store.clear()
            self._seeded = False


    def list_wallets(self) -> list[dict]:
        """Return all wallets as safe public dicts (no private key)."""
        self._ensure_seeded()
        with self._lock:
            return [_public(e) for e in self._store.values()]


    def get_wallet(self, wallet_id: str) -> Optional[dict]:
        """Return one wallet by ID (no private key), or None if not found."""
        self._ensure_seeded()
        with self._lock:
            entry = self._store.get(wallet_id)
            return _public(entry) if entry else None


    def create_wallet(self, name: str) -> dict:
        """Generate a real ECDSA wallet and store it.

        Returns the public representation (no private key).
        Raises ValueError if name is empty.
        """
        name = name.strip()
        if not name:
            raise ValueError("Tên ví không được để trống.")
        if len(name) > 80:
            raise ValueError("Tên ví không được vượt quá 80 ký tự.")

        self._ensure_seeded()

        w: Wallet = generate_wallet()
        entry = WalletEntry(
            id=f"WALLET-{str(uuid.uuid4())[:8].upper()}",
            name=name,
            public_key_hex=w.public_key_hex,
            address=w.address,
            source="user",
            _private_key_pem=w.private_key_pem,
        )
        with self._lock:
            self._store[entry.id] = entry

        return _public(entry)


    def get_private_key_pem(self, wallet_id: str) -> Optional[str]:
        """Internal use only — retrieve private key for signing.

        Call under the owning session lock; never include this value in an API response.
        """
        with self._lock:
            entry = self._store.get(wallet_id)
            return entry._private_key_pem if entry else None



def _wallets():
    from api.session_store import current_session
    return current_session().wallets


def reset_wallets():
    return _wallets().reset_wallets()


def list_wallets():
    return _wallets().list_wallets()


def get_wallet(wallet_id):
    return _wallets().get_wallet(wallet_id)


def create_wallet(name):
    return _wallets().create_wallet(name)


def get_private_key_pem(wallet_id):
    return _wallets().get_private_key_pem(wallet_id)


def _public(entry: WalletEntry) -> dict:
    """Convert WalletEntry to a safe public dict, excluding private key."""
    return {
        "id": entry.id,
        "name": entry.name,
        "public_key_hex": entry.public_key_hex,
        "address": entry.address,
        "source": entry.source,
    }
