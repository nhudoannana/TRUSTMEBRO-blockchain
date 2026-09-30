import threading
import pytest
from blockchain.node import Network, Message
from blockchain.blockchain import Blockchain
from tests.test_review_fixes_round4 import mined
from tests.test_review_fixes import _issue_tx


@pytest.fixture
def network():
    net = Network()
    for i in range(3):
        n = net.create_node(str(i), '127.0.0.1', 5000+i)
        n._running = False
        n._worker.join(timeout=1)
    yield net
    for n in net.nodes.values():
        n._running = False


def test_broadcast_copies_payload_for_each_node(network):
    tx = _issue_tx()
    network.broadcast('0', Message('TX','0',tx))
    first = network.nodes['1'].inbox.get_nowait().payload
    second = network.nodes['2'].inbox.get_nowait().payload
    first.payload['holder_name'] = 'changed'
    assert second.payload['holder_name'] != 'changed'
    assert tx.payload['holder_name'] != 'changed'


def test_receive_cannot_change_chain_while_local_mining(network, monkeypatch):
    import blockchain.node as module
    n = network.nodes['0']
    n.mempool.add_transaction(_issue_tx('LOCAL'), n.blockchain)
    incoming = mined(Blockchain(), [_issue_tx('PEER')])
    entered = threading.Event()
    release = threading.Event()
    delivered = threading.Event()
    real_mine = module.mine_block
    def paused(block):
        entered.set()
        assert release.wait(5)
        return real_mine(block)
    monkeypatch.setattr(module,'mine_block',paused)
    miner = threading.Thread(target=lambda:n.mine_pending(difficulty=1))
    def receive():
        n._handle_block(Message('BLOCK','peer',incoming))
        delivered.set()
    receiver = threading.Thread(target=receive)
    miner.start()
    assert entered.wait(2)
    receiver.start()
    try:
        assert not delivered.wait(0.1)
    finally:
        release.set()
        miner.join(3)
        receiver.join(3)
    assert delivered.is_set()
    assert n.blockchain.is_chain_valid()[0]
    assert n.height == 1
    assert len(n.blockchain.side_branches) == 1
