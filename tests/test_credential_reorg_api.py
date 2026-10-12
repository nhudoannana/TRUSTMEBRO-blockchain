"""P3-A1 real credential API, projections and lifecycle."""
import copy
import time

import pytest
from fastapi.testclient import TestClient
from api import wallet_api
from tests.test_fork_lab_api import create, route, action, node, mine, context


@pytest.fixture
def client():
    with TestClient(wallet_api.app) as value:
        yield value


def credential(client, s, action_name="ISSUE", credential_id="cert-A", **fields):
    return action(client, s, "/credential-transactions", node_id="Node-1",
                  action=action_name, credential_id=credential_id, **fields)


def test_issue_revoke_projection_and_confirmation(client):
    s = create(client)
    r = credential(client, s, label="A")
    issue, s = r["transaction"], r["snapshot"]
    c = node(s)["credential_states"]["cert-A"]
    assert c["status"] is c["confirmed_status"] is None
    assert c["confirmed_transactions"] == []
    assert c["pending_transactions"] == [issue]
    assert node(s)["transaction_states"][issue["tx_id"]]["pending"]
    assert node(s, "Node-2")["credential_states"]["cert-A"]["pending_transactions"] == []
    s = mine(client, s, tx_ids=[issue["tx_id"]])["snapshot"]
    c = node(s)["credential_states"]["cert-A"]
    assert c["confirmed_status"] == "ACTIVE"
    assert c["confirmed_tx_ids"] == [issue["tx_id"]]
    assert c["confirmed_transactions"][0]["transaction"] == issue
    assert c["pending_transactions"] == []
    r = credential(client, s, "REVOKE", reason="withdraw")
    revoke, s = r["transaction"], r["snapshot"]
    assert node(s)["credential_states"]["cert-A"]["confirmed_status"] == "ACTIVE"
    s = mine(client, s, tx_ids=[revoke["tx_id"]])["snapshot"]
    c = node(s)["credential_states"]["cert-A"]
    assert c["confirmed_status"] == "REVOKED"
    assert c["confirmed_tx_ids"] == [issue["tx_id"], revoke["tx_id"]]
    for tx in (issue, revoke):
        projection = node(s)["transaction_states"][tx["tx_id"]]
        assert len(projection["active_blocks"]) == 1
        assert not projection["pending"] and not projection["stale_blocks"]
    before = copy.deepcopy(s)
    for body in (dict(action="ISSUE", label="again"), dict(action="REVOKE", reason="again")):
        r = client.post(route(s, "/credential-transactions"), json=dict(
            expected_revision=s["revision"], node_id="Node-1", credential_id="cert-A", **body))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "transaction_rejected"
        after = client.get(route(s)).json()
        for key in ("revision", "pending_messages"):
            assert after[key] == before[key]
        assert node(after)["mempool"] == node(before)["mempool"]
        assert node(after)["tip_hash"] == node(before)["tip_hash"]


@pytest.mark.parametrize("patch", [
    {"credential_id": ""}, {"credential_id": " "*4}, {"credential_id": "x"*65},
    {"label": ""}, {"label": "  "}, {"label": "x"*121}, {"label": 3},
    {"label": "\ud800"}, {"credential_id": "\ud800"},
    {"action": "TRANSFER"}, {"reason": "inapplicable"}, {"reason": None},
    {"private_key": "no"}, {"expected_revision": True},
])
def test_strict_request_is_rejected_without_mutation(client, patch):
    s = create(client)
    body = dict(expected_revision=s["revision"], node_id="Node-1", action="ISSUE",
                credential_id="cert-A", label="A")
    body.update(patch)
    # ASCII JSON preserves lone surrogate so server, rather than client encoder, rejects it.
    import json
    r = client.post(route(s, "/credential-transactions"),
                    content=json.dumps(body), headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text
    after = client.get(route(s)).json()
    assert after["revision"] == 0 and after["pending_messages"] == []
    assert node(after)["mempool"] == [] and node(after)["credential_states"] == {}


@pytest.mark.parametrize("patch", [{"reason": ""}, {"reason": " "*3},
    {"reason": "x"*121}, {"reason": "\ud800"}, {"label": "bad"}, {"label": None}])
def test_revoke_schema_rejection(client, patch):
    s = create(client)
    import json
    body = dict(expected_revision=0, node_id="Node-1", action="REVOKE",
                credential_id="cert-A", reason="r")
    body.update(patch)
    r = client.post(route(s, "/credential-transactions"), content=json.dumps(body),
                    headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text


def test_missing_issue_stale_ownership_reset_expiry_and_offline(client):
    s = create(client)
    r = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="REVOKE", credential_id="cert-A", reason="r"))
    assert r.status_code == 409
    assert client.get(route(s)).json()["revision"] == 0
    r = credential(client, s, label="A")
    latest = r["snapshot"]
    stale = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="other", label="B"))
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_revision"
    other = TestClient(wallet_api.app)
    try:
        foreign = other.post(route(latest, "/credential-transactions"), json=dict(
            expected_revision=1, node_id="Node-1", action="ISSUE", credential_id="other", label="B"))
        assert foreign.status_code == 404
    finally:
        other.close()
    latest = action(client, latest, "/nodes/Node-1/status", status="OFFLINE")["snapshot"]
    r = client.post(route(latest, "/credential-transactions"), json=dict(
        expected_revision=latest["revision"], node_id="Node-1", action="ISSUE", credential_id="other", label="B"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "offline"
    entry = context(client).lab_networks[latest["lab_handle"]]
    entry["expires"] = time.monotonic() - 1
    assert client.post(route(latest, "/credential-transactions"), json=dict(
        expected_revision=latest["revision"], node_id="Node-1", action="ISSUE", credential_id="other", label="B")).status_code == 404
    fresh = create(client)
    client.delete(route(fresh))
    assert client.post(route(fresh, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="other", label="B")).status_code == 404


def test_limits_and_trim(client):
    s = create(client)
    r = credential(client, s, credential_id="c"*64, label="a"*120)
    assert r["transaction"]["payload"]["label"] == "a"*120
    s = r["snapshot"]
    # Other tests use fixtures for capacity; this checks the limit through actual admissions.
    for i in range(31):
        s = credential(client, s, credential_id=f"c-{i}", label="a")["snapshot"]
    before = client.get(route(s)).json()
    r = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=s["revision"], node_id="Node-1", action="ISSUE", credential_id="overflow", label="a"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "transaction_capacity"
    after = client.get(route(s)).json()
    assert after["revision"] == before["revision"]
    assert after["pending_messages"] == before["pending_messages"]


def test_reorg_projection_is_active_chain_only_and_real_restoration(client):
    s = create(client)
    s = action(client, s, "/links", changes=[
        dict(a=a, b=b, connected=False) for a,b in
        (("Node-1","Node-2"), ("Node-1","Node-3"), ("Node-2","Node-3"))])["snapshot"]
    r = credential(client, s, label="A")
    issue, s = r["transaction"], r["snapshot"]
    s = mine(client, s, tx_ids=[issue["tx_id"]])["snapshot"]
    s = mine(client, s, "Node-3", difficulty=2)["snapshot"]
    s = action(client, s, "/links", changes=[dict(a="Node-1", b="Node-3", connected=True)])["snapshot"]
    s = action(client, s, "/sync", node_id="Node-1")["snapshot"]
    request = next(m for m in s["pending_messages"] if m["kind"] == "SYNC_REQUEST" and m["from"] == "Node-1")
    s = action(client, s, "/deliver", message_id=request["id"])["snapshot"]
    response = next(m for m in s["pending_messages"] if m["kind"] == "SYNC_RESPONSE" and m["to"] == "Node-1")
    s = action(client, s, "/deliver", message_id=response["id"])["snapshot"]
    c = node(s)["credential_states"]["cert-A"]
    assert c["confirmed_status"] is None and c["confirmed_tx_ids"] == []
    assert c["pending_transactions"] == [issue]
    assert c["stale_transactions"][0]["transaction"] == issue
    p = node(s)["transaction_states"][issue["tx_id"]]
    assert p["active_blocks"] == [] and p["pending"] and len(p["stale_blocks"]) == 1
    assert node(s)["last_transition"]["counts"]["restored"] == 1


def test_expiry_during_signing_does_not_publish(client, monkeypatch):
    from blockchain.transaction import Transaction
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    original = Transaction.sign

    def expire(tx, wallet):
        original(tx, wallet)
        entry["expires"] = time.monotonic() - 1

    monkeypatch.setattr(Transaction, "sign", expire)
    response = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="late", label="A"))
    assert response.status_code == 404
    assert entry["lab"].transactions == {}
    assert entry["network"].nodes["Node-1"].mempool.get_transactions() == []
    assert not entry["network"].pending
    assert entry["lab"].revision == 0


def test_reset_serializes_pending_signing_and_handle_cannot_revive(client, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from blockchain.transaction import Transaction
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    entered, release, reset_started = threading.Event(), threading.Event(), threading.Event()
    original = Transaction.sign

    def paused(tx, wallet):
        entered.set()
        assert release.wait(5)
        original(tx, wallet)

    def reset():
        reset_started.set()
        return client.delete(route(s))

    monkeypatch.setattr(Transaction, "sign", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation = pool.submit(client.post, route(s, "/credential-transactions"), json=dict(
            expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="A", label="A"))
        assert entered.wait(5)
        deletion = pool.submit(reset)
        assert reset_started.wait(5)
        # Same lifecycle lock: reset cannot close the network midway through admission.
        assert not deletion.done()
        release.set()
        assert mutation.result(timeout=5).status_code == 200
        assert deletion.result(timeout=5).json() == {"cleared": True}
    assert entry["network"].closed and not entry["network"].pending
    assert client.get(route(s)).status_code == 404
    assert s["lab_handle"] not in context(client).lab_networks


def test_legacy_issue_endpoint_also_has_additive_projection(client):
    s = create(client)
    r = action(client, s, "/transactions", node_id="Node-1", label="legacy")
    tx, s = r["transaction"], r["snapshot"]
    c = node(s)["credential_states"][tx["payload"]["credential_id"]]
    assert c["status"] is None and c["confirmed_tx_ids"] == []
    assert c["pending_transactions"] == [tx]
    assert node(s)["transaction_states"][tx["tx_id"]]["pending"]
    # Returned projection data is detached from live transaction payloads.
    entry = context(client).lab_networks[s["lab_handle"]]
    projection, _ = entry["lab"].credential_projection(entry["network"].nodes["Node-1"])
    projection[tx["payload"]["credential_id"]]["pending_transactions"][0]["payload"]["label"] = "changed"
    assert entry["lab"].transactions[tx["tx_id"]].payload["label"] == "legacy"


def test_expiry_during_ledger_verification_has_no_publication(client, monkeypatch):
    import blockchain.mempool as module
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    n = entry["network"].nodes["Node-1"]
    original = module.verify_ledger_transaction
    before_seen = set(n._seen_tx_ids)

    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result[0]
        entry["expires"] = time.monotonic() - 1
        return result

    monkeypatch.setattr(module, "verify_ledger_transaction", expire)
    response = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="late", label="A"))
    assert response.status_code == 404
    assert entry["lab"].transactions == {}
    assert n.mempool.get_transactions() == []
    assert n._seen_tx_ids == before_seen and not entry["network"].pending
    assert entry["lab"].revision == 0


def test_expiry_after_admission_returns_committed_success(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    network = entry["network"]
    original = network.broadcast

    def expire_after_publication(*args, **kwargs):
        original(*args, **kwargs)
        entry["expires"] = time.monotonic() - 1

    monkeypatch.setattr(network, "broadcast", expire_after_publication)
    response = client.post(route(s, "/credential-transactions"), json=dict(
        expected_revision=0, node_id="Node-1", action="ISSUE", credential_id="A", label="A"))
    assert response.status_code == 200, response.text
    r = response.json()
    assert r["outcome"]["code"] == "accepted_tx" and r["revision"] == 1
    tx_id = r["transaction"]["tx_id"]
    assert tx_id in entry["lab"].transactions
    assert tx_id in network.nodes["Node-1"].mempool._pool
    assert r["snapshot"]["expires_in_seconds"] == 0
    # A committed operation does not extend lifetime or revive an expired handle.
    assert client.get(route(s)).status_code == 404
