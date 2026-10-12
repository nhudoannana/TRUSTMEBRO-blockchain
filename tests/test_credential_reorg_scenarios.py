"""P3-A2 loaders use real backend operations and stop at learner delivery."""
import copy
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from api import wallet_api
from blockchain.transaction import verify_transaction
from tests.test_fork_lab_api import create, route, action, node, mine, context


@pytest.fixture
def client():
    with TestClient(wallet_api.app) as value:
        yield value


def load(client, s, scenario):
    return action(client, s, "/scenario", scenario=scenario)


@pytest.mark.parametrize("scenario", ["C1", "C2", "C3"])
def test_manual_continuation_real_state_and_dispositions(client, scenario):
    s = create(client)
    r = load(client, s, scenario)
    assert r["outcome"]["code"] == "scenario_ready", r
    s, c = r["snapshot"], r["continuation"]
    credential_id, revoke_id, issue_id = c["credential_id"], c["revoke_tx_id"], c["issue_tx_id"]
    assert c["node_id"] == "Node-1" and c["peer_node_id"] == "Node-3"
    assert c["learning_goal"] and c["next_steps"]
    n, peer = node(s), node(s, "Node-3")
    assert n["credential_states"][credential_id]["confirmed_status"] == "REVOKED"
    assert peer["credential_states"][credential_id]["confirmed_status"] == {
        "C1": "ACTIVE", "C2": None, "C3": "REVOKED"}[scenario]
    assert peer["chain_work"] > n["chain_work"]
    decisive = next(m for m in s["pending_messages"] if m["id"] == c["message_id"])
    assert decisive["kind"] == "BLOCK" and decisive["from"] == "Node-3" and decisive["to"] == "Node-1"
    assert decisive["reference"] == c["winning_block_hash"] and not decisive["blocked_reason"]
    assert c["winning_block_hash"] not in {b["hash"] for b in n["blocks"]}
    assert node(s, "Node-2")["height"] == 0
    assert all(n["chain_valid"] for n in s["nodes"])
    entry = context(client).lab_networks[s["lab_handle"]]
    assert len(entry["lab"].transactions) == 2
    assert all(n._publication_guard is None for n in entry["network"].nodes.values())
    assert all(verify_transaction(tx)[0] for tx in entry["lab"].transactions.values())
    assert len(entry["network"].admitted_hashes()) <= 12
    assert len(s["pending_messages"]) <= 64
    assert all(len(n["mempool"]) <= 32 for n in s["nodes"])
    before_tip = n["tip_hash"]
    r = action(client, s, "/deliver", message_id=c["message_id"])
    s, transition = r["snapshot"], r["transition"]
    assert r["outcome"]["code"] == "accepted_block" and transition
    n = node(s)
    assert n["tip_hash"] != before_tip and n["tip_hash"] == c["winning_block_hash"]
    records = {t["tx_id"]: t for t in transition["transactions"]}
    pending = [tx["tx_id"] for tx in n["mempool"]]
    state = n["credential_states"][credential_id]
    if scenario == "C1":
        assert state["confirmed_status"] == "ACTIVE" and state["confirmed_tx_ids"] == [issue_id]
        assert pending == [revoke_id]
        assert transition["counts"]["restored"] == 1
        assert records[revoke_id]["reason_code"] == "accepted_detached"
        assert c["remine_tx_ids"] == [revoke_id]
        r = mine(client, s, tx_ids=c["remine_tx_ids"])
        assert r["outcome"]["code"] == "accepted_block"
        s = r["snapshot"]
        assert node(s)["credential_states"][credential_id]["confirmed_status"] == "REVOKED"
        assert revoke_id not in [t["tx_id"] for t in node(s)["mempool"]]
    elif scenario == "C2":
        assert state["confirmed_status"] is None and state["confirmed_tx_ids"] == []
        assert pending == [issue_id] and transition["counts"]["restored"] == 1
        assert records[issue_id]["reason_code"] == "accepted_detached"
        assert records[revoke_id]["reason_code"] == "not_active_on_chain"
        assert records[revoke_id]["disposition"] == "rejected"
        # Pending ISSUE still cannot authorize another REVOKE.
        response = client.post(route(s, "/credential-transactions"), json=dict(
            expected_revision=s["revision"], node_id="Node-1", action="REVOKE",
            credential_id=credential_id, reason="retry"))
        assert response.status_code == 409
    else:
        assert state["confirmed_status"] == "REVOKED"
        assert state["confirmed_tx_ids"] == [issue_id, revoke_id] and pending == []
        assert transition["counts"]["restored"] == 0
        assert records[revoke_id]["reason_code"] == "confirmed_on_new_chain"
        assert records[revoke_id]["disposition"] == "confirmed"
        placements = n["transaction_states"][revoke_id]
        assert placements["active_blocks"] and placements["stale_blocks"] and not placements["pending"]
    assert all(n["chain_valid"] for n in s["nodes"])


@pytest.mark.parametrize("scenario", ["C1","C2","C3"])
def test_mining_failure_keeps_actual_prefix_not_ready(client, monkeypatch, scenario):
    real = wallet_api._mine_lab_block_bounded
    calls = []
    def fail_second(block):
        calls.append(block)
        if len(calls) == 2:
            return dict(completed=False, reason="bounded budget fixture", attempts=0, seconds=0)
        return real(block)
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", fail_second)
    r = load(client, create(client), scenario)
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["continuation"] is None
    assert r["setup_failure"]["code"] == "mining_incomplete"
    assert r["setup_failure"]["mining"]["completed"] is False
    s = r["snapshot"]
    assert node(s)["height"] == 1
    assert node(s)["credential_states"][r["credential_id"]]["confirmed_status"] == "ACTIVE"
    assert len([p for p in r["setup_completed_steps"] if p["operation"] == "mine"]) == 1
    assert len(node(s)["mempool"]) == 1
    assert s["revision"] == 1
    assert not any(e["code"] == "scenario_ready" for e in s["events"])
    retry = client.post(route(s, "/scenario"), json=dict(expected_revision=1, scenario=scenario))
    assert retry.status_code == 409 and retry.json()["detail"]["code"] == "scenario_requires_empty"


@pytest.mark.parametrize("scenario", ["C1","C2","C3"])
def test_block_capacity_is_not_bypassed(client, scenario):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    entry["network"].MAX_BLOCKS = 1
    r = load(client, s, scenario)
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert all(n._publication_guard is None for n in entry["network"].nodes.values())
    assert r["setup_failure"]["code"] == "block_capacity"
    assert r["continuation"] is None
    assert len(entry["network"].admitted_hashes()) == 1


def test_queue_capacity_failure_is_explicit_not_false_ready(client):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    entry["network"].MAX_MESSAGES = 0
    r = load(client, s, "C1")
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["setup_failure"]["code"] == "message_not_scheduled"
    assert r["continuation"] is None and not r["snapshot"]["pending_messages"]
    assert node(r["snapshot"])["height"] == 1
    assert node(r["snapshot"], "Node-3")["height"] == 0


def test_loader_does_not_bypass_delivery_validation(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    def reject(message_id):
        return dict(code="rejected_block", message="fixture: validator rejects parent")
    monkeypatch.setattr(entry["network"], "deliver", reject)
    r = load(client, s, "C1")
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["setup_failure"]["code"] == "rejected_block"
    assert node(r["snapshot"], "Node-3")["height"] == 0
    assert r["continuation"] is None


@pytest.mark.parametrize("scenario", ["C1","C2","C3"])
def test_revision_ownership_empty_reset_and_other_lab_isolation(client, scenario):
    s = create(client)
    independent = create(client)
    other = TestClient(wallet_api.app)
    try:
        foreign = other.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario=scenario))
        assert foreign.status_code == 404
    finally:
        other.close()
    s = action(client, s, "/links", changes=[dict(a="Node-1",b="Node-2",connected=False)])["snapshot"]
    stale = client.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario=scenario))
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_revision"
    r = load(client, s, scenario)
    assert r["outcome"]["code"] == "scenario_ready"
    s = r["snapshot"]
    before = copy.deepcopy(s)
    retry = client.post(route(s, "/scenario"), json=dict(expected_revision=s["revision"], scenario=scenario))
    assert retry.status_code == 409 and retry.json()["detail"]["code"] == "scenario_requires_empty"
    after = client.get(route(s)).json()
    assert after["revision"] == before["revision"] and after["nodes"] == before["nodes"]
    client.delete(route(s))
    assert client.get(route(s)).status_code == 404
    assert client.get(route(independent)).json()["nodes"] == independent["nodes"]
    assert load(client, create(client), scenario)["outcome"]["code"] == "scenario_ready"


@pytest.mark.parametrize("scenario", ["C1","C2","C3"])
@pytest.mark.parametrize("expire_at", [1, 2])
def test_expiry_during_mining_no_late_block_or_ready(client, monkeypatch, scenario, expire_at):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    real = wallet_api._mine_lab_block_bounded
    calls = []
    def expire(block):
        calls.append(block)
        result = real(block)
        if len(calls) == expire_at:
            entry["expires"] = time.monotonic() - 1
        return result
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", expire)
    response = client.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario=scenario))
    assert response.status_code == 404
    assert len(entry["network"].admitted_hashes()) == expire_at - 1
    assert entry["lab"].revision == 0
    assert all(n._publication_guard is None for n in entry["network"].nodes.values())
    assert not any(e["code"] == "scenario_ready" for e in entry["network"].events)
    assert client.get(route(s)).status_code == 404
    assert entry["network"].closed


def test_reset_during_loader_waits_then_removes_old_lab(client, monkeypatch):
    s = create(client)
    independent = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    entered, release, resetting = threading.Event(), threading.Event(), threading.Event()
    real = wallet_api._mine_lab_block_bounded
    def pause(block):
        entered.set()
        assert release.wait(5)
        return real(block)
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", pause)
    def reset():
        resetting.set()
        return client.delete(route(s))
    with ThreadPoolExecutor(max_workers=2) as pool:
        loading = pool.submit(client.post, route(s, "/scenario"), json=dict(expected_revision=0, scenario="C1"))
        assert entered.wait(5)
        deletion = pool.submit(reset)
        assert resetting.wait(5) and not deletion.done()
        release.set()
        assert loading.result(timeout=5).json()["outcome"]["code"] == "scenario_ready"
        assert deletion.result(timeout=5).json()["cleared"]
    assert entry["network"].closed and not entry["network"].pending
    assert client.get(route(s)).status_code == 404
    assert client.get(route(independent)).json()["nodes"] == independent["nodes"]


@pytest.mark.parametrize("scenario", ["C1", "C2", "C3"])
def test_winning_mine_failure_does_not_claim_ready(client, monkeypatch, scenario):
    real = wallet_api._mine_lab_block_bounded
    calls = []
    def fail_winner(block):
        calls.append(block)
        if len(calls) == 3:
            return dict(completed=False, reason="winner budget fixture", attempts=0, seconds=0)
        return real(block)
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", fail_winner)
    r = load(client, create(client), scenario)
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["setup_failure"]["code"] == "mining_incomplete" and r["continuation"] is None
    s = r["snapshot"]
    assert node(s)["credential_states"][r["credential_id"]]["confirmed_status"] == "REVOKED"
    assert node(s, "Node-3")["height"] == (0 if scenario == "C2" else 1)
    assert len([p for p in r["setup_completed_steps"] if p["operation"] == "mine"]) == 2
    assert not any(e["code"] == "scenario_ready" for e in s["events"])


def test_decisive_queue_capacity_failure_reports_actual_winning_branch(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    lab, network = entry["lab"], entry["network"]
    real = lab.mine
    calls = []
    def full_at_winner(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append(result)
        if len(calls) == 3:
            network.MAX_MESSAGES = 0
        return result
    monkeypatch.setattr(lab, "mine", full_at_winner)
    r = load(client, s, "C1")
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["setup_failure"]["code"] == "message_not_scheduled" and r["continuation"] is None
    assert len(r["snapshot"]["pending_messages"]) == 0
    assert node(r["snapshot"], "Node-3")["chain_work"] > node(r["snapshot"])["chain_work"]
    assert node(r["snapshot"])["credential_states"][r["credential_id"]]["confirmed_status"] == "REVOKED"
    assert len([p for p in r["setup_completed_steps"] if p["operation"] == "mine"]) == 3


def test_actual_candidate_validation_failure_is_reported(client, monkeypatch):
    real = wallet_api._mine_lab_block_bounded
    def tamper(block):
        result = real(block)
        block.transactions[0].payload["label"] = "changed after signing"
        return result
    monkeypatch.setattr(wallet_api, "_mine_lab_block_bounded", tamper)
    r = load(client, create(client), "C1")
    assert r["outcome"]["code"] == "scenario_incomplete"
    assert r["setup_failure"]["code"] == "candidate_rejected"
    assert r["setup_failure"]["mining"]["completed"]
    assert r["continuation"] is None
    assert all(n["height"] == 0 for n in r["snapshot"]["nodes"])
    assert not any(p["operation"] == "mine" for p in r["setup_completed_steps"])
    assert node(r["snapshot"])["mempool"][0]["payload"]["label"] != "changed after signing"


@pytest.mark.parametrize("target", ["Node-1", "Node-3"])
def test_expiry_during_real_candidate_validation_cannot_publish(client, monkeypatch, target):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    n = entry["network"].nodes[target]
    real = n._validate_candidate
    def expire(block):
        result = real(block)
        assert result[0]
        entry["expires"] = time.monotonic() - 1
        return result
    monkeypatch.setattr(n, "_validate_candidate", expire)
    response = client.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario="C1"))
    assert response.status_code == 404
    assert n.height == 0 and n.state_revision == 0
    assert all(n._publication_guard is None for n in entry["network"].nodes.values())
    assert not n.last_transition
    assert len(n.blockchain.block_pool) == 1
    assert not any(e["code"] == "scenario_ready" for e in entry["network"].events)


def test_expiry_during_reconciliation_cannot_publish(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    n = entry["network"].nodes["Node-3"]
    real = n.mempool.plan_reconciliation
    def expire(*args, **kwargs):
        result = real(*args, **kwargs)
        entry["expires"] = time.monotonic() - 1
        return result
    monkeypatch.setattr(n.mempool, "plan_reconciliation", expire)
    response = client.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario="C1"))
    assert response.status_code == 404
    assert n.height == 0 and n.state_revision == 0 and not n.last_transition
    assert len(n.blockchain.block_pool) == 1 and not n.mempool.get_transactions()


def test_expiry_during_relay_admission_cannot_publish(client, monkeypatch):
    s = create(client)
    entry = context(client).lab_networks[s["lab_handle"]]
    n = entry["network"].nodes["Node-3"]
    real = n.mempool.add_transaction
    def expire(*args, **kwargs):
        entry["expires"] = time.monotonic() - 1
        return real(*args, **kwargs)
    monkeypatch.setattr(n.mempool, "add_transaction", expire)
    response = client.post(route(s, "/scenario"), json=dict(expected_revision=0, scenario="C3"))
    assert response.status_code == 404
    assert n.blockchain.credential_status(next(iter(entry["lab"].transactions.values())).payload["credential_id"]) == "ACTIVE"
    revoke = next(tx for tx in entry["lab"].transactions.values() if tx.tx_type == "REVOKE")
    assert not n.mempool.get_transactions() and revoke.tx_id not in n._seen_tx_ids
