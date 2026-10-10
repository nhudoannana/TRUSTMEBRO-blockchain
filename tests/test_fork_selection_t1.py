"""Phase 2 T1: real mined branch admission, storage and selection regressions."""
import copy

import pytest

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.mining import mine_block
from blockchain.node import Message, Network
from blockchain.transaction import Transaction
from blockchain.wallet import generate_wallet


def mined(parent, difficulty=1, label="branch", transactions=()):
    block = Block(list(transactions), parent.height + 1, parent.compute_hash(),
                  difficulty=difficulty, timestamp=label)
    mine_block(block)
    return block


def chain(difficulties, label):
    bc = Blockchain()
    for i, difficulty in enumerate(difficulties):
        bc.add_block(mined(bc.get_latest_block(), difficulty, f"{label}-{i}"))
    assert bc.is_chain_valid()[0]
    return bc


@pytest.fixture
def node():
    net = Network()
    result = net.create_node("N", "127.0.0.1", 5001)
    result.stop()
    yield result
    for peer in net.nodes.values():
        peer.stop()


def receive(node, block):
    node._handle_message(Message("BLOCK", "peer", copy.deepcopy(block)))


def sync(node, bc):
    node._handle_message(Message("SYNC_RESPONSE", "peer", copy.deepcopy(bc)))


def hashes(blocks):
    return [block.compute_hash() for block in blocks]


def snapshot(node):
    bc = node.blockchain
    return ([b.compute_hash() for b in bc.chain],
            [[b.compute_hash() for b in branch] for branch in bc.side_branches],
            set(bc.block_pool),
            [tx.tx_id for tx in node.mempool.get_transactions()])


def test_internal_side_parent_fanout_remains_selectable(node):
    genesis = node.blockchain.chain[0]
    a1 = mined(genesis, 2, "A1")
    b1 = mined(genesis, 1, "B1")
    b2 = mined(b1, 1, "B2")
    c2 = mined(b1, 3, "C2")
    for block in (a1, b1, b2):
        receive(node, block)
    assert node.blockchain.get_latest_block().compute_hash() == a1.compute_hash()
    receive(node, c2)
    assert node.blockchain.get_latest_block().compute_hash() == c2.compute_hash()
    assert node.blockchain.total_work() == 4112
    assert node.blockchain.is_chain_valid()[0]
    assert hashes(node.blockchain.branch_to_tip(b2.compute_hash())) == hashes([genesis, b1, b2])
    assert any(branch[-1].compute_hash() == b2.compute_hash()
               for branch in node.blockchain.side_branches)


def test_duplicate_side_block_does_not_duplicate_archive(node):
    genesis = node.blockchain.chain[0]
    receive(node, mined(genesis, 2, "A"))
    side = mined(genesis, 1, "B")
    receive(node, side)
    before = snapshot(node)
    receive(node, side)
    assert snapshot(node) == before


@pytest.mark.parametrize("route", ["block", "sync"])
def test_validated_shorter_higher_work_is_actually_adopted(node, route):
    current = chain([2, 2, 2], "long")
    stronger = chain([3], "short")
    sync(node, current)
    assert node.height == 3 and node.blockchain.total_work() == 768
    if route == "block":
        receive(node, stronger.chain[-1])
    else:
        sync(node, stronger)
    assert node.height == 1 and node.blockchain.total_work() == 4096
    assert node.blockchain.get_latest_block().compute_hash() == stronger.chain[-1].compute_hash()
    assert node.blockchain.is_chain_valid()[0]


@pytest.mark.parametrize("route", ["block", "sync"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("different_height", [False, True])
def test_equal_work_keeps_valid_current(node, route, reverse, different_height):
    left = chain([2] if different_height else [1], "left")
    right = chain([1] * 16 if different_height else [1], "right")
    current, alternative = (right, left) if reverse else (left, right)
    sync(node, current)
    original = node.blockchain.get_latest_block().compute_hash()
    if route == "sync":
        sync(node, alternative)
    else:
        for block in alternative.chain[1:]:
            receive(node, block)
    assert node.blockchain.get_latest_block().compute_hash() == original
    assert node.blockchain.is_chain_valid()[0]
    assert hashes(node.blockchain.branch_to_tip(alternative.chain[-1].compute_hash())) == hashes(alternative.chain)


@pytest.mark.parametrize("route", ["block", "sync"])
@pytest.mark.parametrize("equal_work", [False, True])
def test_valid_branch_recovers_invalid_current_without_score_threshold(node, route, equal_work):
    node.blockchain = chain([2], "corrupt")
    node.blockchain.chain[-1].header.merkle_root = "f" * 64
    assert not node.blockchain.is_chain_valid()[0]
    valid = chain([2] if equal_work else [1], "recovery")
    if route == "block":
        receive(node, valid.chain[-1])
    else:
        sync(node, valid)
    assert node.blockchain.get_latest_block().compute_hash() == valid.chain[-1].compute_hash()
    assert node.blockchain.is_chain_valid()[0]


@pytest.mark.parametrize("route", ["block", "sync"])
@pytest.mark.parametrize("kind", ["merkle", "signature", "replay", "issuer", "ledger", "genesis", "height"])
def test_invalid_higher_work_candidate_changes_no_chain_pool_or_archive(node, route, kind):
    receive(node, chain([1], "current").chain[-1])
    owner, stranger = generate_wallet(), generate_wallet()
    node.mempool.authorized_issuers = {owner.public_key_hex}
    issue = Transaction("ISSUE", owner.public_key_hex, {"credential_id": "C"})
    issue.sign(owner)
    txs = [issue]
    if kind == "signature":
        issue.signature = "fake"
    elif kind == "replay":
        txs = [issue, issue]
    elif kind == "issuer":
        issue = Transaction("ISSUE", stranger.public_key_hex, {"credential_id": "C"})
        issue.sign(stranger)
        txs = [issue]
    elif kind == "ledger":
        revoke = Transaction("REVOKE", owner.public_key_hex, {"credential_id": "missing"})
        revoke.sign(owner)
        txs = [revoke]
    candidate = Blockchain()
    if kind == "genesis":
        candidate.chain[0].header.timestamp = "foreign genesis"
    bad = mined(candidate.chain[0], 2, "invalid", txs)
    if kind == "merkle":
        bad.header.merkle_root = "f" * 64
        mine_block(bad)
    elif kind == "height":
        bad.height += 1
        mine_block(bad)
    candidate.add_block(bad)
    assert not candidate.is_chain_valid(authorized_issuers={owner.public_key_hex})[0]
    before = snapshot(node)
    if route == "block":
        receive(node, bad)
    else:
        sync(node, candidate)
    assert snapshot(node) == before


def test_parent_prefix_resolves_active_and_internal_side_paths(node):
    genesis = node.blockchain.chain[0]
    a1, b1 = mined(genesis, 2, "A"), mined(genesis, 1, "B")
    b2 = mined(b1, 1, "B2")
    for block in (a1, b1, b2):
        receive(node, block)
    assert hashes(node.blockchain.branch_to_tip(a1.compute_hash())) == hashes([genesis, a1])
    assert hashes(node.blockchain.branch_to_tip(b1.compute_hash())) == hashes([genesis, b1])
    assert hashes(node.blockchain.branch_to_tip(b2.compute_hash())) == hashes([genesis, b1, b2])


@pytest.mark.parametrize("damage", ["missing", "height", "foreign_genesis", "cycle"])
def test_parent_resolution_rejects_broken_paths(damage, monkeypatch):
    bc = chain([1, 1], "path")
    tip_hash = bc.chain[-1].compute_hash()
    if damage == "missing":
        del bc.block_pool[bc.chain[1].compute_hash()]
    elif damage == "height":
        bc.chain[1].height = 9
    elif damage == "foreign_genesis":
        bc.chain[0].header.timestamp = "wrong genesis"
    else:
        # A corrupt index cycle cannot be made by honest mining; isolate resolver.
        tip = bc.chain[-1]
        tip.header.previous_hash = tip_hash
        monkeypatch.setattr(tip, "compute_hash", lambda: tip_hash)
    assert bc.branch_to_tip(tip_hash) is None
    assert bc.branch_to_tip("unknown") is None


def test_unknown_parent_storage_does_not_admit_block():
    bc = Blockchain()
    missing_parent = mined(bc.chain[0], 1, "not stored")
    child = mined(missing_parent, 1, "unknown parent child")
    before = set(bc.block_pool)
    ok, _, candidate = bc.add_side_branch_block(child)
    assert not ok and candidate is None
    assert set(bc.block_pool) == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("different_height", [False, True])
def test_legacy_coordinator_keeps_height_then_insertion_tie_policy(node, reverse, different_height):
    net = node.network
    node.stop()
    del net.nodes[node.node_id]
    left = chain([2] if different_height else [1], "left")
    right = chain([1] * 16 if different_height else [1], "right")
    choices = [("Z-first", left), ("A-second", right)]
    if reverse:
        choices.reverse()
    peers = []
    for name, bc in choices:
        peer = net.create_node(name, "127.0.0.1", 5001 + len(peers))
        peer.stop()
        peer.blockchain = bc
        peers.append(peer)
    expected = right.chain[-1].compute_hash() if different_height else choices[0][1].chain[-1].compute_hash()
    net.sync_all_nodes()
    assert all(peer.blockchain.get_latest_block().compute_hash() == expected for peer in peers)

@pytest.mark.parametrize("route", ["block", "sync"])
def test_invalid_current_recovers_best_already_known_valid_branch(node, route):
    genesis = node.blockchain.chain[0]
    current = mined(genesis, 3, "current")
    stronger_side = mined(genesis, 2, "stronger-side")
    new_side = mined(genesis, 1, "new-side")
    receive(node, current)
    receive(node, stronger_side)
    node.blockchain.chain[-1].header.merkle_root = "f" * 64
    if route == "block":
        receive(node, new_side)
    else:
        peer = Blockchain()
        peer.add_block(new_side)
        sync(node, peer)
    assert node.blockchain.get_latest_block().compute_hash() == stronger_side.compute_hash()
    assert node.blockchain.is_chain_valid()[0]

def test_sync_recovery_retains_received_branch_for_later_descendants(node):
    genesis = node.blockchain.chain[0]
    current = mined(genesis, 3, "current")
    stronger_side = mined(genesis, 2, "stronger-side")
    peer_parent = mined(genesis, 1, "peer-parent")
    receive(node, current)
    receive(node, stronger_side)
    node.blockchain.chain[-1].header.merkle_root = "f" * 64
    peer = Blockchain()
    peer.add_block(peer_parent)
    sync(node, peer)
    assert node.blockchain.get_latest_block().compute_hash() == stronger_side.compute_hash()
    assert peer_parent.compute_hash() in node.blockchain.block_pool
    child = mined(peer_parent, 3, "peer-child")
    receive(node, child)
    assert node.blockchain.get_latest_block().compute_hash() == child.compute_hash()
    assert node.blockchain.is_chain_valid()[0]


def test_valid_duplicate_repairs_invalid_stored_body(node):
    owner = generate_wallet()
    tx = Transaction("ISSUE", owner.public_key_hex, {"credential_id": "repair"})
    tx.sign(owner)
    good = mined(node.blockchain.chain[0], 1, "repair-body", [tx])
    receive(node, good)
    node.blockchain.chain[-1].transactions[0].signature = "fake"
    assert not node.blockchain.is_chain_valid()[0]
    receive(node, good)
    assert node.blockchain.is_chain_valid()[0]
    assert node.blockchain.credential_status("repair") == "ACTIVE"
