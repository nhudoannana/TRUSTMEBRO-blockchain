"""Step E: actual Node PoW through the existing adapter."""
from api.session_store import current_session


import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from api import network_store
from blockchain.mining import is_acceptable_pow
from tests.test_mempool_api import client, issue, submit, wait_for_counts


@pytest.fixture
def low_difficulty(client, monkeypatch):
    """Only test calls use difficulty 1; application default stays 3."""
    node = network_store.get_network().nodes['Node-1']
    original = node.mine_pending
    monkeypatch.setattr(node, 'mine_pending', lambda: original(difficulty=1))
    return node


def mine(client, node='Node-1'):
    return client.post('/api/mining/pow', json={'node_id': node})


def test_issue_submit_mine_real_block(client, low_difficulty, monkeypatch):
    credentials = [issue(client) for _ in range(2)]
    for credential in credentials:
        assert submit(client, credential).json()['accepted']
    wait_for_counts(client, [2, 2, 2])
    node = low_difficulty
    previous = node.blockchain.get_latest_block().compute_hash()
    height = node.height
    broadcasts = []
    original = node.network.broadcast
    def broadcast(sender, message):
        broadcasts.append(message)
        original(sender, message)
    monkeypatch.setattr(node.network, 'broadcast', broadcast)
    response = mine(client)
    assert response.status_code == 200
    result = response.json()
    assert result['mined'] is True
    with node._state_lock:
        block = node.blockchain.get_latest_block()
        assert result['block'] == block.to_dict()
        assert block.header.previous_hash == previous
        assert block.height == height + 1 == node.height
        assert result['transaction_ids'] == [c['transaction']['tx_id'] for c in credentials]
        assert result['transaction_ids'] == [tx.tx_id for tx in block.transactions]
        assert block.transaction_count == 2
        assert is_acceptable_pow(block)
        assert block.header.difficulty == 1
        assert node.blockchain.is_chain_valid(pos_registry=node.network.pos_registry)[0]
        assert not node.mempool.get_transactions()
        assert result['attempts'] == block.header.nonce + 1
        assert result['seconds'] >= 0
    assert len(broadcasts) == 1 and broadcasts[0].payload is block
    wait_for_counts(client, [0, 0, 0])
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if all(n.height == 1 for n in node.network.nodes.values()):
            break
        time.sleep(0.02)
    assert all(n.height == 1 for n in node.network.nodes.values())


def test_real_demo_default_difficulty(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    result = mine(client).json()
    assert result['mined']
    assert result['block']['difficulty'] == 3
    assert result['block']['hash'].startswith('000')
    print(f"Measured demo difficulty 3: {result['seconds']} seconds, {result['attempts']} attempts")


def test_unknown_offline_and_empty(client):
    assert mine(client, 'missing').status_code == 404
    result = mine(client).json()
    assert result['mined'] is False
    assert result['reason'] == 'Mempool trống — không có TX để mine'
    assert result['block'] is None and result['seconds'] is None
    node = network_store.get_network().nodes['Node-1']
    node.go_offline()
    result = mine(client).json()
    assert not result['mined'] and result['reason'] == 'Node đang OFFLINE'


def test_validation_failure_preserves_pending(client, low_difficulty, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    reason = 'fixture: candidate validation failed'
    monkeypatch.setattr(low_difficulty, '_validate_candidate', lambda block: (False, reason))
    result = mine(client).json()
    assert result['mined'] is False and result['reason'] == reason
    assert low_difficulty.height == 0
    with low_difficulty._state_lock:
        assert [tx.tx_id for tx in low_difficulty.mempool.get_transactions()] == [credential['transaction']['tx_id']]


def test_unexpected_failure_clear_and_no_pending_deletion(client, low_difficulty, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    def fail():
        raise RuntimeError('fixture exception')
    monkeypatch.setattr(low_difficulty, 'mine_pending', fail)
    response = mine(client)
    assert response.status_code == 500
    assert response.json()['detail']['code'] == 'mining_failed'
    assert low_difficulty.height == 0
    assert len(low_difficulty.mempool.get_transactions()) == 1


def test_reset_after_mining_recreates_chain(client, low_difficulty):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    old = network_store.get_network()
    result = mine(client).json()
    assert result['mined']
    client.post('/api/session/reset')
    assert network_store.get_network() is not old
    assert not current_session().signed_credentials
    assert all(node.height == 0 for node in network_store.get_network().nodes.values())
    assert client.get('/api/mempool').json()['reset_count'] == result['reset_count'] + 1
    assert all(row['pending_count'] == 0 for row in client.get('/api/mempool').json()['nodes'])


def test_reset_waits_for_mining_session_lock(client, low_difficulty, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    entered, release, reset_requested = threading.Event(), threading.Event(), threading.Event()
    original = low_difficulty.mine_pending
    def paused():
        assert current_session().lock._is_owned()
        entered.set()
        assert release.wait(2)
        return original()
    monkeypatch.setattr(low_difficulty, 'mine_pending', paused)
    def reset():
        reset_requested.set()
        return client.post('/api/session/reset')
    with ThreadPoolExecutor(max_workers=2) as executor:
        mining = executor.submit(mine, client)
        try:
            assert entered.wait(2)
            resetting = executor.submit(reset)
            assert reset_requested.wait(2)
            assert not resetting.done()
        finally:
            release.set()
        result = mining.result(timeout=3).json()
        session = resetting.result(timeout=3).json()
    assert result['mined']
    assert session['reset_count'] == result['reset_count'] + 1
    assert all(node.height == 0 for node in network_store.get_network().nodes.values())


@pytest.mark.parametrize('body', [{}, {'node_id':' '}, {'node_id':'x'*201},
                                 {'node_id':'Node-1','difficulty':1}])
def test_mining_input_contract(client, body):
    assert client.post('/api/mining/pow', json=body).status_code == 422
