"""Disposable queue-network lab, including real catch-up and worker cleanup."""
import json
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from api import wallet_api, network_store
from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.mining import mine_block
from fastapi.testclient import TestClient
from tests.test_mempool_api import client


def initialize(client):
    response = client.post('/api/labs/network')
    assert response.status_code == 201, response.text
    return response.json()


def path(handle, suffix=''):
    return f'/api/labs/network/{handle}{suffix}'


def read(client, handle):
    response = client.get(path(handle))
    assert response.status_code == 200, response.text
    return response.json()


def wait_for(client, handle, predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = read(client, handle)
        if predicate(snapshot):
            return snapshot
        time.sleep(.02)
    pytest.fail(f'Lab propagation timed out: {snapshot}')


def node3(client, handle, online):
    return client.post(path(handle, '/nodes/Node-3/status'), json={'online': online})


def test_offline_peer_and_automatic_catchup(client, monkeypatch):
    data = initialize(client)
    handle = data['lab_handle']
    entry = wallet_api._lab_networks[handle]
    network = entry['network']
    assert data['all_nodes_synchronized'] and all(n['height'] == 0 for n in data['nodes'])
    assert all(n['verification'] is None for n in data['nodes'])
    assert node3(client, handle, False).json()['changed']
    seen_registries = []
    original = Blockchain.verify_credential
    def verify(chain, *args, **kwargs):
        seen_registries.append(kwargs['pos_registry'])
        return original(chain, *args, **kwargs)
    monkeypatch.setattr(Blockchain, 'verify_credential', verify)
    mined = client.post(path(handle, '/mine')).json()
    assert mined['mined'] and mined['block']['difficulty'] == 3
    behind = wait_for(client, handle, lambda d: [n['height'] for n in d['nodes']] == [1, 1, 0])
    assert [n['verification']['status'] for n in behind['nodes']] == ['VERIFIED', 'VERIFIED', 'NOT_FOUND']
    assert behind['nodes'][2]['local_chain_warning']
    assert behind['online_nodes_synchronized'] and not behind['all_nodes_synchronized']
    offline_tip = behind['nodes'][2]['tip_hash']
    manual = client.post(path(handle, '/sync')).json()
    assert not manual['completed']
    assert manual['snapshot']['nodes'][2]['status'] == 'OFFLINE'
    assert manual['snapshot']['nodes'][2]['tip_hash'] == offline_tip
    broadcasts = []
    broadcast = network.broadcast
    def capture(sender, message):
        if sender == 'Node-3' and message.msg_type == 'SYNC_REQUEST':
            broadcasts.append(message)
        return broadcast(sender, message)
    monkeypatch.setattr(network, 'broadcast', capture)
    online = node3(client, handle, True).json()
    assert online['changed'] and online['catch_up_requested']
    assert len(broadcasts) == 1
    converged = wait_for(client, handle, lambda d: d['all_nodes_synchronized'])
    assert all(n['status'] == 'ONLINE' and n['height'] == 1 and n['tip_hash'] == mined['block']['hash']
               and n['chain_valid'] and n['verification']['status'] == 'VERIFIED' for n in converged['nodes'])
    assert all(r is network.pos_registry for r in seen_registries)
    assert not node3(client, handle, True).json()['changed'] and len(broadcasts) == 1
    assert client.post(path(handle, '/sync')).json()['completed']
    assert all(n['height'] == 1 for n in read(client, handle)['nodes'])
    assert client.post(path(handle, '/mine')).status_code == 409
    assert 'private' not in json.dumps(converged).lower()
    assert 'BEGIN PRIVATE KEY' not in json.dumps(mined)


def test_lab_and_other_state_isolation_and_repeated_cleanup(client):
    shared = network_store.get_network()
    shared_wallets = client.get('/api/wallets').json()
    before = client.get('/api/network').json(), client.get('/api/session').json(), dict(network_store.signed_credentials)
    key = client.post('/api/labs/signatures/keys').json()
    other = initialize(client)['lab_handle']
    for _ in range(3):
        data = initialize(client)
        handle = data['lab_handle']
        network = wallet_api._lab_networks[handle]['network']
        assert node3(client, handle, False).status_code == 200
        assert client.post(path(handle, '/mine')).json()['mined']
        assert client.post(path(handle, '/reset')).json()['cleared']
        assert all(not n._worker.is_alive() for n in network.nodes.values())
        assert not client.post(path(handle, '/reset')).json()['cleared']
        assert client.get(path(handle)).status_code == 404
        assert client.post(path(handle, '/mine')).status_code == 404
    assert network_store.get_network() is shared
    assert client.get('/api/wallets').json() == shared_wallets
    assert before == (client.get('/api/network').json(), client.get('/api/session').json(), dict(network_store.signed_credentials))
    assert client.post('/api/labs/signatures/sign', json={'key_handle': key['key_handle'], 'message': 'still usable'}).status_code == 200
    assert all(n['height'] == 0 for n in read(client, other)['nodes'])
    assert len(wallet_api._lab_networks) == 1
    comparison = client.post('/api/labs/consensus/run', json={'mode': 'pos'})
    assert comparison.status_code == 200 and comparison.json()['created']
    assert all(n['height'] == 0 for n in read(client, other)['nodes'])
    client.post('/api/session/reset')
    assert client.get(path(other)).status_code == 200  # Guided reset cannot reset this lab.


def test_expiry_capacity_and_shutdown_cleanup(client, monkeypatch):
    monkeypatch.setattr(wallet_api, '_LAB_NETWORK_LIMIT', 1)
    data = initialize(client)
    handle = data['lab_handle']
    network = wallet_api._lab_networks[handle]['network']
    assert client.post('/api/labs/network').status_code == 429
    # Exercise the real expiry callback without a long sleep.
    entry = wallet_api._lab_networks[handle]
    entry['expires'] = time.monotonic() - 1
    wallet_api._expire_lab_network(handle)
    assert handle not in wallet_api._lab_networks
    assert all(not n._worker.is_alive() for n in network.nodes.values())
    new = initialize(client)['lab_handle']
    node = wallet_api._lab_networks[new]['network'].nodes['Node-1']
    wallet_api.close_lab_networks()
    assert not wallet_api._lab_networks and not node._worker.is_alive()


def test_lifespan_shutdown_stops_workers_and_timer():
    with TestClient(wallet_api.app) as local:
        handle = initialize(local)['lab_handle']
        entry = wallet_api._lab_networks[handle]
    entry['timer'].join(timeout=1)
    assert not entry['timer'].is_alive()
    assert all(not node._worker.is_alive() for node in entry['network'].nodes.values())
    assert not wallet_api._lab_networks


def test_reset_waits_for_mining_and_new_handle_starts_fresh(client, monkeypatch):
    handle = initialize(client)['lab_handle']
    old = wallet_api._lab_networks[handle]['network']
    node = old.nodes['Node-1']
    mining_started, release_mining, resetting = threading.Event(), threading.Event(), threading.Event()
    mine = node.mine_pending
    def paused_mine():
        mining_started.set()
        assert release_mining.wait(timeout=3)
        return mine(difficulty=1)
    def reset():
        resetting.set()
        return client.post(path(handle, '/reset'))
    monkeypatch.setattr(node, 'mine_pending', paused_mine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mining = pool.submit(client.post, path(handle, '/mine'))
        assert mining_started.wait(timeout=3)
        cleaning = pool.submit(reset)
        assert resetting.wait(timeout=3)
        assert not cleaning.done()
        release_mining.set()
        assert mining.result(timeout=5).json()['mined']
        assert cleaning.result(timeout=5).json()['cleared']
    assert all(not n._worker.is_alive() for n in old.nodes.values())
    fresh = initialize(client)
    assert fresh['lab_handle'] != handle and fresh['credential_id'] is None
    assert all(n['height'] == 0 and n['verification'] is None for n in fresh['nodes'])
    assert client.get(path(handle)).status_code == 404


def test_divergence_and_invalid_chain_never_label_complete(client):
    handle = initialize(client)['lab_handle']
    mined = client.post(path(handle, '/mine')).json()
    data = wait_for(client, handle, lambda d: d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 1)
    network = wallet_api._lab_networks[handle]['network']
    node = network.nodes['Node-2']
    with node._state_lock:
        original = node.blockchain.chain[-1]
        fork = Block(deepcopy(original.transactions), 1, original.header.previous_hash,
                     difficulty=1, timestamp='2026-10-03T00:00:00+00:00')
        mine_block(fork)
        node.blockchain.chain[-1] = fork
    divergent = read(client, handle)
    assert divergent['online_nodes_valid'] and not divergent['online_nodes_agree']
    assert not divergent['all_nodes_synchronized']
    assert divergent['nodes'][0]['height'] == divergent['nodes'][1]['height']
    assert divergent['nodes'][0]['tip_hash'] != divergent['nodes'][1]['tip_hash']
    with node._state_lock:
        node.blockchain.chain[-1].header.merkle_root = 'invalid'
    invalid = read(client, handle)
    assert not invalid['nodes'][1]['chain_valid']
    assert invalid['nodes'][1]['verification']['status'] == 'INVALID'
    assert not invalid['all_nodes_synchronized']
    synced = client.post(path(handle, '/sync')).json()
    assert synced['snapshot']['all_nodes_synchronized']  # Existing backend recovers from valid peer.


def test_backend_rejection_and_failure_preserve_lab_for_retry(client, monkeypatch):
    handle = initialize(client)['lab_handle']
    node = wallet_api._lab_networks[handle]['network'].nodes['Node-1']
    original = node._validate_candidate
    monkeypatch.setattr(node, '_validate_candidate', lambda b: (False, 'fixture: backend rejected block'))
    rejected = client.post(path(handle, '/mine')).json()
    assert not rejected['mined'] and rejected['reason'] == 'fixture: backend rejected block'
    assert read(client, handle)['nodes'][0]['pending_count'] == 1
    tx_id = read(client, handle)['transaction']['tx_id']
    monkeypatch.setattr(node, '_validate_candidate', original)
    assert client.post(path(handle, '/mine')).json()['mined']
    assert read(client, handle)['transaction']['tx_id'] == tx_id
    def fail(**kwargs):
        raise RuntimeError('fixture sync failure')
    monkeypatch.setattr(node.network, 'sync_all_nodes', fail)
    response = client.post(path(handle, '/sync'))
    assert response.status_code == 500
    assert client.get(path(handle)).status_code == 200


@pytest.mark.parametrize('body', [{}, {'online':'false'}, {'online':1}, {'online':False,'payload':'fake'}])
def test_unknown_and_status_validation(client, body):
    assert client.get(path('missing')).status_code == 404
    handle = initialize(client)['lab_handle']
    assert client.post(path(handle, '/nodes/Node-3/status'), json=body).status_code == 422
    assert client.post(path(handle, '/nodes/missing/status'), json={'online':True}).status_code == 404
