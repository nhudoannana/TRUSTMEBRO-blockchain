"""Guided PoS integration uses existing selection, signatures and chains."""
from api.session_store import current_session

import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from api import network_store
from tests.test_mempool_api import client, issue, submit
from tests.test_mining_api import low_difficulty, mine
from tests.test_network_api import status, wait_for
from tests.test_verification_api import verify, presentation, revoke


def forge(client, node='Node-1'):
    return client.post('/api/mining/pos', json={'node_id': node})


def prediction(client, node='Node-1'):
    response = client.get('/api/consensus/pos', params={'node_id': node})
    assert response.status_code == 200, response.text
    return response.json()


def test_pos_selection_flow_revocation_and_stable_stakes(client, monkeypatch):
    network = network_store.get_network()
    registry = network.pos_registry
    stakes = {address: v.stake for address, v in registry.validators.items()}
    credential = issue(client)
    expected = registry.select_validator(1, network.consensus_seed,
                                         network.nodes['Node-1'].blockchain.get_latest_block().compute_hash())
    predicted = prediction(client)
    assert predicted['prediction_provisional']
    assert predicted['predicted_validator']['address'] == expected.address
    assert predicted['target_height'] == 1
    assert sum(v['selection_weight'] for v in predicted['validators']) == pytest.approx(1)
    assert credential['transaction']['sender_public_key'] not in [v.public_key_hex for v in registry.validators.values()]
    assert submit(client, credential).json()['accepted']
    broadcasts = []
    original = network.broadcast
    def broadcast(sender, message):
        broadcasts.append(message)
        original(sender, message)
    monkeypatch.setattr(network, 'broadcast', broadcast)
    response = forge(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['forged'] and result['reason'] is None
    assert len(broadcasts) == 1
    assert result['signer'] == predicted['predicted_validator']
    assert result['signer']['public_key_hex'] == expected.public_key_hex
    assert result['block']['validator_address'] == expected.address
    assert result['seconds'] >= 0 and result['elapsed_scope'] == 'forge_pos_pending call'
    assert 'attempts' not in result and 'private_key' not in response.text and 'PRIVATE KEY' not in response.text
    node = network.nodes['Node-1']
    with node._state_lock:
        block = node.blockchain.get_latest_block()
        assert result['block'] == block.to_dict()
        assert result['transaction_ids'] == [credential['transaction']['tx_id']]
        assert node.height == 1 and not node.mempool.get_transactions()
        assert node.blockchain.is_chain_valid(pos_registry=registry)[0]
    wait_for(client, lambda data: data['all_nodes_synchronized'] and data['nodes'][0]['height'] == 1)
    assert client.post('/api/network/sync').json()['completed']
    verified = verify(client, credential['credential_id'], 'Node-2', presentation(credential))
    assert verified['chain_status']['status'] == 'VERIFIED' and verified['presentation_match']
    assert revoke(client, credential['credential_id']).json()['accepted']
    assert verify(client, credential['credential_id'])['chain_status']['status'] == 'VERIFIED'
    assert forge(client).json()['forged']
    wait_for(client, lambda data: data['all_nodes_synchronized'] and data['nodes'][0]['height'] == 2)
    assert verify(client, credential['credential_id'], 'Node-3')['chain_status']['status'] == 'REVOKED'
    assert stakes == {address: v.stake for address, v in registry.validators.items()}


def test_offline_catchup_and_mixed_chain(client, low_difficulty):
    status(client, False)
    first = issue(client)
    assert submit(client, first).json()['accepted']
    assert mine(client).json()['mined']
    second = issue(client)
    assert submit(client, second).json()['accepted']
    assert forge(client).json()['forged']
    assert verify(client, second['credential_id'], 'Node-3')['chain_status']['status'] == 'NOT_FOUND'
    status(client, True)
    data = wait_for(client, lambda data: data['all_nodes_synchronized'] and data['nodes'][0]['height'] == 2)
    assert all(n['chain_valid'] for n in data['nodes'])
    assert verify(client, second['credential_id'], 'Node-3')['chain_status']['status'] == 'VERIFIED'
    network = network_store.get_network()
    chain = network.nodes['Node-1'].blockchain
    assert chain.is_chain_valid(pos_registry=network.pos_registry)[0]
    assert not chain.is_chain_valid()[0]


def test_pos_errors_preserve_pending(client, monkeypatch):
    assert forge(client, 'missing').status_code == 404
    assert client.get('/api/consensus/pos?node_id=missing').status_code == 404
    assert forge(client).json()['reason'] == 'Mempool trống — không có TX để tạo khối PoS'
    node = network_store.get_network().nodes['Node-1']
    node.go_offline()
    assert forge(client).json()['reason'] == 'Node đang OFFLINE'
    node.go_online()
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    for validator in node.network.pos_registry.validators.values():
        validator.is_active = False
    data = prediction(client)
    assert data['predicted_validator'] is None and not any(v['eligible'] for v in data['validators'])
    assert forge(client).json()['reason'] == 'Không tìm thấy validator hợp lệ trong mạng PoS'
    assert len(node.mempool.get_transactions()) == 1
    for validator in node.network.pos_registry.validators.values():
        validator.is_active = True
    monkeypatch.setattr(node, '_validate_candidate', lambda block: (False, 'fixture: rejected candidate'))
    result = forge(client).json()
    assert not result['forged'] and result['reason'] == 'fixture: rejected candidate'
    assert len(node.mempool.get_transactions()) == 1 and node.height == 0


def test_reset_replaces_registry_and_public_contract(client):
    old = network_store.get_network().pos_registry
    before = prediction(client)
    assert 'private_key' not in str(before) and 'PRIVATE KEY' not in str(before)
    client.post('/api/session/reset')
    after = prediction(client)
    assert network_store.get_network().pos_registry is not old
    assert after['reset_count'] == before['reset_count'] + 1
    assert set(v['address'] for v in before['validators']).isdisjoint(v['address'] for v in after['validators'])
    assert not current_session().signed_credentials
    assert all(n['pending_count'] == 0 for n in client.get('/api/mempool').json()['nodes'])


@pytest.mark.parametrize('body', [{}, {'node_id':' '}, {'node_id':'Node-1','validator':'fake'}])
def test_pos_request_contract(client, body):
    assert client.post('/api/mining/pos', json=body).status_code == 422


def test_forging_metadata_and_reset_share_locks(client, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    old = network_store.get_network()
    node = old.nodes['Node-1']
    expected = prediction(client)['predicted_validator']
    entered, release, requested = threading.Event(), threading.Event(), threading.Event()
    original = node.forge_pos_pending
    def paused():
        assert current_session().lock._is_owned()
        assert all(n._state_lock._is_owned() for n in old.nodes.values())
        entered.set()
        assert release.wait(2)
        return original()
    monkeypatch.setattr(node, 'forge_pos_pending', paused)
    def reset():
        requested.set()
        return client.post('/api/session/reset')
    with ThreadPoolExecutor(max_workers=2) as executor:
        forging = executor.submit(forge, client)
        try:
            assert entered.wait(2)
            resetting = executor.submit(reset)
            assert requested.wait(2) and not resetting.done()
        finally:
            release.set()
        result = forging.result(timeout=4).json()
        session = resetting.result(timeout=4).json()
    assert result['forged'] and result['signer'] == expected
    assert session['reset_count'] == result['reset_count'] + 1
    assert network_store.get_network().pos_registry is not old.pos_registry
    assert all(n.height == 0 for n in network_store.get_network().nodes.values())


def test_unexpected_pos_failure_preserves_pending(client, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    node = network_store.get_network().nodes['Node-1']
    def fail():
        raise RuntimeError('fixture exception')
    monkeypatch.setattr(node, 'forge_pos_pending', fail)
    response = forge(client)
    assert response.status_code == 500
    assert response.json()['detail']['code'] == 'mining_failed'
    assert node.height == 0 and len(node.mempool.get_transactions()) == 1
