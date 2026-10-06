"""Step F: real snapshots and queue-based catch-up through the API."""

import time
from copy import deepcopy

import pytest

from api import network_store
from blockchain.block import Block
from blockchain.mining import mine_block
from tests.test_mempool_api import client, issue, submit
from tests.test_mining_api import low_difficulty, mine


def snapshot(client):
    response = client.get('/api/network')
    assert response.status_code == 200
    return response.json()


def status(client, online, node='Node-3'):
    return client.post(f'/api/network/nodes/{node}/status', json={'online': online})


def wait_for(client, predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        data = snapshot(client)
        if predicate(data):
            return data
        time.sleep(0.02)
    pytest.fail(f'Catch-up timeout: {data}')


def mine_one(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    response = mine(client)
    assert response.status_code == 200 and response.json()['mined']
    return response.json()


def test_mining_propagates_and_sync_is_idempotent(client, low_difficulty):
    result = mine_one(client)
    data = wait_for(client, lambda d: d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 1)
    assert all(n['tip_hash'] == result['block']['hash'] for n in data['nodes'])
    assert all(n['block_count'] == 2 and n['chain_valid'] for n in data['nodes'])
    response = client.post('/api/network/sync')
    assert response.status_code == 200
    assert response.json()['completed']
    after = snapshot(client)
    assert [(n['height'], n['tip_hash']) for n in after['nodes']] == [(n['height'], n['tip_hash']) for n in data['nodes']]


def test_offline_remains_behind_sync_then_online_catches_up(client, low_difficulty, monkeypatch):
    assert status(client, False).json()['changed']
    result = mine_one(client)
    data = wait_for(client, lambda d: [n['height'] for n in d['nodes']] == [1, 1, 0])
    assert data['online_nodes_synchronized'] and not data['all_nodes_synchronized']
    offline_tip = data['nodes'][2]['tip_hash']
    response = client.post('/api/network/sync').json()
    assert response['completed']
    assert response['network']['nodes'][2]['status'] == 'OFFLINE'
    assert response['network']['nodes'][2]['height'] == 0
    assert response['network']['nodes'][2]['tip_hash'] == offline_tip
    net = network_store.get_network()
    original = net.broadcast
    requests = []
    def broadcast(sender, message):
        if sender == 'Node-3' and message.msg_type == 'SYNC_REQUEST':
            requests.append(message)
        original(sender, message)
    monkeypatch.setattr(net, 'broadcast', broadcast)
    response = status(client, True).json()
    assert response['changed'] and response['catch_up_requested']
    assert len(requests) == 1
    data = wait_for(client, lambda d: d['all_nodes_synchronized'])
    assert all(n['height'] == 1 and n['tip_hash'] == result['block']['hash'] for n in data['nodes'])
    assert not status(client, True).json()['changed']
    assert len(requests) == 1


def test_equal_height_different_tips_are_divergent(client, low_difficulty):
    status(client, False)
    mine_one(client)
    wait_for(client, lambda d: d['nodes'][1]['height'] == 1)
    node = network_store.get_network().nodes['Node-2']
    with node._state_lock:
        original = node.blockchain.chain[-1]
        fork = Block(deepcopy(original.transactions), 1, original.header.previous_hash, difficulty=1, timestamp='2026-10-03T00:00:00+00:00')
        mine_block(fork)
        node.blockchain.chain[-1] = fork
        node.blockchain.block_pool[fork.compute_hash()] = fork
    data = snapshot(client)
    assert data['nodes'][0]['height'] == data['nodes'][1]['height']
    assert data['nodes'][0]['tip_hash'] != data['nodes'][1]['tip_hash']
    assert data['online_nodes_valid']
    assert not data['online_nodes_agree'] and not data['online_nodes_synchronized']
    assert not data['all_nodes_synchronized']


def test_validator_reasons_and_sync_failure_are_real(client, low_difficulty):
    mine_one(client)
    wait_for(client, lambda d: d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 1)
    net = network_store.get_network()
    for node in net.nodes.values():
        with node._state_lock:
            node.blockchain.chain[1].header.merkle_root = 'invalid'
    data = snapshot(client)
    assert not data['online_nodes_valid'] and not data['online_nodes_synchronized']
    for row in data['nodes']:
        node = net.nodes[row['node_id']]
        with node._state_lock:
            expected = node.blockchain.is_chain_valid(pos_registry=net.pos_registry, authorized_issuers=node.mempool.authorized_issuers)
        assert row['chain_valid'] == expected[0]
        assert row['invalid_height'] == expected[1]
        assert row['validity_reason'] == expected[2]
    response = client.post('/api/network/sync').json()
    assert not response['completed']
    assert response['reason'] == data['nodes'][0]['validity_reason']


def test_unknown_repeated_status_and_reset(client):
    assert status(client, False, 'missing').status_code == 404
    assert not status(client, True).json()['changed']
    assert status(client, False).json()['changed']
    assert not status(client, False).json()['changed']
    before = snapshot(client)
    client.post('/api/session/reset')
    data = snapshot(client)
    assert data['reset_count'] == before['reset_count'] + 1
    assert data['all_nodes_synchronized']
    assert all(n['status'] == 'ONLINE' and n['height'] == 0 and n['block_count'] == 1 for n in data['nodes'])


def test_no_online_nodes_is_not_synchronized(client):
    for node in ['Node-1', 'Node-2', 'Node-3']:
        status(client, False, node)
    data = snapshot(client)
    assert not data['online_nodes_synchronized'] and not data['all_nodes_synchronized']
    assert not client.post('/api/network/sync').json()['completed']
    assert all(n['status'] == 'OFFLINE' for n in snapshot(client)['nodes'])


@pytest.mark.parametrize('body', [{}, {'online':'true'}, {'online':1}, {'online':None}, {'online':True,'status':'OFFLINE'}])
def test_explicit_boolean_required(client, body):
    assert client.post('/api/network/nodes/Node-3/status', json=body).status_code == 422
