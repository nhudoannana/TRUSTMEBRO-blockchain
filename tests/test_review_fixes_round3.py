"""Regression coverage for signed heights and fail-closed PoS verification."""

import pytest

from blockchain.blockchain import Blockchain, verify_pos_signature
from blockchain.node import Network, Message
from blockchain.pos import create_trustprofile_consortium
from tests.test_review_fixes_round2 import _issue_with_claims


def test_height_tampering_cannot_frame_an_honest_validator():
    reg = create_trustprofile_consortium()
    validator = next(iter(reg.validators.values()))
    first = reg.forge_block(validator, [], 1, "parent-a")
    second = reg.forge_block(validator, [], 2, "parent-b")
    stake = validator.stake
    assert not reg.detect_and_slash(first, second)[0]
    second.height = 1
    assert not verify_pos_signature(second, reg)[0]
    assert not reg.detect_and_slash(first, second)[0]
    assert validator.stake == stake


@pytest.mark.parametrize("forged", [False, True])
def test_pos_verification_requires_registry(forged):
    bc, tx, salts, proofs = _issue_with_claims({"grade": "A"})
    reg = create_trustprofile_consortium()
    validator = next(iter(reg.validators.values()))
    bc.chain[1] = reg.forge_block(validator, [tx], 1, bc.chain[0].compute_hash())
    if forged:
        bc.chain[1].header.validator_signature = "fake-signature"
    assert not bc.is_chain_valid()[0]
    assert bc.verify_credential("CRED-RF2-001")[1] == "INVALID"
    assert not bc.verify_selective_claim(
        "CRED-RF2-001", "grade", "A", salts["grade"], proofs["grade"]
    )[0]
    assert bc.is_chain_valid(pos_registry=reg)[0] is (not forged)
    assert bc.verify_selective_claim(
        "CRED-RF2-001", "grade", "A", salts["grade"], proofs["grade"],
        pos_registry=reg,
    )[0] is (not forged)


@pytest.mark.parametrize("fork", [False, True])
def test_correctly_signed_wrong_height_rejected_by_chain_node_and_sync(fork):
    net = Network()
    try:
        node = net.create_node("N", "127.0.0.1", 5001)
        bc = Blockchain()
        parent = bc.get_latest_block().compute_hash()
        reg = net.pos_registry
        validator = reg.select_validator(9, seed=net.consensus_seed, previous_hash=parent)
        if fork:
            proposer = reg.select_validator(1, seed=net.consensus_seed, previous_hash=parent)
            node.blockchain.add_block(reg.forge_block(proposer, [], 1, parent))
        old_height = node.height
        block = reg.forge_block(validator, [], 9, parent)
        assert verify_pos_signature(block, reg)[0]
        bc.add_block(block)
        assert not bc.is_chain_valid(pos_registry=reg)[0]
        node._handle_block(Message("BLOCK", "peer", block))
        assert node.height == old_height
        assert not node.blockchain.side_branches
        node._handle_sync_response(Message("SYNC_RESPONSE", "peer", bc))
        assert node.height == old_height
    finally:
        for node in net.nodes.values():
            node._running = False
