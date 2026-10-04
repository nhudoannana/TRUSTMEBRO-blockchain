"""tests/test_wallet_api.py — API tests for TRUSTMEBRO Phase 1 wallet integration.

Tests:
  - GET /api/wallets: returns list, no private_key_pem, seeded demo wallets present.
  - POST /api/wallets: creates wallet, returns public data only.
  - POST /api/wallets empty name: 422 validation error.
  - POST /api/wallets whitespace-only name: 422 validation error.
  - POST /api/wallets name > 80 chars: 422 validation error.
  - GET /api/wallets/{id}: returns correct wallet.
  - GET /api/wallets/{id} unknown: 404.
  - Create then reload via GET: same public_key_hex.
  - Reload does not create extra wallets.

Uses FastAPI TestClient (synchronous, no real server needed).
"""
from api.session_store import current_session


import pytest
from tests.session_helpers import SessionTestClient as TestClient

# Reset module-level store between test sessions
import importlib
import api.wallet_store as ws


@pytest.fixture(autouse=True)
def reset_store():
    """Reset the in-memory wallet store before each test."""
    current_session().wallets._store.clear()
    current_session().wallets._seeded = False
    yield
    current_session().wallets._store.clear()
    current_session().wallets._seeded = False


@pytest.fixture
def client():
    # Import here so store reset takes effect first
    from api.wallet_api import app
    return TestClient(app, raise_server_exceptions=True)


# ── List wallets ─────────────────────────────────────────────────────────

def test_list_wallets_returns_list(client):
    r = client.get("/api/wallets")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_list_wallets_seeded_demo(client):
    """Demo wallets are pre-seeded and labeled source=demo."""
    data = client.get("/api/wallets").json()
    assert len(data) >= 2
    sources = [w["source"] for w in data]
    assert "demo" in sources


def test_list_wallets_no_private_key(client):
    """Private key must never appear in any wallet list response."""
    data = client.get("/api/wallets").json()
    for wallet in data:
        assert "private_key_pem" not in wallet
        assert "private_key" not in wallet
        assert "_private_key_pem" not in wallet


def test_list_wallets_public_fields(client):
    """Each wallet has required public fields."""
    data = client.get("/api/wallets").json()
    for w in data:
        assert "id" in w
        assert "name" in w
        assert "public_key_hex" in w
        assert "address" in w
        assert "source" in w


def test_list_wallets_public_key_format(client):
    """Public keys are uncompressed SECP256K1 points: 130 hex chars starting with 04."""
    data = client.get("/api/wallets").json()
    for w in data:
        assert len(w["public_key_hex"]) == 130
        assert w["public_key_hex"].startswith("04")


def test_list_wallets_address_format(client):
    """Address is 40 hex chars (first 40 of SHA-256(public_key_hex))."""
    data = client.get("/api/wallets").json()
    for w in data:
        assert len(w["address"]) == 40


# ── Create wallet ────────────────────────────────────────────────────────

def test_create_wallet_returns_201(client):
    r = client.post("/api/wallets", json={"name": "Đại học DEMO-Test"})
    assert r.status_code == 201


def test_create_wallet_public_data(client):
    r = client.post("/api/wallets", json={"name": "Đại học DEMO-Test"})
    w = r.json()
    assert w["name"] == "Đại học DEMO-Test"
    assert w["source"] == "user"
    assert len(w["public_key_hex"]) == 130
    assert w["public_key_hex"].startswith("04")
    assert len(w["address"]) == 40


def test_create_wallet_no_private_key(client):
    """Private key must never appear in create response."""
    r = client.post("/api/wallets", json={"name": "Test Org"})
    body = r.json()
    assert "private_key_pem" not in body
    assert "private_key" not in body
    assert "_private_key_pem" not in body


def test_create_wallet_appears_in_list(client):
    """Newly created wallet appears in subsequent list."""
    name = "Tổ chức Kiểm định DEMO-New"
    r = client.post("/api/wallets", json={"name": name})
    wallet_id = r.json()["id"]
    all_ids = [w["id"] for w in client.get("/api/wallets").json()]
    assert wallet_id in all_ids


def test_create_wallet_empty_name_rejected(client):
    r = client.post("/api/wallets", json={"name": ""})
    assert r.status_code == 422


def test_create_wallet_whitespace_name_rejected(client):
    r = client.post("/api/wallets", json={"name": "   "})
    assert r.status_code == 422


def test_create_wallet_name_too_long_rejected(client):
    r = client.post("/api/wallets", json={"name": "A" * 81})
    assert r.status_code == 422


def test_create_wallet_trims_name(client):
    """Leading/trailing whitespace is stripped from wallet name."""
    r = client.post("/api/wallets", json={"name": "  Demo Org  "})
    assert r.status_code == 201
    assert r.json()["name"] == "Demo Org"


def test_create_wallet_unique_ids(client):
    """Two wallets with same name get different IDs."""
    a = client.post("/api/wallets", json={"name": "Org"}).json()
    b = client.post("/api/wallets", json={"name": "Org"}).json()
    assert a["id"] != b["id"]


def test_create_wallet_unique_keys(client):
    """Each wallet gets a distinct public key (ECDSA keygen is random)."""
    a = client.post("/api/wallets", json={"name": "Org A"}).json()
    b = client.post("/api/wallets", json={"name": "Org B"}).json()
    assert a["public_key_hex"] != b["public_key_hex"]
    assert a["address"] != b["address"]


# ── Get wallet by ID ─────────────────────────────────────────────────────

def test_get_wallet_by_id(client):
    created = client.post("/api/wallets", json={"name": "Test Get"}).json()
    r = client.get(f"/api/wallets/{created['id']}")
    assert r.status_code == 200
    fetched = r.json()
    assert fetched["id"] == created["id"]
    assert fetched["public_key_hex"] == created["public_key_hex"]
    assert fetched["address"] == created["address"]


def test_get_wallet_no_private_key(client):
    created = client.post("/api/wallets", json={"name": "PK Check"}).json()
    fetched = client.get(f"/api/wallets/{created['id']}").json()
    assert "private_key_pem" not in fetched
    assert "private_key" not in fetched


def test_get_wallet_unknown_returns_404(client):
    r = client.get("/api/wallets/WALLET-UNKNOWN-000")
    assert r.status_code == 404


# ── Reload / re-validate behavior ────────────────────────────────────────

def test_reload_does_not_create_extra_wallets(client):
    """Listing wallets multiple times does not grow the store."""
    count_first  = len(client.get("/api/wallets").json())
    count_second = len(client.get("/api/wallets").json())
    assert count_first == count_second


def test_create_then_refetch_consistency(client):
    """Created wallet can be fetched by ID with identical public values."""
    created = client.post("/api/wallets", json={"name": "Reload Test"}).json()
    refetched = client.get(f"/api/wallets/{created['id']}").json()
    assert refetched["public_key_hex"] == created["public_key_hex"]
    assert refetched["address"] == created["address"]
    assert refetched["name"] == created["name"]
