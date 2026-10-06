"""Gateway integration with real ephemeral loopback HTTP servers, not mocks."""
import json
import socket
import threading
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from api import session_store, wallet_api
from blockchain.net_node import NetNode


def initialize(client):
    response = client.post('/api/labs/network', json={'transport': 'http'})
    assert response.status_code == 201, response.text
    assert response.json().get('transport') == 'http'
    return response.json()['lab_handle']


def path(handle, suffix=''):
    return '/api/labs/network/' + handle + suffix


def context(client):
    return session_store.registry.entries[client.cookies.get(session_store.COOKIE_NAME)]


def http(node, route, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{node.port}{route}',
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def assert_closed(network):
    for node in network.nodes.values():
        assert not node._server_thread.is_alive()
        assert node._server.socket.fileno() == -1
        with socket.socket() as connection:
            connection.settimeout(.1)
            assert connection.connect_ex(('127.0.0.1', node.port)) != 0


def test_real_http_gateway_offline_explicit_sync_and_validation(monkeypatch):
    requests = []
    open_url = urllib.request.urlopen
    def observed(request, *args, **kwargs):
        requests.append(request.full_url)
        return open_url(request, *args, **kwargs)
    monkeypatch.setattr(urllib.request, 'urlopen', observed)
    with TestClient(wallet_api.app) as client:
        handle = initialize(client)
        network = context(client).lab_networks[handle]['network']
        assert all(node.host == '127.0.0.1' and node.port > 0 for node in network.nodes.values())
        assert len({node.port for node in network.nodes.values()}) == 3
        assert client.post(path(handle, '/nodes/Node-3/status'), json={'online': False}).status_code == 200
        mined = client.post(path(handle, '/mine')).json()
        assert mined['mined'], mined
        snapshot = client.get(path(handle)).json()
        assert [n['height'] for n in snapshot['nodes']] == [1, 1, 0]
        assert [n['verification']['status'] for n in snapshot['nodes']] == ['VERIFIED', 'VERIFIED', 'NOT_FOUND']
        # These observations are read through each real node HTTP endpoint.
        assert [http(n, '/status')['height'] for n in network.nodes.values()] == [1, 1, 0]
        assert http(network.nodes['Node-3'], '/mine', {}) == {'ok': False, 'reason': 'Node OFFLINE'}
        online = client.post(path(handle, '/nodes/Node-3/status'), json={'online': True}).json()
        assert online['changed'] and not online['catch_up_requested']
        assert online['snapshot']['nodes'][2]['height'] == 0
        restored = client.post(path(handle, '/sync')).json()
        assert restored['completed'], restored
        assert all(n['verification']['status'] == 'VERIFIED' and n['chain_valid']
                   and n['tip_hash'] == mined['block']['hash'] for n in restored['snapshot']['nodes'])
        assert any('HTTP' in event for event in restored['snapshot']['events'])
        assert any('/submit_tx' in url for url in requests)
        assert any('/mine' in url for url in requests)
        assert any('/message' in url for url in requests)
        assert any('/sync' in url for url in requests)
        assert all(url.startswith('http://127.0.0.1:') for url in requests)
        changed = dict(snapshot['transaction'])
        changed['payload'] = {**changed['payload'], 'title': 'corrupted'}
        rejection = http(network.nodes['Node-2'], '/submit_tx', changed)
        assert not rejection['ok'] and 'tx_id' in rejection['reason']
        assert 'private' not in json.dumps(restored).lower()
        assert client.post(path(handle, '/reset')).json()['cleared']
        assert not client.post(path(handle, '/reset')).json()['cleared']
        assert_closed(network)


def test_bad_block_and_incomplete_mining_keep_pending_evidence(monkeypatch):
    from blockchain.net_node import block_to_json
    from blockchain.block import Block
    with TestClient(wallet_api.app) as client:
        handle = initialize(client)
        network = context(client).lab_networks[handle]['network']
        node1, node2 = network.nodes['Node-1'], network.nodes['Node-2']
        real_miner = node1._miner
        monkeypatch.setattr(node1, '_miner', lambda block: {'completed': False,
            'reason': 'fixture: bounded search incomplete', 'attempts': 2, 'seconds': .001})
        incomplete = client.post(path(handle, '/mine')).json()
        assert not incomplete['mined'] and incomplete['reason'] == 'fixture: bounded search incomplete'
        assert incomplete['block'] is None
        assert all(n['height'] == 0 and n['pending_count'] == 1 for n in incomplete['snapshot']['nodes'])
        tx = node1.mempool.get_transactions()[0]
        invalid = Block([tx], 1, node2.blockchain.get_latest_block().compute_hash(), difficulty=3)
        invalid.header.merkle_root = 'invalid-root'
        rejected = http(node2, '/message', {'msg_type': 'BLOCK', 'msg_id': 'bad-block',
            'sender_id': 'Node-1', 'payload': block_to_json(invalid)})
        assert not rejected['ok'] and rejected['reason'] == 'merkle_root mismatch'
        assert http(node2, '/status')['height'] == 0
        monkeypatch.setattr(node1, '_miner', real_miner)
        assert client.post(path(handle, '/mine')).json()['mined']


def test_active_http_request_is_not_expired(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    now = [0.0]
    registry = session_store.SessionRegistry(clock=lambda: now[0], idle_seconds=10)
    monkeypatch.setattr(session_store, 'registry', registry)
    with TestClient(wallet_api.app) as client:
        handle = initialize(client)
        owner = context(client)
        network = owner.lab_networks[handle]['network']
        node = network.nodes['Node-1']
        started, release = threading.Event(), threading.Event()
        original = node._miner
        def paused(block):
            started.set()
            assert release.wait(5)
            return original(block)
        monkeypatch.setattr(node, '_miner', paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(client.post, path(handle, '/mine'))
            try:
                assert started.wait(3)
                now[0] = 11
                registry.cleanup()
                assert owner in registry.entries.values()
                assert all(n._server_thread.is_alive() for n in network.nodes.values())
            finally:
                release.set()
            assert response.result(5).json()['mined']


def test_cookie_isolation_queue_guided_state_and_expiry_cleanup():
    with TestClient(wallet_api.app) as a, TestClient(wallet_api.app) as b:
        before = a.get('/api/network').json(), a.get('/api/wallets').json(), a.get('/api/session').json()
        queue = a.post('/api/labs/network').json()['lab_handle']
        ha, hb = initialize(a), initialize(b)
        na, nb = context(a).lab_networks[ha]['network'], context(b).lab_networks[hb]['network']
        assert {n.port for n in na.nodes.values()}.isdisjoint(n.port for n in nb.nodes.values())
        for suffix in ['', '/mine', '/sync', '/nodes/Node-3/status']:
            response = b.get(path(ha)) if not suffix else b.post(path(ha, suffix), json={'online': False})
            assert response.status_code == 404
        assert a.post(path(ha, '/mine')).json()['mined']
        assert all(n['height'] == 0 for n in b.get(path(hb)).json()['nodes'])
        assert all(n['height'] == 0 for n in a.get(path(queue)).json()['nodes'])
        assert before == (a.get('/api/network').json(), a.get('/api/wallets').json(), a.get('/api/session').json())
        a.post('/api/session/reset')
        assert a.get(path(ha)).status_code == 200
        entry = context(a).lab_networks[ha]
        entry['expires'] = time.monotonic() - 1
        wallet_api._expire_lab_network(ha, context(a))
        assert a.get(path(ha)).status_code == 404
        assert_closed(na)
        assert b.get(path(hb)).status_code == 200
    assert_closed(nb)


def test_partial_startup_failure_closes_servers_and_releases_capacity(monkeypatch):
    started = []
    original = NetNode.start
    def failing_start(node):
        original(node)
        started.append(node)
        if len(started) == 2:
            raise OSError('fixture: startup failed after bind')
    with TestClient(wallet_api.app) as client:
        monkeypatch.setattr(NetNode, 'start', failing_start)
        response = client.post('/api/labs/network', json={'transport': 'http'})
        assert response.status_code == 503, response.text
        assert response.json()['detail']['code'] == 'http_start_failed'
        assert not context(client).lab_networks
        for node in started:
            assert not node._server_thread.is_alive() and node._server.socket.fileno() == -1
        monkeypatch.setattr(NetNode, 'start', original)
        assert initialize(client)


def test_http_capacity_is_controlled_without_eviction(monkeypatch):
    from api import http_network
    monkeypatch.setattr(http_network, '_slots', threading.BoundedSemaphore(1))
    with TestClient(wallet_api.app) as a, TestClient(wallet_api.app) as b:
        ha = initialize(a)
        assert a.post('/api/labs/network', json={'transport': 'http'}).status_code == 429
        blocked = b.post('/api/labs/network', json={'transport': 'http'})
        assert blocked.status_code == 503 and blocked.json()['detail']['code'] == 'http_capacity'
        assert a.get(path(ha)).status_code == 200
        a.post(path(ha, '/reset'))
        assert initialize(b)


@pytest.mark.parametrize('body', [{'transport': 'tcp'}, {'transport': 'http', 'url': 'http://example.com'},
                                 {'transport': 'http', 'difficulty': 99}])
def test_gateway_rejects_client_addresses_and_controls(body):
    with TestClient(wallet_api.app) as client:
        assert client.post('/api/labs/network', json=body).status_code == 422


def test_http_session_expiry_stops_nodes_without_long_sleep(monkeypatch):
    now = [0.0]
    registry = session_store.SessionRegistry(clock=lambda: now[0], idle_seconds=10)
    monkeypatch.setattr(session_store, 'registry', registry)
    with TestClient(wallet_api.app) as client:
        handle = initialize(client)
        old_context = context(client)
        network = old_context.lab_networks[handle]['network']
        now[0] = 11
        assert client.get(path(handle)).status_code == 404
        assert context(client) is not old_context
        assert_closed(network)
