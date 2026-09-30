"""Regression tests for sync, ledger rules and PoS chain scoring."""
import pytest
from blockchain.block import Block
from blockchain.blockchain import Blockchain, calculate_chain_work
from blockchain.mining import mine_block
from blockchain.node import Network, Message
from blockchain.transaction import Transaction
from blockchain.wallet import generate_wallet, sign_message
from tests.test_review_fixes import _issue_tx


def mined(bc, txs=()):
    block = Block(list(txs), len(bc.chain), bc.get_latest_block().compute_hash(), difficulty=1)
    mine_block(block)
    return block


@pytest.fixture
def node():
    net = Network()
    node = net.create_node('N', '127.0.0.1', 5001)
    node._running = False
    yield node
    for n in net.nodes.values():
        n._running = False


def test_sync_then_accept_next_block(node):
    peer = Blockchain()
    peer.add_block(mined(peer))
    node._handle_sync_response(Message('SYNC_RESPONSE', 'peer', peer))
    assert node.height == 1
    node._handle_block(Message('BLOCK', 'peer', mined(peer)))
    assert node.height == 2


@pytest.mark.parametrize('route', ['sync', 'sync_all'])
def test_invalid_transaction_never_enters_via_sync(node, route):
    peer = Blockchain()
    tx = _issue_tx()
    tx.signature = 'fake'
    peer.add_block(mined(peer, [tx]))
    assert not peer.is_chain_valid()[0]
    if route == 'sync':
        node._handle_sync_response(Message('SYNC_RESPONSE', 'peer', peer))
    else:
        other = node.network.create_node('peer', '127.0.0.1', 5002)
        other._running = False
        other.blockchain = peer
        node.network.sync_all_nodes()
    assert node.height == 0


def invalid_transactions(kind):
    owner = generate_wallet()
    issuer = Transaction('ISSUE', owner.public_key_hex, {'credential_id': 'C'})
    issuer.sign(owner)
    stranger = generate_wallet()
    revoke = Transaction('REVOKE', stranger.public_key_hex, {'credential_id': 'C'})
    revoke.sign(stranger)
    if kind == 'wrong_revoke':
        return [issuer, revoke]
    if kind == 'missing_issue':
        return [revoke]
    if kind == 'replay':
        return [issuer, issuer]
    another = Transaction('ISSUE', stranger.public_key_hex, {'credential_id': 'C'})
    another.sign(stranger)
    return [issuer, another]


@pytest.mark.parametrize('kind', ['wrong_revoke', 'missing_issue', 'replay', 'duplicate_issue'])
@pytest.mark.parametrize('route', ['block', 'fork', 'sync'])
def test_ledger_rules_on_every_ingress(node, kind, route):
    peer = Blockchain()
    bad = mined(peer, invalid_transactions(kind))
    if route == 'fork':
        node.blockchain.add_block(mined(node.blockchain))
    original = node.blockchain.get_latest_block().compute_hash()
    if route == 'sync':
        peer.add_block(bad)
        node._handle_sync_response(Message('SYNC_RESPONSE', 'peer', peer))
    else:
        node._handle_block(Message('BLOCK', 'peer', bad))
    assert node.blockchain.get_latest_block().compute_hash() == original
    assert not node.blockchain.side_branches
    assert bad.compute_hash() not in node.blockchain.block_pool


def test_legitimate_issue_then_revoke_in_same_block(node):
    owner = generate_wallet()
    txs = []
    for kind in ['ISSUE', 'REVOKE']:
        tx = Transaction(kind, owner.public_key_hex, {'credential_id': 'C'})
        tx.sign(owner)
        txs.append(tx)
    node._handle_block(Message('BLOCK', 'peer', mined(node.blockchain, txs)))
    assert node.height == 1
    assert node.blockchain.credential_status('C') == 'REVOKED'


@pytest.mark.parametrize('field,value', [('difficulty',20), ('nonce',1)])
def test_pos_cannot_inflate_work_or_use_nonce(node, field, value):
    reg = node.network.pos_registry
    parent = node.blockchain.get_latest_block().compute_hash()
    validator = reg.select_validator(1, seed=42, previous_hash=parent)
    block = reg.forge_block(validator, [], 1, parent)
    setattr(block.header, field, value)
    block.header.validator_signature = sign_message(block.compute_hash(), validator.private_key_pem)
    assert calculate_chain_work([node.blockchain.chain[0], block]) == 1
    assert not reg.verify_pos_block(block, 1, 42, parent)[0]
    node._handle_block(Message('BLOCK', 'peer', block))
    assert node.height == 0
    peer = Blockchain()
    peer.add_block(block)
    assert not peer.is_chain_valid(pos_registry=reg)[0]
    node._handle_sync_response(Message('SYNC_RESPONSE','peer',peer))
    assert node.height == 0


@pytest.mark.parametrize('consensus',['pow','pos'])
def test_local_producer_rejects_conflicting_pending_transactions(node, consensus):
    for tx in invalid_transactions('duplicate_issue'):
        assert node.mempool.add_transaction(tx, node.blockchain)[0]
    if consensus == 'pow':
        result = node.mine_pending(difficulty=1)
    else:
        result = node.forge_pos_pending()
    assert result[0] is None
    assert node.height == 0
    assert len(node.mempool.get_transactions()) == 2


def test_fork_validates_its_own_ledger(node):
    # Same ID on two alternative branches is allowed, but not twice in one branch.
    main = mined(node.blockchain, [_issue_tx('C')])
    node.blockchain.add_block(main)
    fork = mined(Blockchain(), [_issue_tx('C')])
    node._handle_block(Message('BLOCK','peer',fork))
    assert len(node.blockchain.side_branches) == 1
    peer = Blockchain()
    peer.add_block(fork)
    next_block = mined(peer, [_issue_tx('D')])
    node._handle_block(Message('BLOCK','peer',next_block))
    assert node.blockchain.get_latest_block().compute_hash() == next_block.compute_hash()
    assert node.blockchain.is_chain_valid()[0]


def test_sync_all_recovers_invalid_node_and_clears_confirmed_mempool(node):
    good = node.network.create_node('good', '127.0.0.1', 5002)
    good._running = False
    tx = _issue_tx('GOOD')
    good.blockchain.add_block(mined(good.blockchain, [tx]))
    assert node.mempool.add_transaction(tx, node.blockchain)[0]
    for number in range(2):
        bad = _issue_tx(f'BAD-{number}')
        bad.signature = 'fake'
        node.blockchain.add_block(mined(node.blockchain, [bad]))
    node.network.sync_all_nodes()
    assert node.blockchain.get_latest_block().compute_hash() == good.blockchain.get_latest_block().compute_hash()
    assert not node.mempool.get_transactions()
    node._handle_block(Message('BLOCK', 'good', mined(good.blockchain)))
    assert node.height == 2


@pytest.mark.parametrize('route', ['block','fork','sync'])
def test_issuer_registry_enforced_on_ingress(node, route):
    node.mempool.authorized_issuers = {generate_wallet().public_key_hex}
    peer = Blockchain()
    bad = mined(peer, [_issue_tx()])
    if route == 'fork':
        node.blockchain.add_block(mined(node.blockchain))
    old_tip = node.blockchain.get_latest_block().compute_hash()
    if route == 'sync':
        peer.add_block(bad)
        node._handle_sync_response(Message('SYNC_RESPONSE','peer',peer))
    else:
        node._handle_block(Message('BLOCK','peer',bad))
    assert node.blockchain.get_latest_block().compute_hash() == old_tip
    assert not node.blockchain.side_branches


def test_reissued_id_requires_new_identifier(node):
    owner = generate_wallet()
    txs = []
    for kind in ['ISSUE','REVOKE','ISSUE']:
        tx = Transaction(kind, owner.public_key_hex, {'credential_id':'C'})
        tx.sign(owner)
        txs.append(tx)
    node.blockchain.add_block(mined(node.blockchain, txs[:2]))
    assert not node.mempool.add_transaction(txs[2],node.blockchain)[0]
    node._handle_block(Message('BLOCK','peer',mined(node.blockchain,txs[2:])))
    assert node.height == 1
    assert node.blockchain.verify_credential('C')[1] == 'REVOKED'
