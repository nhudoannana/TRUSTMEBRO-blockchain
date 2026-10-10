"""Fork API: real learner continuation, ownership, revisions and bounds."""
import copy

import pytest
from fastapi.testclient import TestClient
from api import wallet_api, session_store


@pytest.fixture
def client():
    with TestClient(wallet_api.app) as client:
        yield client


def create(client):
    r = client.post("/api/labs/fork", json={})
    assert r.status_code == 201, r.text
    return r.json()


def route(s, suffix=""):
    return "/api/labs/fork/" + s["lab_handle"] + suffix


def action(client, s, suffix, **body):
    r = client.post(route(s, suffix), json={"expected_revision": s["revision"], **body})
    assert r.status_code == 200, r.text
    return r.json()


def node(s, key="Node-1"):
    return next(n for n in s["nodes"] if n["node_id"] == key)


def mine(client, s, key="Node-1", difficulty=1, tx_ids=()):
    return action(client, s, "/mine", node_id=key, parent_hash=node(s, key)["tip_hash"],
                  difficulty=difficulty, tx_ids=list(tx_ids))


def context(client):
    return session_store.registry.entries[client.cookies.get(session_store.COOKIE_NAME)]


def test_create_owns_three_independent_nodes_and_get_does_not_mutate(client):
    s = create(client)
    assert s["delivery_mode"] == "manual" and s["tie_policy"] == "keep_valid_current"
    assert len(s["nodes"]) == 3 and all(n["chain_work"] == 0 for n in s["nodes"])
    entry = context(client).lab_networks[s["lab_handle"]]
    ns = list(entry["network"].nodes.values())
    assert len({id(n.blockchain) for n in ns}) == 3
    assert len({id(n.mempool) for n in ns}) == 3
    assert client.get(route(s)).json()["revision"] == s["revision"]
    assert client.delete(route(s)).json() == {"cleared": True}
    assert client.delete(route(s)).json() == {"cleared": False}
    assert all(not n._worker.is_alive() for n in ns)


def test_real_signed_transaction_mine_delivery_and_stale_revision(client):
    s = create(client)
    result = action(client, s, "/transactions", node_id="Node-1", label="Bằng A")
    tx = result["transaction"]
    s = result["snapshot"]
    from blockchain.transaction import Transaction, verify_transaction
    from blockchain.net_node import tx_from_json
    assert verify_transaction(tx_from_json(tx))[0]
    result = mine(client, s, tx_ids=[tx["tx_id"]])
    s = result["snapshot"]
    assert node(s)["height"] == 1 and node(s)["chain_work"] == 16
    assert node(s, "Node-2")["height"] == 0
    block = next(m for m in s["pending_messages"] if m["kind"] == "BLOCK" and m["to"] == "Node-2")
    old = copy.deepcopy(s)
    s = action(client, s, "/deliver", message_id=block["id"])["snapshot"]
    assert node(s, "Node-2")["height"] == 1 and node(s, "Node-2")["chain_valid"]
    r = client.post(route(old, "/discard"), json={"expected_revision": old["revision"], "message_id": block["id"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "stale_revision"
    assert client.get(route(s)).json()["revision"] == s["revision"]


@pytest.mark.parametrize("scenario", ["E1", "E2", "E4", "E5"])
def test_each_loader_stops_before_decision_and_manual_continuation(client, scenario):
    s = create(client)
    result = action(client, s, "/scenario", scenario=scenario)
    assert result["outcome"]["code"] == "scenario_ready"
    s, next_action = result["snapshot"], result["continuation"]
    if scenario == "E1":
        assert node(s)["chain_work"] == 256 and node(s, "Node-3")["chain_work"] == 256
        original = node(s)["tip_hash"]
        s = action(client, s, "/links", changes=next_action["reconnect"])["snapshot"]
        s = action(client, s, "/deliver", message_id=next_action["message_id"])["snapshot"]
        assert node(s)["tip_hash"] == original
        assert len(node(s)["branches"]) >= 2
        s = mine(client, s, "Node-3", 2)["snapshot"]
        child = next(m for m in s["pending_messages"] if m["kind"] == "BLOCK" and m["to"] == "Node-1"
                     and m["reference"] == node(s, "Node-3")["tip_hash"])
        s = action(client, s, "/deliver", message_id=child["id"])["snapshot"]
        assert node(s)["chain_work"] == 512
        for _ in range(100):
            if not s["pending_messages"]:
                break
            s = action(client, s, "/deliver", message_id=s["pending_messages"][0]["id"])["snapshot"]
        assert not s["pending_messages"]
        assert {n["chain_work"] for n in s["nodes"]} == {512}
        assert len({n["tip_hash"] for n in s["nodes"]}) == 1
        assert all(n["chain_valid"] for n in s["nodes"])
    elif scenario == "E2":
        assert node(s)["height"] == 3 and node(s)["chain_work"] == 768
        assert node(s, "Node-3")["height"] == 1 and node(s, "Node-3")["chain_work"] == 4096
        s = action(client, s, "/deliver", message_id=next_action["message_id"])["snapshot"]
        assert node(s)["height"] == 1 and node(s)["chain_work"] == 4096
    elif scenario == "E4":
        detached = next_action["detached_tx_id"]
        assert node(s)["credential_states"][next_action["credential_id"]]["status"] == "ACTIVE"
        result = action(client, s, "/deliver", message_id=next_action["message_id"])
        s = result["snapshot"]
        assert result["transition"]["counts"]["restored"] == 1
        assert detached in [t["tx_id"] for t in node(s)["mempool"]]
        assert node(s)["credential_states"][next_action["credential_id"]]["status"] is None
        s = mine(client, s, tx_ids=[detached])["snapshot"]
        assert node(s)["credential_states"][next_action["credential_id"]]["status"] == "ACTIVE"
    else:
        assert node(s, "Node-2")["height"] == 0
        s = action(client, s, "/deliver", message_id=next_action["child_message_id"])["snapshot"]
        assert len(node(s, "Node-2")["orphans"]) == 1
        assert node(s, "Node-2")["chain_work"] == 0
        s = action(client, s, "/deliver", message_id=next_action["parent_message_id"])["snapshot"]
        assert node(s, "Node-2")["height"] == 2 and not node(s, "Node-2")["orphans"]


def test_cross_session_all_mutations_and_reset_do_not_touch_other_labs(client):
    s = create(client)
    independent = client.post("/api/labs/network", json={}).json()
    with TestClient(wallet_api.app) as other:
        assert other.get(route(s)).status_code == 404
        assert other.delete(route(s)).status_code == 404
        for suffix, body in [
            ("/links", {"changes": [{"a": "Node-1", "b": "Node-2", "connected": False}]}),
            ("/transactions", {"node_id": "Node-1", "label": "x"}),
            ("/mine", {"node_id": "Node-1", "parent_hash": node(s)["tip_hash"], "difficulty": 1, "tx_ids": []}),
            ("/sync", {"node_id": "Node-1"}), ("/deliver", {"message_id": "x"}),
            ("/discard", {"message_id": "x"}), ("/scenario", {"scenario": "E1"}),
            ("/nodes/Node-1/status", {"status": "OFFLINE"})]:
            assert other.post(route(s, suffix), json={"expected_revision": 0, **body}).status_code == 404
    # Other TestClient shutdown retires the shared registry: verify isolation above while both live.


@pytest.mark.parametrize("suffix,body", [
    ("/mine", {"node_id": "Node-1", "parent_hash": "x", "difficulty": 1, "tx_ids": []}),
    ("/mine", {"node_id": "Node-1", "parent_hash": "a"*64, "difficulty": True, "tx_ids": []}),
    ("/transactions", {"node_id": "Node-4", "label": "x"}),
    ("/transactions", {"node_id": "Node-1", "label": " "*3}),
    ("/transactions", {"node_id": "Node-1", "label": "a"*121}),
    ("/sync", {"node_id": "Node-1", "peer_url": "http://evil"}),
    ("/scenario", {"scenario": "E3"}),
])
def test_malformed_requests_never_mutate(client, suffix, body):
    s = create(client)
    assert client.post(route(s, suffix), json={"expected_revision": 0, **body}).status_code == 422
    assert client.get(route(s)).json()["revision"] == 0


def test_limits_expiry_and_owned_kind(client):
    s = create(client)
    for i in range(32):
        s = action(client, s, "/transactions", node_id="Node-1", label=f"x{i}")["snapshot"]
    r = client.post(route(s, "/transactions"), json={"expected_revision": s["revision"], "node_id": "Node-1", "label": "overflow"})
    assert r.status_code == 409
    assert len(node(client.get(route(s)).json())["mempool"]) == 32
    entry = context(client).lab_networks[s["lab_handle"]]
    entry["expires"] = 0
    assert client.get(route(s)).status_code == 404
    assert entry["network"].closed
    network = client.post("/api/labs/network", json={}).json()
    assert client.get("/api/labs/fork/" + network["lab_handle"]).status_code == 404


def test_partition_sync_offline_and_discard_do_not_silently_converge(client):
    s = create(client)
    s = mine(client, s)["snapshot"]
    incoming = next(m for m in s["pending_messages"] if m["to"] == "Node-2")
    s = action(client, s, "/links", changes=[dict(a="Node-1", b="Node-2", connected=False)])["snapshot"]
    r = action(client, s, "/deliver", message_id=incoming["id"])
    assert r["outcome"]["code"] == "blocked"
    s = r["snapshot"]
    s = action(client, s, "/discard", message_id=incoming["id"])["snapshot"]
    s = action(client, s, "/links", changes=[dict(a="Node-1", b="Node-2", connected=True)])["snapshot"]
    assert node(s, "Node-2")["height"] == 0
    assert not any(m["id"] == incoming["id"] for m in s["pending_messages"])
    s = action(client, s, "/sync", node_id="Node-2")["snapshot"]
    request = next(m for m in s["pending_messages"] if m["kind"] == "SYNC_REQUEST" and m["to"] == "Node-1")
    s = action(client, s, "/deliver", message_id=request["id"])["snapshot"]
    response = next(m for m in s["pending_messages"] if m["kind"] == "SYNC_RESPONSE" and m["to"] == "Node-2")
    s = action(client, s, "/nodes/Node-2/status", status="OFFLINE")["snapshot"]
    assert action(client, s, "/deliver", message_id=response["id"])["outcome"]["code"] == "blocked"
    s = client.get(route(s)).json()
    s = action(client, s, "/nodes/Node-2/status", status="ONLINE")["snapshot"]
    assert node(s, "Node-2")["height"] == 0
    s = action(client, s, "/deliver", message_id=response["id"])["snapshot"]
    assert node(s, "Node-2")["height"] == 1


def test_block_limit_admission_and_atomic_link_validation(client):
    s = create(client)
    for i in range(12):
        s = mine(client, s)["snapshot"]
    before = copy.deepcopy(s)
    r = client.post(route(s, "/mine"), json={"expected_revision": s["revision"], "node_id": "Node-1",
        "parent_hash": node(s)["tip_hash"], "difficulty": 1, "tx_ids": []})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "block_capacity"
    r = client.post(route(s, "/links"), json={"expected_revision": s["revision"], "changes": [
        {"a": "Node-1", "b": "Node-2", "connected": False},
        {"a": "Node-3", "b": "Node-3", "connected": False}]})
    assert r.status_code == 409
    after = client.get(route(s)).json()
    assert after["revision"] == before["revision"] and after["links"] == before["links"]
    assert node(after)["height"] == 12


def test_unknown_parent_transactions_and_uppercase_hash_normalization(client):
    s = create(client)
    assert client.post(route(s, "/mine"), json={"expected_revision": 0, "node_id": "Node-1",
        "parent_hash": "f"*64, "difficulty": 1, "tx_ids": []}).status_code == 409
    assert client.post(route(s, "/mine"), json={"expected_revision": 0, "node_id": "Node-1",
        "parent_hash": node(s)["tip_hash"], "difficulty": 1, "tx_ids": ["a"*64]}).status_code == 409
    r = action(client, s, "/mine", node_id="Node-1", parent_hash=node(s)["tip_hash"].upper(), difficulty=1, tx_ids=[])
    assert node(r["snapshot"])["height"] == 1


def test_loader_partial_failure_keeps_real_progress_and_requires_fresh_state(client, monkeypatch):
    from api import fork_lab
    original = wallet_api._mine_lab_block_bounded
    calls = []
    def partial(block):
        calls.append(block)
        if len(calls) == 2:
            return dict(completed=False, reason="fixture: bounded mining incomplete", attempts=0, seconds=0)
        return original(block)
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", partial)
    s = create(client)
    r = action(client, s, "/scenario", scenario="E2")
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert "bounded mining incomplete" in r["outcome"]["message"]
    assert len(r["setup_completed_steps"]) == 1
    s = r["snapshot"]
    assert node(s)["height"] == 1 and node(s)["chain_work"] == 256
    assert len(node(s)["mempool"]) == 0
    assert client.post(route(s, "/scenario"), json={"expected_revision": s["revision"], "scenario": "E4"}).status_code == 409


@pytest.mark.parametrize("operation", ["mine", "deliver"])
def test_reset_waits_for_bounded_action_then_retires_old_state(client, monkeypatch, operation):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    entered, release, deleting = threading.Event(), threading.Event(), threading.Event()
    if operation == "mine":
        original = wallet_api._mine_lab_block_bounded
        def paused(block):
            entered.set()
            assert release.wait(5)
            return original(block)
        monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", paused)
        body = dict(node_id="Node-1", parent_hash=node(s)["tip_hash"], difficulty=1, tx_ids=[])
    else:
        s = mine(client, s)["snapshot"]
        original = entry["network"]._block
        def paused(*args):
            entered.set()
            assert release.wait(5)
            return original(*args)
        monkeypatch.setattr(entry["network"], "_block", paused)
        body = dict(message_id=next(m["id"] for m in s["pending_messages"] if m["to"] == "Node-2"))
    def delete():
        deleting.set()
        return client.delete(route(s))
    with ThreadPoolExecutor(max_workers=2) as workers:
        working = workers.submit(client.post, route(s, "/"+operation), json={"expected_revision": s["revision"], **body})
        assert entered.wait(2)
        resetting = workers.submit(delete)
        assert deleting.wait(2)
        assert not resetting.done()
        release.set()
        assert working.result(timeout=5).status_code == 200
        assert resetting.result(timeout=5).json() == {"cleared": True}
    assert client.get(route(s)).status_code == 404
    assert entry["network"].closed and not entry["network"].pending
    assert not any(entry["network"].orphans.values())
    fresh = create(client)
    assert fresh["revision"] == 0 and all(n["height"] == 0 for n in fresh["nodes"])


def test_expiry_during_mining_does_not_publish_candidate(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    original = wallet_api._mine_lab_block_bounded
    def expires(block):
        result = original(block)
        entry["expires"] = 0
        return result
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", expires)
    r = client.post(route(s, "/mine"), json={"expected_revision": 0, "node_id": "Node-1",
            "parent_hash": node(s)["tip_hash"], "difficulty": 1, "tx_ids": []})
    assert r.status_code == 404
    assert entry["network"].nodes["Node-1"].height == 0
    assert client.get(route(s)).status_code == 404 and entry["network"].closed


def test_reset_fork_leaves_existing_lab_and_guided_session_untouched(client):
    s = create(client)
    existing = client.post("/api/labs/network", json={}).json()
    guided = client.get("/api/session").json()
    assert client.delete(route(s)).json()["cleared"]
    assert client.get("/api/labs/network/"+existing["lab_handle"]).status_code == 200
    assert client.get("/api/session").json() == guided


def test_guided_reset_preserves_independent_fork_and_its_owned_cleanup(client):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    s = mine(client, s)["snapshot"]
    assert client.post("/api/session/reset").status_code == 200
    after = client.get(route(s)).json()
    assert not entry["network"].closed
    assert node(after)["height"] == 1 and after["revision"] == s["revision"]
    assert after["context_generation"] != s["context_generation"]
    assert client.delete(route(s)).json() == {"cleared": True}
    assert entry["network"].closed



@pytest.mark.parametrize("cause", ["partition", "capacity", "duplicate"])
def test_sync_reports_only_actual_new_scheduling(client, monkeypatch, cause):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    if cause == "partition":
        s = action(client, s, "/links", changes=[
            dict(a="Node-1", b="Node-2", connected=False),
            dict(a="Node-1", b="Node-3", connected=False)])["snapshot"]
    elif cause == "capacity":
        monkeypatch.setattr(entry["network"], "MAX_MESSAGES", 0)
    else:
        s = action(client, s, "/sync", node_id="Node-1")["snapshot"]
    before = len(s["pending_messages"])
    r = action(client, s, "/sync", node_id="Node-1")
    assert r["outcome"]["code"] == "sync_not_scheduled"
    assert r["scheduled_count"] == 0
    assert len(r["snapshot"]["pending_messages"]) == before


def test_real_bounded_mining_failure_keeps_pending_transaction(client, monkeypatch):
    s = create(client)
    r = action(client, s, "/transactions", node_id="Node-1", label="Giới hạn")
    tx_id, s = r["transaction"]["tx_id"], r["snapshot"]
    monkeypatch.setattr(wallet_api, "_BLOCK_LAB_MAX_ATTEMPTS", 0)
    r = mine(client, s, tx_ids=[tx_id])
    assert r["outcome"]["code"] == "mining_incomplete"
    assert r["mining"]["completed"] is False and r["mining"]["attempts"] == 0
    assert node(r["snapshot"])["height"] == 0
    assert [t["tx_id"] for t in node(r["snapshot"])["mempool"]] == [tx_id]


def test_lab_entry_capacity_and_shutdown_cleanup_are_bounded(client):
    snapshots = [create(client) for _ in range(8)]
    entries = list(context(client).lab_networks.values())
    assert client.post("/api/labs/fork", json={}).status_code == 429
    context(client).close()
    assert not context(client).lab_networks
    assert all(e["network"].closed and not e["timer"].is_alive() or e["timer"].finished.is_set() for e in entries)
    assert all(not n._worker.is_alive() for e in entries for n in e["network"].nodes.values())
