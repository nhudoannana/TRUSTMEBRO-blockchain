from blockchain.pos import create_trustprofile_consortium
from blockchain.wallet import generate_wallet
from blockchain.transaction import Transaction
from blockchain.blockchain import Blockchain
from tests.test_review_fixes_round4 import mined
from blockchain.node import Network
from tests.test_review_fixes import _issue_tx


def test_stake_cannot_be_credited_by_copying_institution_name():
    reg = create_trustprofile_consortium()
    validator = next(iter(reg.validators.values()))
    attacker = generate_wallet()
    tx = Transaction('ISSUE',attacker.public_key_hex,{'credential_id':'FAKE','issuer_name':validator.name})
    tx.sign(attacker)
    bc=Blockchain()
    bc.add_block(mined(bc,[tx]))
    reg.sync_with_blockchain(bc)
    assert validator.credentials_issued == 0


def test_local_pos_rejects_wrong_proposer():
    net=Network()
    node=net.create_node('N','127.0.0.1',5001)
    try:
        node.mempool.add_transaction(_issue_tx(),node.blockchain)
        parent=node.blockchain.get_latest_block().compute_hash()
        chosen=net.pos_registry.select_validator(1,seed=net.consensus_seed,previous_hash=parent)
        wrong=next(v for v in net.pos_registry.validators.values() if v.address != chosen.address)
        block, reason=node.forge_pos_pending(validator=wrong)
        assert block is None
        assert node.height == 0
    finally:
        node._running=False
