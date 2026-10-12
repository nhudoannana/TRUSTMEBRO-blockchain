"""Queue-only T2: whole-pool reconciliation and atomic publication."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from blockchain.blockchain import Blockchain
from blockchain.mempool import Mempool
from blockchain.node import Message
from blockchain.transaction import Transaction
from blockchain.wallet import generate_wallet
from tests.test_fork_selection_t1 import node, mined, receive, sync


def tx(owner, credential, kind="ISSUE"):
    result = Transaction(kind, owner.public_key_hex, {"credential_id": credential})
    result.sign(owner)
    return result


def ledger(txs=(), difficulty=1, label="ledger"):
    bc = Blockchain()
    bc.add_block(mined(bc.chain[0], difficulty, label, txs))
    assert bc.is_chain_valid()[0]
    return bc


def ids(txs):
    return [item.tx_id for item in txs]


def state(node):
    bc = node.blockchain
    return copy.deepcopy({
        "chain": [(b.to_dict(), [t.to_dict() for t in b.transactions]) for b in bc.chain],
        "branches": [[b.compute_hash() for b in branch] for branch in bc.side_branches],
        "index": {key: (b.to_dict(), [t.to_dict() for t in b.transactions])
                  for key, b in bc.block_pool.items()},
        "pool": [t.to_dict() for t in node.mempool.get_transactions()],
        "seen": sorted(node._seen_tx_ids),
        "report": getattr(node, "last_transition", None),
        "revision": getattr(node, "state_revision", None),
    })


def records(node):
    return {item["tx_id"]: item for item in node.last_transition["transactions"]}


@pytest.mark.parametrize("route", ["block", "sync"])
def test_retained_conflict_removed_and_independent_remainder_mines(node, route):
    owner = generate_wallet()
    conflict, independent = tx(owner, "C"), tx(owner, "D")
    assert node.submit_transaction(conflict)[0]
    assert node.submit_transaction(independent)[0]
    peer = ledger([tx(owner, "C")], label="peer")
    if route == "block":
        receive(node, peer.chain[-1])
    else:
        sync(node, peer)
    assert ids(node.mempool.get_transactions()) == [independent.tx_id]
    assert records(node)[conflict.tx_id]["reason_code"] == "credential_exists"
    assert records(node)[independent.tx_id]["reason_code"] == "accepted_retained"
    assert conflict.tx_id not in node._seen_tx_ids
    assert node.mine_pending(difficulty=1)[0] is not None


@pytest.mark.parametrize("consensus", ["pow", "pos"])
def test_successful_local_production_reconciles_unselected_pool(node, consensus):
    owner = generate_wallet()
    included, conflict, independent = tx(owner, "C"), tx(owner, "C"), tx(owner, "D")
    for item in (included, conflict, independent):
        assert node.mempool.add_transaction(item, node.blockchain)[0]
    if consensus == "pow":
        result = node.mine_pending(max_txs=1, difficulty=1)
    else:
        result = node.forge_pos_pending(max_txs=1)
    assert result[0] is not None
    assert ids(node.mempool.get_transactions()) == [independent.tx_id]
    assert records(node)[included.tx_id]["reason_code"] == "confirmed_on_new_chain"
    assert records(node)[conflict.tx_id]["reason_code"] == "credential_exists"


@pytest.mark.parametrize("route", ["fork", "sync"])
def test_restored_count_is_actual_not_attempted(node, route):
    owner, other = generate_wallet(), generate_wallet()
    old_conflict, detached_ok, retained = tx(owner, "C"), tx(owner, "D"), tx(owner, "E")
    old = ledger([old_conflict, detached_ok], label="old")
    receive(node, old.chain[-1])
    assert node.mempool.add_transaction(retained, node.blockchain)[0]
    new = ledger([tx(other, "C")], 2, "new")
    if route == "fork":
        receive(node, new.chain[-1])
    else:
        sync(node, new)
    report = node.last_transition
    assert report["counts"] == dict(candidates=3, retained=1, restored=1,
                                    rejected=1, confirmed=0, duplicates=0)
    assert ids(node.mempool.get_transactions()) == [retained.tx_id, detached_ok.tx_id]
    assert records(node)[old_conflict.tx_id]["reason_code"] == "credential_exists"
    assert records(node)[detached_ok.tx_id]["reason_code"] == "accepted_detached"
    assert node.blockchain.credential_issuer("C") == other.public_key_hex
    assert node.blockchain.credential_status("D") is None
    assert any("hoàn trả 1 TX" in event for event in node.network.get_event_log(100))
    assert any("từ chối 1 TX" in event for event in node.network.get_event_log(100))
    assert node.mine_pending(difficulty=1)[0] is not None
    assert node.blockchain.credential_status("D") == "ACTIVE"


def test_detached_revoke_uses_confirmed_state_not_pending_issue(node):
    owner = generate_wallet()
    issue, revoke = tx(owner, "C"), tx(owner, "C", "REVOKE")
    old = ledger([issue, revoke], label="issue-revoke")
    receive(node, old.chain[-1])
    assert node.blockchain.credential_status("C") == "REVOKED"
    new = ledger([], 2, "empty-stronger")
    sync(node, new)
    assert node.blockchain.credential_status("C") is None
    assert ids(node.mempool.get_transactions()) == [issue.tx_id]
    assert records(node)[revoke.tx_id]["reason_code"] == "not_active_on_chain"
    assert node.last_transition["counts"]["restored"] == 1


def test_revoke_rollback_restores_active_then_revoke_can_mine(node):
    owner = generate_wallet()
    issue, revoke = tx(owner, "C"), tx(owner, "C", "REVOKE")
    old = ledger([issue], label="issued")
    old.add_block(mined(old.chain[-1], 1, "revoked", [revoke]))
    sync(node, old)
    assert node.blockchain.credential_status("C") == "REVOKED"
    new = ledger([issue], 2, "issued-stronger")
    sync(node, new)
    assert node.blockchain.credential_status("C") == "ACTIVE"
    assert ids(node.mempool.get_transactions()) == [revoke.tx_id]
    assert node.mine_pending(difficulty=1)[0] is not None
    assert node.blockchain.credential_status("C") == "REVOKED"


def test_shared_confirmed_transaction_is_reported_not_restored(node):
    owner = generate_wallet()
    shared, detached = tx(owner, "C"), tx(owner, "D")
    old = ledger([shared, detached], label="old")
    receive(node, old.chain[-1])
    sync(node, ledger([shared], 2, "new"))
    assert ids(node.mempool.get_transactions()) == [detached.tx_id]
    assert records(node)[shared.tx_id]["reason_code"] == "confirmed_on_new_chain"
    assert node.last_transition["counts"]["confirmed"] == 1
    assert node.last_transition["counts"]["restored"] == 1


def test_reconciliation_plan_is_pure_fifo_and_deduplicates_sources():
    owner = generate_wallet()
    first, conflict, independent = tx(owner, "C"), tx(owner, "C"), tx(owner, "D")
    pool = Mempool()
    bc = Blockchain()
    for item in (first, conflict, independent):
        assert pool.add_transaction(item, bc)[0]
    before = [t.to_dict() for t in pool.get_transactions()]
    candidates = [{"transaction": item, "origin": "retained"} for item in pool.get_transactions()]
    candidates += [{"transaction": first, "origin": "detached"}]
    plan = pool.plan_reconciliation(bc, candidates, set())
    assert ids(plan["pending"]) == [first.tx_id, independent.tx_id]
    assert [t.to_dict() for t in pool.get_transactions()] == before
    assert plan["counts"] == dict(candidates=3, retained=2, restored=0,
                                 rejected=1, confirmed=0, duplicates=1)
    by_id = {item["tx_id"]: item for item in plan["transactions"]}
    assert by_id[first.tx_id]["origins"] == ["retained", "detached"]
    assert by_id[first.tx_id]["duplicate_reason_code"] == "duplicate_candidate"
    assert by_id[conflict.tx_id]["reason_code"] == "pending_conflict"


def test_reorg_plan_is_pure_and_legacy_reorganize_return_is_preserved():
    owner = generate_wallet()
    shared, detached = tx(owner, "C"), tx(owner, "D")
    old = ledger([shared, detached], label="old")
    new = ledger([shared], 2, "new")
    before_chain, before_pool, before_branches = list(old.chain), dict(old.block_pool), list(old.side_branches)
    plan = old.plan_reorg(new.chain)
    assert old.chain == before_chain and old.block_pool == before_pool and old.side_branches == before_branches
    assert plan["common_ancestor"] == dict(hash=old.chain[0].compute_hash(), height=0)
    assert ids(plan["detached_transactions"]) == [shared.tx_id, detached.tx_id]
    assert plan["detached_blocks"] == [old.chain[-1]]
    assert plan["attached_blocks"] == [new.chain[-1]]
    reverted, blocks = old.reorganize(new.chain)
    assert ids(reverted) == [detached.tx_id]
    assert blocks == plan["detached_blocks"]


@pytest.mark.parametrize("kind,code", [
    ("hash", "invalid_tx_hash"), ("signature", "invalid_signature"),
    ("issuer", "unauthorized_issuer"), ("revoke", "not_active_on_chain"),
    ("wrong_issuer", "wrong_issuer"), ("credential", "invalid_credential_id"),
    ("type", "invalid_tx_type"), ("payload", "invalid_payload"),
])
def test_reconciliation_reports_stable_validator_reason(kind, code):
    owner, other = generate_wallet(), generate_wallet()
    bc = ledger([tx(owner, "ACTIVE")], label="confirmed")
    item = tx(owner, "NEW")
    authorized = {owner.public_key_hex, other.public_key_hex}
    if kind == "hash":
        item.payload["changed"] = True
    elif kind == "signature":
        item.signature = "fake"
    elif kind == "issuer":
        authorized = {other.public_key_hex}
    elif kind == "revoke":
        item = tx(owner, "absent", "REVOKE")
    elif kind == "wrong_issuer":
        item = tx(other, "ACTIVE", "REVOKE")
    elif kind == "credential":
        item.payload = {"other": "missing credential"}
        item.sign(owner)
    elif kind == "type":
        item.tx_type = "UNKNOWN"
        item.sign(owner)
    elif kind == "payload":
        item.payload = ["invalid shape"]
        item.sign(owner)
    pool = Mempool(authorized)
    plan = pool.plan_reconciliation(bc, [{"transaction": item, "origin": "detached"}], set())
    assert not plan["pending"]
    assert plan["transactions"][0]["reason_code"] == code
    assert plan["counts"]["rejected"] == 1 and plan["counts"]["restored"] == 0


@pytest.mark.parametrize("route", ["extension", "fork", "sync", "pow", "pos"])
@pytest.mark.parametrize("planner", ["reorg", "pool"])
def test_preparation_failure_leaves_every_published_field_unchanged(node, monkeypatch, route, planner):
    owner = generate_wallet()
    receive(node, ledger([], label="old").chain[-1])
    pending = tx(owner, "C")
    assert node.submit_transaction(pending)[0]
    alternative = ledger([tx(owner, "C")], 2, "fork")
    extension = mined(node.blockchain.chain[-1], 1, "extension", [pending])
    before = state(node)
    bc_identity, pool_identity = id(node.blockchain), id(node.mempool)
    def fail(*args, **kwargs):
        raise RuntimeError("fixture: preparation failed")
    if planner == "pool":
        monkeypatch.setattr(Mempool, "plan_reconciliation", fail, raising=False)
    else:
        monkeypatch.setattr(Blockchain, "plan_reorg", fail, raising=False)
    with pytest.raises(RuntimeError, match="preparation failed"):
        if route == "extension":
            receive(node, extension)
        elif route == "fork":
            receive(node, alternative.chain[-1])
        elif route == "sync":
            sync(node, alternative)
        elif route == "pow":
            node.mine_pending(max_txs=1, difficulty=1)
        else:
            node.forge_pos_pending(max_txs=1)
    assert state(node) == before
    assert id(node.blockchain) == bc_identity and id(node.mempool) == pool_identity


def test_locked_observer_sees_chain_pool_ledger_and_report_together(node, monkeypatch):
    owner = generate_wallet()
    conflict, independent = tx(owner, "C"), tx(owner, "D")
    for item in (conflict, independent):
        assert node.submit_transaction(item)[0]
    incoming = ledger([tx(owner, "C")], label="incoming")
    entered, release, observed = threading.Event(), threading.Event(), threading.Event()
    original = getattr(node.mempool, "plan_reconciliation", None)
    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(node.mempool, "plan_reconciliation", paused, raising=False)
    def observe():
        with node._state_lock:
            result = (node.height, ids(node.mempool.get_transactions()),
                      node.blockchain.credential_status("C"), node.state_revision,
                      node.last_transition["new_tip"])
            observed.set()
            return result
    with ThreadPoolExecutor(max_workers=2) as workers:
        applying = workers.submit(receive, node, incoming.chain[-1])
        try:
            assert entered.wait(2)
            inspecting = workers.submit(observe)
            assert not observed.wait(.1)
            release.set()
            applying.result(timeout=5)
            result = inspecting.result(timeout=5)
        finally:
            release.set()
    assert result == (1, [independent.tx_id], "ACTIVE", 1, incoming.chain[-1].compute_hash())


def test_removed_seen_id_allows_later_valid_resubmission(node):
    owner = generate_wallet()
    original = tx(owner, "C")
    node._handle_message(Message("TX", "peer", copy.deepcopy(original)))
    assert original.tx_id in node._seen_tx_ids
    receive(node, ledger([tx(owner, "C")], label="confirmed-conflict").chain[-1])
    assert original.tx_id not in ids(node.mempool.get_transactions())
    sync(node, ledger([], 2, "rollback"))
    assert node.blockchain.credential_status("C") is None
    node._handle_message(Message("TX", "peer", copy.deepcopy(original)))
    assert original.tx_id in ids(node.mempool.get_transactions())


def test_noop_sync_and_side_storage_keep_pending_raw_conflicts(node):
    owner = generate_wallet()
    current = ledger([], 2, "current")
    sync(node, current)
    first, second = tx(owner, "C"), tx(owner, "C")
    for item in (first, second):
        assert node.mempool.add_transaction(item, node.blockchain)[0]
    receive(node, ledger([], 1, "lower-side").chain[-1])
    sync(node, current)
    assert ids(node.mempool.get_transactions()) == [first.tx_id, second.tx_id]


def test_real_queue_worker_reconciles_after_delivery(node):
    import time
    peer = node.network.create_node("worker", "127.0.0.1", 5002)
    owner = generate_wallet()
    conflict, independent = tx(owner, "C"), tx(owner, "D")
    for item in (conflict, independent):
        assert peer.mempool.add_transaction(item, peer.blockchain)[0]
    incoming = ledger([tx(owner, "C")], label="real-queue")
    assert node.network.send("peer", "worker", Message("BLOCK", "peer", incoming.chain[-1]))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with peer._state_lock:
            if peer.height == 1 and ids(peer.mempool.get_transactions()) == [independent.tx_id]:
                assert peer.last_transition["counts"]["rejected"] == 1
                return
        time.sleep(.01)
    pytest.fail("Real queue delivery did not reconcile retained conflict")


def test_empty_invalid_current_sync_recovers(node):
    node.blockchain.chain = []
    peer = ledger([], 1, "empty-current-recovery")
    sync(node, peer)
    assert node.blockchain.is_chain_valid()[0]
    assert node.last_transition["old_tip"] is None
    assert node.last_transition["new_tip"] == peer.chain[-1].compute_hash()
