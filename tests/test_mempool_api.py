"""Step D API checks; real queue workers, no mining or browser."""
from api.session_store import current_session


import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest
from tests.session_helpers import SessionTestClient as TestClient

from api import network_store, wallet_store
from api.wallet_api import app
from blockchain.wallet import Wallet
from blockchain.block import Block


@pytest.fixture
def client():
    with TestClient(app) as client:
        client.post('/api/session/reset')
        yield client
        client.post('/api/session/reset')


def issue(client):
    wallet = client.get('/api/wallets').json()[0]
    response = client.post('/api/credentials', json={
        'issuer_wallet_id': wallet['id'], 'holder_name': 'Demo',
        'title': 'Certificate', 'issue_date': '2026-10-01',
    })
    assert response.status_code == 201
    return response.json()


def submit(client, credential, node='Node-1'):
    return client.post('/api/mempool', json={'credential_id': credential['credential_id'], 'node_id': node})


def snapshots(client):
    response = client.get('/api/mempool')
    assert response.status_code == 200
    return response.json()['nodes']


def wait_for_counts(client, counts):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        rows = snapshots(client)
        if [r['pending_count'] for r in rows] == counts:
            return rows
        time.sleep(0.02)
    pytest.fail(f'Propagation timeout: {rows}')


def test_accept_exact_transaction_broadcast_once_and_no_height_change(client, monkeypatch):
    credential = issue(client)
    net = network_store.get_network()
    original = net.broadcast
    broadcasts = []
    def broadcast(sender, message):
        broadcasts.append((sender, message.payload))
        original(sender, message)
    monkeypatch.setattr(net, 'broadcast', broadcast)
    stored = current_session().signed_credentials[credential['credential_id']][1]
    result = submit(client, credential)
    assert result.status_code == 200
    data = result.json()
    assert data['accepted'] is True
    assert data['reason'] == 'Accepted — đã thêm vào Mempool và broadcast'
    assert data['reason_source'] == 'backend'
    assert data['tx_id'] == stored.tx_id
    assert len(broadcasts) == 1 and broadcasts[0][1] is stored
    rows = wait_for_counts(client, [1, 1, 1])
    for row in rows:
        assert row['status'] == 'ONLINE'
        assert row['transactions'] == [stored.to_dict()]
    assert all(node.height == 0 for node in net.nodes.values())
    assert 'private_key' not in result.text


def test_resubmit_has_no_second_copy(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    result = submit(client, credential, 'Node-2').json()
    assert not result['accepted']
    assert result['reason_source'] == 'adapter'
    wait_for_counts(client, [1, 1, 1])


def replacement(credential):
    """Fixture only: alternate signed tx_id for the SAME credential_id."""
    with current_session().lock:
        cred, original = current_session().signed_credentials[credential['credential_id']]
        tx = deepcopy(original)
        tx.nonce += '-alternate'
        wallet = wallet_store.get_wallet(credential['issuer_wallet_id'])
        tx.sign(Wallet(wallet_store.get_private_key_pem(wallet['id']), wallet['public_key_hex'], wallet['address']))
        assert tx.tx_id != original.tx_id
        current_session().signed_credentials[credential['credential_id']] = (cred, tx)
        return tx


def test_different_tx_id_same_credential_blocked_across_nodes(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    replacement(credential)
    result = submit(client, credential, 'Node-3').json()
    assert not result['accepted']
    assert result['reason_source'] == 'adapter'
    assert 'credential_id' in result['reason']
    rows = wait_for_counts(client, [1, 1, 1])
    assert all(row['transactions'][0]['tx_id'] == credential['transaction']['tx_id'] for row in rows)


def test_existing_peer_chain_blocks_issue(client):
    credential = issue(client)
    net = network_store.get_network()
    tx = current_session().signed_credentials[credential['credential_id']][1]
    peer = net.nodes['Node-3']
    with peer._state_lock:
        # Fixture represents already-recorded ISSUE; no mining API is invoked.
        peer.blockchain.chain.append(Block([deepcopy(tx)], 1, peer.blockchain.get_latest_block().compute_hash()))
    replacement(credential)
    result = submit(client, credential).json()
    assert not result['accepted'] and result['reason_source'] == 'adapter'
    assert 'chain' in result['reason']
    assert all(row['pending_count'] == 0 for row in snapshots(client))


def test_invalid_signature_preserves_backend_reason(client):
    credential = issue(client)
    net = network_store.get_network()
    tx = current_session().signed_credentials[credential['credential_id']][1]
    tx.signature = '00'
    expected_ok, expected_reason = net.nodes['Node-1'].submit_transaction(tx)
    assert not expected_ok
    response = submit(client, credential).json()
    assert response['accepted'] is False
    assert response['reason_source'] == 'backend'
    assert response['reason'] == expected_reason
    assert all(row['pending_count'] == 0 for row in snapshots(client))


def test_unknown_node_and_credential(client):
    credential = issue(client)
    response = submit(client, credential, 'missing')
    assert response.status_code == 404 and response.json()['detail']['code'] == 'node_not_found'
    response = submit(client, {'credential_id': 'missing'})
    assert response.status_code == 404 and response.json()['detail']['code'] == 'credential_not_found'


def test_offline_node_and_offline_peer(client):
    credential = issue(client)
    net = network_store.get_network()
    net.nodes['Node-3'].go_offline()
    response = submit(client, credential, 'Node-3').json()
    assert not response['accepted']
    assert response['reason_source'] == 'backend'
    assert response['reason'] == 'Node-3 đang OFFLINE'
    assert submit(client, credential).json()['accepted']
    rows = wait_for_counts(client, [1, 1, 0])
    assert rows[2]['status'] == 'OFFLINE'


def test_reset_clears_pending_and_signed_store(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    old = network_store.get_network()
    generation = client.get('/api/mempool').json()['reset_count']
    client.post('/api/session/reset')
    assert not current_session().signed_credentials
    assert client.get('/api/mempool').json()['reset_count'] == generation + 1
    assert all(row['pending_count'] == 0 for row in snapshots(client))
    assert submit(client, credential).status_code == 404
    assert all(not node._worker.is_alive() for node in old.nodes.values())


def test_concurrent_submission_only_admits_once(client):
    credential = issue(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda node: submit(client, credential, node).json(), ['Node-1', 'Node-2']))
    assert sorted(result['accepted'] for result in results) == [False, True]
    wait_for_counts(client, [1, 1, 1])


def test_admission_holds_all_worker_locks(client, monkeypatch):
    credential = issue(client)
    net = network_store.get_network()
    node = net.nodes['Node-1']
    original = node.submit_transaction
    def submit_under_locks(tx):
        assert all(peer._state_lock._is_owned() for peer in net.nodes.values())
        return original(tx)
    monkeypatch.setattr(node, 'submit_transaction', submit_under_locks)
    assert submit(client, credential).json()['accepted']


@pytest.mark.parametrize('body', [
    {}, {'credential_id':' ', 'node_id':'Node-1'}, {'credential_id':'id', 'node_id':''},
    {'credential_id':'id', 'node_id':'Node-1', 'payload':{}},
    {'credential_id':'x'*201, 'node_id':'Node-1'},
])
def test_reject_invalid_or_replacement_input(client, body):
    assert client.post('/api/mempool', json=body).status_code == 422
