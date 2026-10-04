"""Independent cookie jars must never share mutable simulation state."""
from fastapi.testclient import TestClient

from api.wallet_api import app
from api import session_store, wallet_api
from api.session_store import COOKIE_NAME, SessionRegistry, bind_session
from api.network_store import get_network
from blockchain.node import Node
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor


def context(client):
    return session_store.registry.entries[client.cookies.get(COOKIE_NAME)]


def issue(client):
    wallet = client.get('/api/wallets').json()[0]
    response = client.post('/api/credentials', json={'issuer_wallet_id': wallet['id'],
        'holder_name': 'Session test', 'title': 'Private simulation', 'issue_date': '2026-10-04'})
    assert response.status_code == 201
    return response.json()


def submit(client, credential):
    return client.post('/api/mempool', json={'credential_id': credential['credential_id'], 'node_id': 'Node-1'})


@pytest.fixture
def clocked(monkeypatch):
    now = [0.0]
    registry = SessionRegistry(clock=lambda: now[0], idle_seconds=10, capacity=3)
    monkeypatch.setattr(session_store, 'registry', registry)
    yield registry, now
    registry.shutdown()


@pytest.fixture
def fast_pow(monkeypatch):
    original = Node.mine_pending
    monkeypatch.setattr(Node, 'mine_pending', lambda node: original(node, difficulty=1))


def test_cookie_clients_do_not_see_each_others_wallets():
    with TestClient(app) as a, TestClient(app) as b:
        wallet = a.post('/api/wallets', json={'name': 'Only client A'}).json()
        assert b.get('/api/wallets/' + wallet['id']).status_code == 404
        assert wallet['id'] not in {w['id'] for w in b.get('/api/wallets').json()}


def test_reset_cannot_delete_another_clients_wallet():
    with TestClient(app) as a, TestClient(app) as b:
        wallet = b.post('/api/wallets', json={'name': 'Keep client B'}).json()
        before = b.get('/api/session').json()
        assert a.post('/api/session/reset').status_code == 200
        assert b.get('/api/wallets/' + wallet['id']).status_code == 200
        assert b.get('/api/session').json() == before


def test_real_guided_state_explorer_pow_pos_and_reset_are_isolated(fast_pow):
    with TestClient(app) as a, TestClient(app) as b:
        ca, cb = issue(a), issue(b)
        a_ctx, b_ctx = context(a), context(b)
        assert a_ctx.network is None and b_ctx.network is None  # Issuance does not create a Network.
        assert submit(a, ca).json()['accepted'] and submit(b, cb).json()['accepted']
        assert submit(b, ca).status_code == 404
        assert a_ctx.signed_credentials.keys() == {ca['credential_id']}
        assert b_ctx.signed_credentials.keys() == {cb['credential_id']}
        assert a_ctx.network is not b_ctx.network
        assert a_ctx.network.pos_registry is not b_ctx.network.pos_registry
        mined = a.post('/api/mining/pow', json={'node_id': 'Node-1'}).json()
        assert mined['mined']
        assert a.get('/api/explorer/blocks/1').json()['transactions'] == [ca['transaction']]
        assert b.get('/api/explorer/blocks/1').status_code == 404
        assert b.get('/api/explorer/blocks').json()['tip_height'] == 0
        assert b.post('/api/verify', json={'credential_id': ca['credential_id'], 'node_id': 'Node-1'}).json()['chain_status']['status'] == 'NOT_FOUND'
        assert b.post('/api/credentials/'+ca['credential_id']+'/revoke', json={'node_id': 'Node-1'}).status_code == 404
        b_before = b.get('/api/network').json(), b.get('/api/mempool').json(), b.get('/api/wallets').json(), b_ctx.generation
        old_cookie, old_gen = a.cookies.get(COOKIE_NAME), a_ctx.generation
        mined_nodes = list(a_ctx.network.nodes.values())
        a.post('/api/session/reset')
        assert a.cookies.get(COOKIE_NAME) == old_cookie and a_ctx.generation != old_gen
        assert all(not n._worker.is_alive() for n in mined_nodes)
        assert not a_ctx.signed_credentials
        assert b_before == (b.get('/api/network').json(), b.get('/api/mempool').json(), b.get('/api/wallets').json(), b_ctx.generation)
        forged = b.post('/api/mining/pos', json={'node_id': 'Node-1'}).json()
        assert forged['forged']
        assert b.get('/api/explorer/blocks/1').json()['validator']['public_key_hex'] == forged['signer']['public_key_hex']
        assert a.get('/api/explorer/blocks/1').status_code == 404
        assert b.post('/api/verify', json={'credential_id': cb['credential_id'], 'node_id': 'Node-1'}).json()['chain_status']['status'] == 'VERIFIED'


def test_cookie_stable_same_profile_tabs_and_ignored_selection_inputs():
    with TestClient(app) as a, TestClient(app) as b:
        wallet = a.post('/api/wallets', json={'name': 'A'}).json()
        cookie = a.cookies.get(COOKIE_NAME)
        a.get('/api/session')
        assert a.cookies.get(COOKIE_NAME) == cookie
        b.get('/api/session', params={'session_id': cookie}, headers={'X-Session-ID': cookie})
        assert b.get('/api/wallets/'+wallet['id']).status_code == 404
        b.post('/api/wallets', json={'name': 'B', 'session_id': cookie})
        assert len(a.get('/api/wallets').json()) == 3
        b.cookies.clear()
        b.cookies.set(COOKIE_NAME, cookie)
        assert b.get('/api/wallets/'+wallet['id']).json() == wallet
        assert b.get('/api/session').json()['context_generation'] == a.get('/api/session').json()['context_generation']


@pytest.mark.parametrize('https', [False, True])
def test_server_cookie_flags_and_missing_forged_identifiers(https):
    with TestClient(app, base_url=('https' if https else 'http')+'://testserver') as client:
        response = client.get('/landing.html', headers={'X-Forwarded-Proto': 'https'})
        cookie = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/' in cookie
        assert ('; secure' in cookie) is https
        first = client.cookies.get(COOKIE_NAME)
        assert len(first) >= 40
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, 'attacker-chosen', domain='testserver.local', path='/')
        response = client.get('/api/session')
        assert response.status_code == 200
        assert client.cookies.get(COOKIE_NAME) not in {'attacker-chosen', first}
        assert 'attacker-chosen' not in session_store.registry.entries
        assert response.json()['shared_session'] is False
        assert response.headers['cache-control'] == 'no-store'


def test_expired_cookie_gets_new_identifier_generation_and_stops_all_workers(clocked):
    registry, now = clocked
    with TestClient(app) as client:
        original = client.get('/api/session').json()
        identifier, old = client.cookies.get(COOKIE_NAME), context(client)
        handle = client.post('/api/labs/network').json()['lab_handle']
        lab = old.lab_networks[handle]
        workers = [n._worker for n in old.network.nodes.values()] + [n._worker for n in lab['network'].nodes.values()]
        now[0] = 11
        renewed = client.get('/api/session').json()
        assert identifier not in registry.entries
        assert client.cookies.get(COOKIE_NAME) != identifier
        assert renewed['reset_count'] == original['reset_count'] == 0
        assert renewed['context_generation'] != original['context_generation']
        assert all(not t.is_alive() for t in workers)
        lab['timer'].join(timeout=1)
        assert not lab['timer'].is_alive() and not old.lab_keys and not old.lab_networks
        assert client.get('/api/labs/network/'+handle).status_code == 404


def test_restart_cannot_restore_old_generation_even_at_reset_zero(clocked):
    registry, _ = clocked
    with TestClient(app) as client:
        before = client.get('/api/session').json()
        cookie = client.cookies.get(COOKIE_NAME)
        registry.shutdown()
        registry.start()
        after = client.get('/api/session').json()
        assert client.cookies.get(COOKIE_NAME) != cookie
        assert before['reset_count'] == after['reset_count'] == 0
        assert before['context_generation'] != after['context_generation']


def test_lab_handle_ownership_and_guided_reset_preserves_own_labs():
    with TestClient(app) as a, TestClient(app) as b:
        key = a.post('/api/labs/signatures/keys').json()['key_handle']
        handle = a.post('/api/labs/network').json()['lab_handle']
        tamper = a.post('/api/labs/tamper').json()['lab_id']
        for route in ['/api/labs/network/'+handle, '/api/labs/tamper/'+tamper]:
            assert b.get(route).status_code == 404
        for suffix in ['/mine', '/sync', '/nodes/Node-3/status']:
            assert b.post('/api/labs/network/'+handle+suffix, json={'online': False}).status_code == 404
        assert b.post('/api/labs/tamper/'+tamper+'/edit', json={'title': 'Foreign edit'}).status_code == 404
        assert b.post('/api/labs/tamper/'+tamper+'/sync').status_code == 404
        assert b.delete('/api/labs/tamper/'+tamper).json() == {'cleared': False}
        assert b.post('/api/labs/network/'+handle+'/reset').json() == {'cleared': False}
        assert b.post('/api/labs/signatures/sign', json={'key_handle': key, 'message': 'x'}).status_code == 404
        assert b.post('/api/labs/signatures/keys/'+key+'/reset').json() == {'cleared': False}
        a.post('/api/session/reset')
        assert a.get('/api/labs/network/'+handle).status_code == 200
        assert a.get('/api/labs/tamper/'+tamper).status_code == 200
        assert a.post('/api/labs/signatures/sign', json={'key_handle': key, 'message': 'x'}).status_code == 200


def test_capacity_controlled_no_active_eviction_and_expiry_cleanup(clocked):
    registry, now = clocked
    registry.capacity = 1
    identifier, old, _ = registry.acquire(None)
    with bind_session(old):
        network = get_network()
    now[0] = 100
    registry.cleanup()
    assert registry.entries[identifier] is old and all(n._worker.is_alive() for n in network.nodes.values())
    with TestClient(app) as foreign:
        response = foreign.get('/api/session')
        assert response.status_code == 503 and response.json()['detail']['code'] == 'session_capacity'
        assert response.headers['retry-after'] == '60' and 'set-cookie' not in response.headers
    # Shutdown also pins the active request until its lease is released.
    assert all(n._worker.is_alive() for n in network.nodes.values())
    registry.release(identifier, old)
    assert all(not n._worker.is_alive() for n in network.nodes.values())
    registry.start()
    with TestClient(app) as client:
        assert client.get('/api/session').status_code == 200


def test_idle_cleanup_frees_capacity_without_evicting_live_session(clocked):
    registry, now = clocked
    registry.capacity = 1
    with TestClient(app) as a, TestClient(app) as b:
        a.get('/api/session')
        old = context(a)
        network = old.network
        now[0] = 11
        assert b.get('/api/session').status_code == 200
        assert len(registry.entries) == 1
        assert all(not n._worker.is_alive() for n in network.nodes.values())


def test_long_request_uses_own_lock_and_cannot_expire(clocked, monkeypatch):
    registry, now = clocked
    started, release = threading.Event(), threading.Event()
    original = Node.mine_pending
    def held(node):
        started.set()
        assert release.wait(timeout=5)
        return original(node, difficulty=1)
    monkeypatch.setattr(Node, 'mine_pending', held)
    with TestClient(app) as a, TestClient(app) as b:
        credential = issue(a)
        assert submit(a, credential).json()['accepted']
        a_ctx = context(a)
        b_wallet = b.post('/api/wallets', json={'name': 'B remains responsive'}).json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            mining = pool.submit(a.post, '/api/mining/pow', json={'node_id': 'Node-1'})
            assert started.wait(timeout=2)
            try:
                reading = pool.submit(b.get, '/api/wallets/'+b_wallet['id'])
                assert reading.result(timeout=2).status_code == 200
                now[0] = 11
                registry.cleanup()
                assert a_ctx in registry.entries.values() and a_ctx.active == 1
            finally:
                release.set()
            assert mining.result(timeout=5).json()['mined']
            assert a_ctx.active == 0 and a_ctx.last_used == 11


def test_failed_network_initialization_does_not_leak_workers(monkeypatch):
    from api import network_store
    created = []
    original = network_store.Network.create_node
    def fail_second(network, *args):
        if created:
            raise RuntimeError('Node initialization fixture failure')
        node = original(network, *args)
        created.append(node)
        return node
    monkeypatch.setattr(network_store.Network, 'create_node', fail_second)
    try:
        with TestClient(app) as client:
            with pytest.raises(RuntimeError, match='initialization fixture failure'):
                client.get('/api/network')
            assert all(not node._worker.is_alive() for node in created)
    finally:
        for node in created:
            node.stop()
