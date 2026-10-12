"""Controlled transport must obey partitions and real Node validation."""
import copy
import importlib.util

import pytest

from blockchain.node import Message, Network
from tests.test_fork_selection_t1 import mined


@pytest.fixture
def net():
    assert importlib.util.find_spec("blockchain.fork_transport"), "Controlled transport is missing"
    from blockchain.fork_transport import ControlledNetwork
    result = ControlledNetwork()
    for i in range(1, 4):
        result.create_node(f"Node-{i}", "local", 0)
    yield result
    result.close()


def test_manual_has_no_workers_and_automatic_network_still_delivers(net):
    assert all(not n._worker.is_alive() for n in net.nodes.values())
    automatic = Network()
    n = automatic.create_node("a", "local", 0)
    try:
        assert n._worker.is_alive()
        assert automatic.send("b", "a", Message("SYNC_REQUEST", "b", None))
    finally:
        n.stop()


@pytest.mark.parametrize("kind", ["TX", "BLOCK", "SYNC_REQUEST", "SYNC_RESPONSE"])
def test_partition_blocks_scheduling_and_existing_delivery(net, kind):
    payload = None
    if kind == "BLOCK":
        payload = mined(net.nodes["Node-1"].blockchain.chain[0], 1, "partition")
    elif kind == "SYNC_RESPONSE":
        payload = net.nodes["Node-1"].blockchain
    assert net.send("Node-1", "Node-2", Message(kind, "Node-1", payload))
    message_id = next(iter(net.pending))
    net.set_link("Node-1", "Node-2", False)
    assert not net.send("Node-1", "Node-2", Message(kind, "Node-1", payload))
    assert net.deliver(message_id)["code"] == "blocked"
    assert message_id in net.pending
    assert net.nodes["Node-2"].height == 0
    net.set_link("Node-1", "Node-2", True)
    if kind != "TX":
        assert net.deliver(message_id)["code"] != "blocked"


def test_child_before_parent_retries_then_suppresses_duplicates(net):
    genesis = net.nodes["Node-1"].blockchain.chain[0]
    parent = mined(genesis, 1, "parent")
    child = mined(parent, 2, "child")
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
    assert net.deliver(next(iter(net.pending)))["code"] == "orphan"
    receiver = net.nodes["Node-2"]
    assert receiver.height == 0 and len(net.orphans["Node-2"]) == 1
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", parent))
    assert net.deliver(next(iter(net.pending)))["code"] == "accepted_block"
    assert receiver.height == 2 and receiver.blockchain.total_work() == 272
    assert not net.orphans["Node-2"]
    assert not net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
    assert any(e["code"] == "orphan_retried" for e in net.events)


def test_invalid_parent_never_promotes_retained_child(net):
    parent = mined(net.nodes["Node-1"].blockchain.chain[0], 1, "invalid-parent")
    parent.header.merkle_root = "f" * 64
    from blockchain.mining import mine_block
    mine_block(parent)
    child = mined(parent, 3, "advertised-work")
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
    net.deliver(next(iter(net.pending)))
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", parent))
    candidates = [key for key, env in net.pending.items() if env["message"].msg_type == "BLOCK"]
    assert net.deliver(candidates[-1])["code"] == "rejected_block"
    receiver = net.nodes["Node-2"]
    assert receiver.height == 0
    assert child.compute_hash() not in receiver.blockchain.block_pool
    assert not net.orphans["Node-2"]
    assert any(e["code"] == "invalid_parent" for e in net.events)


def test_queue_capacity_discard_and_close_are_explicit(net, monkeypatch):
    monkeypatch.setattr(net, "MAX_MESSAGES", 1)
    assert net.send("Node-1", "Node-2", Message("SYNC_REQUEST", "Node-1", None))
    assert not net.send("Node-1", "Node-3", Message("SYNC_REQUEST", "Node-1", None))
    assert len(net.pending) == 1
    assert any(e["code"] == "message_capacity" for e in net.events)
    key = next(iter(net.pending))
    assert net.discard(key)["code"] == "discarded"
    assert not net.pending
    net.close()
    assert not net.send("Node-1", "Node-2", Message("SYNC_REQUEST", "Node-1", None))


def test_orphan_capacity_expiry_and_event_cursor(net, monkeypatch):
    import blockchain.fork_transport as transport
    monkeypatch.setattr(net, "MAX_ORPHANS", 1)
    now = [100.0]
    monkeypatch.setattr(transport.time, "monotonic", lambda: now[0])
    genesis = net.nodes["Node-1"].blockchain.chain[0]
    parent = mined(genesis, 1, "missing")
    for label in ("a", "b"):
        child = mined(parent, 1, label)
        net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
        result = net.deliver(next(iter(net.pending)))
    assert result["code"] == "orphan_capacity"
    assert len(net.orphans["Node-2"]) == 1
    now[0] += net.ORPHAN_TTL + 1
    net.expire_orphans()
    assert not net.orphans["Node-2"]
    assert any(e["code"] == "orphan_expired" for e in net.events)
    for i in range(205):
        net.log_event("test", str(i))
    assert len(net.events) == 200 and net.event_cursor > 200
    assert net.events_truncated


def test_context_invalid_parent_rejects_all_descendants_without_admission(net):
    from blockchain.transaction import Transaction
    from blockchain.wallet import generate_wallet
    owner = generate_wallet()
    parent_tx = Transaction("REVOKE", owner.public_key_hex, {"credential_id": "absent"})
    parent_tx.sign(owner)
    parent = mined(net.nodes["Node-1"].blockchain.chain[0], 1, "invalid-ledger", [parent_tx])
    child = mined(parent, 1, "child")
    grandchild = mined(child, 1, "grandchild")
    for block in (grandchild, child, parent):
        net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", block))
        ids = [k for k,e in net.pending.items() if e["to"] == "Node-2" and e["message"].msg_type == "BLOCK"]
        net.deliver(ids[-1])
    assert net.nodes["Node-2"].height == 0
    assert not net.orphans["Node-2"]


def test_sync_with_bad_merkle_parent_drops_unresolved_descendants(net):
    from blockchain.blockchain import Blockchain
    parent = mined(net.nodes["Node-1"].blockchain.chain[0], 1, "bad-parent")
    parent.header.merkle_root = "f"*64
    from blockchain.mining import mine_block
    mine_block(parent)
    child = mined(parent, 1, "child")
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
    net.deliver(next(iter(net.pending)))
    peer = Blockchain()
    peer.chain.append(parent)
    net.send("Node-1", "Node-2", Message("SYNC_RESPONSE", "Node-1", peer))
    response = next(k for k,e in net.pending.items() if e["message"].msg_type == "SYNC_RESPONSE")
    assert net.deliver(response)["code"] == "rejected_sync"
    assert net.nodes["Node-2"].height == 0
    # Invalid sync must not imply validating orphan context; retain explicit unresolved state.
    assert len(net.orphans["Node-2"]) == 1
    assert child.compute_hash() not in net.nodes["Node-2"].blockchain.block_pool


def test_sync_cannot_bypass_manual_partition_via_coordinator(net):
    parent = mined(net.nodes["Node-1"].blockchain.chain[0], 2, "isolated")
    net.nodes["Node-1"]._handle_message(Message("BLOCK", "Node-1", parent))
    net.set_link("Node-1", "Node-2", False)
    net.set_link("Node-1", "Node-3", False)
    with pytest.raises(ValueError, match="manual"):
        net.sync_all_nodes()
    assert net.nodes["Node-2"].height == 0 and net.nodes["Node-3"].height == 0


def test_closed_manual_network_cannot_register_or_deliver(net):
    net.send("Node-1", "Node-2", Message("SYNC_REQUEST", "Node-1", None))
    key = next(iter(net.pending))
    net.close()
    with pytest.raises(KeyError):
        net.deliver(key)
    with pytest.raises(ValueError):
        net.create_node("Node-4", "local", 0)


def test_envelope_is_deep_copied_and_pending_duplicates_do_not_consume_capacity(net):
    block = mined(net.nodes["Node-1"].blockchain.chain[0], 1, "original")
    ref = block.compute_hash()
    assert net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", block))
    assert not net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", block))
    assert len(net.pending) == 1
    block.header.merkle_root = "f"*64
    result = net.deliver(next(iter(net.pending)))
    assert result["code"] == "accepted_block"
    assert net.nodes["Node-2"].blockchain.chain[-1].compute_hash() == ref


def test_successful_peer_sync_retries_orphan_with_real_parent_chain(net):
    from blockchain.blockchain import Blockchain
    genesis = net.nodes["Node-1"].blockchain.chain[0]
    parent = mined(genesis, 1, "sync-parent")
    child = mined(parent, 2, "sync-child")
    net.send("Node-1", "Node-2", Message("BLOCK", "Node-1", child))
    net.deliver(next(iter(net.pending)))
    peer = Blockchain()
    peer.add_block(parent)
    net.send("Node-1", "Node-2", Message("SYNC_RESPONSE", "Node-1", peer))
    response = next(k for k,e in net.pending.items() if e["message"].msg_type == "SYNC_RESPONSE")
    assert net.deliver(response)["code"] == "sync_processed"
    assert net.nodes["Node-2"].height == 2 and net.nodes["Node-2"].blockchain.total_work() == 272
    assert not net.orphans["Node-2"]
