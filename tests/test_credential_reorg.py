"""Queue validator fixture keys: authorization is not signature validity."""
import copy
import time
import pytest
from api.fork_lab import ForkLab
from blockchain.transaction import Transaction
from blockchain.wallet import generate_wallet


def mine(lab, key, txs=(), difficulty=1):
    n = lab.network.nodes[key]
    r = lab.mine(key, n.blockchain.chain[-1].compute_hash(), difficulty,
                 [t.tx_id for t in txs], {"expires": time.monotonic()+60})
    assert r["code"] == "accepted_block", r
    return r


def test_real_wrong_issuer_and_tampering_do_not_publish():
    lab = ForkLab()
    try:
        issue = lab.credential_transaction("Node-1", "ISSUE", "cert-A", "A")
        mine(lab, "Node-1", [issue])
        n = lab.network.nodes["Node-1"]
        other = generate_wallet()
        # Independently authorized fixture key, not a global permission expansion.
        n.mempool.authorized_issuers.add(other.public_key_hex)
        wrong = Transaction("REVOKE", other.public_key_hex, {"credential_id": "cert-A", "reason": "r"})
        wrong.sign(other)
        bad_sig = copy.deepcopy(wrong)
        bad_sig.sender_public_key = lab.issuer.public_key_hex
        bad_sig.tx_id = bad_sig.compute_hash()
        edited = Transaction("REVOKE", lab.issuer.public_key_hex, {"credential_id": "cert-A", "reason": "r"})
        edited.sign(lab.issuer)
        edited.payload["reason"] = "changed"
        stranger = generate_wallet()
        unauthorized = Transaction("REVOKE", stranger.public_key_hex, {"credential_id": "cert-A"})
        unauthorized.sign(stranger)
        for tx, expected in ((wrong, "Issuer"), (bad_sig, "Ch"), (edited, "hash"), (unauthorized, "unauthorized")):
            pool, queue, revision = list(n.mempool.get_transactions()), list(lab.network.pending), n.state_revision
            ok, reason = n.submit_transaction(tx)
            assert not ok and expected in reason
            assert n.mempool.get_transactions() == pool and list(lab.network.pending) == queue
            assert n.state_revision == revision and n.blockchain.credential_status("cert-A") == "ACTIVE"
    finally:
        lab.network.close()


def test_detached_issue_revoke_revalidated_against_new_chain():
    lab = ForkLab()
    try:
        for a,b in (("Node-1","Node-2"), ("Node-1","Node-3"), ("Node-2","Node-3")):
            lab.network.set_link(a,b,False)
        issue = lab.credential_transaction("Node-1", "ISSUE", "cert-A", "A")
        mine(lab, "Node-1", [issue])
        revoke = lab.credential_transaction("Node-1", "REVOKE", "cert-A", "r")
        mine(lab, "Node-1", [revoke])
        mine(lab, "Node-3", difficulty=2)
        n = lab.network.nodes["Node-1"]
        branch = lab.network.nodes["Node-3"].blockchain.chain
        ok, _ = n._apply_valid_branch(branch, "test_sync")
        assert ok and n.blockchain.credential_status("cert-A") is None
        assert [t.tx_id for t in n.mempool.get_transactions()] == [issue.tx_id]
        report = n.last_transition
        assert report["counts"]["restored"] == 1
        records = {t["tx_id"]: t for t in report["transactions"]}
        assert records[issue.tx_id]["reason_code"] == "accepted_detached"
        assert records[revoke.tx_id]["reason_code"] == "not_active_on_chain"
    finally:
        lab.network.close()


@pytest.mark.parametrize("same_revoke", [False, True])
def test_revoke_after_reorg_with_common_issue(same_revoke):
    lab = ForkLab()
    try:
        for a,b in (("Node-1","Node-2"), ("Node-1","Node-3"), ("Node-2","Node-3")):
            lab.network.set_link(a,b,False)
        issue = lab.credential_transaction("Node-1", "ISSUE", "cert-A", "A")
        mine(lab, "Node-1", [issue])
        n = lab.network.nodes["Node-1"]
        peer = lab.network.nodes["Node-3"]
        assert peer._apply_valid_branch(n.blockchain.chain, "common_ancestor")[0]
        revoke = lab.credential_transaction("Node-1", "REVOKE", "cert-A", "r")
        mine(lab, "Node-1", [revoke])
        mine(lab, "Node-3", [revoke] if same_revoke else [], difficulty=2)
        assert n._apply_valid_branch(peer.blockchain.chain, "test_sync")[0]
        assert n.blockchain.credential_status("cert-A") == ("REVOKED" if same_revoke else "ACTIVE")
        assert n.last_transition["counts"]["restored"] == (0 if same_revoke else 1)
        assert [t.tx_id for t in n.mempool.get_transactions()] == ([] if same_revoke else [revoke.tx_id])
        record = next(t for t in n.last_transition["transactions"] if t["tx_id"] == revoke.tx_id)
        assert record["reason_code"] == ("confirmed_on_new_chain" if same_revoke else "accepted_detached")
    finally:
        lab.network.close()
