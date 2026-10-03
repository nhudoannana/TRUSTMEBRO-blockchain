"""Shared demo session lifecycle tests (FastAPI TestClient, no browser)."""

import threading

from fastapi.testclient import TestClient

from api.wallet_api import app
from blockchain.node import Network


def test_node_stop_is_idempotent():
    net = Network()
    node = net.create_node("Stop-Test", "127.0.0.1", 5001)
    try:
        node.stop()
        node.stop()
        assert not node._running
        assert not node._worker.is_alive()
    finally:
        node._running = False
        node._worker.join(timeout=1)


def test_reset_reseeds_wallets_and_replaces_network():
    from api.network_store import get_network

    with TestClient(app) as client:
        before = client.get("/api/session").json()
        old = get_network()
        demos = client.get("/api/wallets").json()
        created = client.post("/api/wallets", json={"name": "Reset me"}).json()
        old.nodes["Node-1"].go_offline()
        response = client.post("/api/session/reset")
        assert response.status_code == 200
        session = response.json()
        assert session["shared_session"] is True
        assert session["reset_count"] == before["reset_count"] + 1
        assert session["wallet_count"] == 2
        assert session["nodes"] == [
            {"id": f"Node-{i}", "status": "ONLINE"} for i in range(1, 4)
        ]
        assert client.get("/api/session").json() == session
        assert client.get(f"/api/wallets/{created['id']}").status_code == 404
        fresh = client.get("/api/wallets").json()
        assert len(fresh) == 2
        assert all(w["source"] == "demo" for w in fresh)
        assert {w["name"] for w in fresh} == {w["name"] for w in demos if w["source"] == "demo"}
        assert not {w["id"] for w in fresh} & {w["id"] for w in demos}
        assert get_network() is not old
        assert get_network() is get_network()
        assert all(not n._worker.is_alive() for n in old.nodes.values())
        assert all(n.height == 0 for n in get_network().nodes.values())


def test_repeated_resets_keep_three_workers():
    with TestClient(app) as client:
        initial = client.get("/api/session").json()["reset_count"]
        for count in range(1, 5):
            assert client.post("/api/session/reset").status_code == 200
            assert client.get("/api/session").json()["reset_count"] == initial + count
            workers = [t for t in threading.enumerate() if t.name.startswith("worker-")]
            assert len(workers) == 3
