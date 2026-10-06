"""Real request-scoped attacks; no persistent attack network or private keys."""
import json
import pytest
from api.session_store import current_session
from blockchain.node import Network
from api import wallet_api, session_store
from tests.session_helpers import SessionTestClient
from tests.test_mempool_api import issue, submit, wait_for_counts
from tests.test_mempool_api import client


@pytest.mark.parametrize('scenario', ['tamper', 'impersonation', 'replay'])
def test_attack_baseline_and_actual_outcome(client, scenario):
    response = client.post('/api/labs/attacks/run', json={'scenario': scenario})
    assert response.status_code == 200
    data = response.json()
    assert data['baseline']['verification']['valid']
    assert data['baseline']['submission']['accepted']
    assert not data['attack']['submission']['accepted']
    assert data['attack']['submission']['reason']
    assert data['failure_layer'] == {
        'tamper': 'transaction_hash', 'impersonation': 'issuer_authorization',
        'replay': 'duplicate_submission'}[scenario]
    assert 'private' not in json.dumps(data).lower()
    original, attack = data['baseline']['transaction'], data['attack']['transaction']
    if scenario == 'tamper':
        assert attack['signature'] == original['signature']
        assert attack['tx_id'] == original['tx_id']
        assert attack['payload']['title'] != original['payload']['title']
        assert data['attack']['verification']['signature_checked'] is False
        assert 'tx_id' in data['attack']['verification']['reason']
    elif scenario == 'impersonation':
        assert data['attack']['verification']['valid']
        assert data['attack']['verification']['signature_checked']
        assert attack['sender_public_key'] == data['attacker']['public_key_hex']
        assert attack['sender_public_key'] != data['authorized_issuer']['public_key_hex']
        assert attack['payload']['issuer_name'] == original['payload']['issuer_name']
        assert 'unauthorized' in data['attack']['submission']['reason']
    else:
        assert attack == original
        assert 'trùng tx_id' in data['attack']['submission']['reason']


@pytest.fixture
def attack_nodes(monkeypatch):
    nodes = []
    original = Network.create_node
    def capture(network, *args, **kwargs):
        node = original(network, *args, **kwargs)
        nodes.append(node)
        return node
    monkeypatch.setattr(Network, 'create_node', capture)
    return nodes


def test_isolation_repeated_runs_and_no_retained_state(client, attack_nodes):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    wait_for_counts(client, [1, 1, 1])
    paths = ['/api/wallets', '/api/session', '/api/network', '/api/mempool',
             '/api/explorer/blocks?node_id=Node-1']
    before = [client.get(path).json() for path in paths]
    owner = current_session()
    key = client.post('/api/labs/signatures/keys').json()['key_handle']
    retained = client.post('/api/labs/network').json()['lab_handle']
    lab_before = client.get('/api/labs/network/' + retained).json()
    guided = owner.network
    # The outer fixture owns application lifespan; the second cookie jar must
    # not start/stop the same application's registry midway through this test.
    other = SessionTestClient(wallet_api.app)
    try:
        for scenario in ['tamper', 'impersonation', 'replay', 'replay']:
            data = client.post('/api/labs/attacks/run', json={'scenario': scenario}).json()
            assert data['context_generation'] == before[1]['context_generation']
            response = other.post('/api/labs/attacks/run', json={'scenario': scenario})
            assert response.status_code == 200
            assert response.json()['baseline']['transaction']['tx_id'] != data['baseline']['transaction']['tx_id']
            assert 'lab_handle' not in data and 'lab_id' not in data
            assert other.get('/api/labs/network/' + retained).status_code == 404
    finally:
        other.close()
    assert [client.get(path).json() for path in paths] == before
    assert client.get('/api/labs/network/' + retained).json()['nodes'] == lab_before['nodes']
    assert owner.network is guided and key in owner.lab_keys
    assert len(owner.lab_networks) == 1
    isolated = [n for n in attack_nodes if n.node_id == 'Attack-Node']
    assert len(isolated) == 8
    assert len({id(n.network) for n in isolated}) == 8
    assert all(not n._worker.is_alive() for n in isolated)
    assert all(n.height == 0 and len(n.mempool.get_transactions()) == 1 for n in isolated)


@pytest.mark.parametrize('body', [{}, {'scenario': 'other'}, {'scenario': 'tamper', 'edited_title': ''},
    {'scenario': 'tamper', 'edited_title': '   '}, {'scenario': 'tamper', 'edited_title': 'x' * 201},
    {'scenario': 'tamper', 'edited_title': 'Chứng chỉ mẫu lab'}, {'scenario': 'replay', 'node_id': 'Node-1'}])
def test_invalid_input_creates_no_workers(client, attack_nodes, body):
    assert client.post('/api/labs/attacks/run', json=body).status_code == 422
    assert not attack_nodes


def test_exception_and_baseline_failure_cleanup(client, attack_nodes, monkeypatch):
    from blockchain.node import Node
    original = Node.submit_transaction
    def fail(*args):
        raise RuntimeError('test failure')
    monkeypatch.setattr(Node, 'submit_transaction', fail)
    response = client.post('/api/labs/attacks/run', json={'scenario': 'replay'})
    assert response.status_code == 500
    assert all(not n._worker.is_alive() for n in attack_nodes)
    monkeypatch.setattr(Node, 'submit_transaction', lambda *args: (False, 'Exact baseline rejection'))
    response = client.post('/api/labs/attacks/run', json={'scenario': 'tamper'})
    assert response.status_code == 409 and response.json()['detail'] == 'Exact baseline rejection'
    assert all(not n._worker.is_alive() for n in attack_nodes)
    monkeypatch.setattr(Node, 'submit_transaction', original)


def test_session_expiry_never_retains_attack_workers(client, attack_nodes):
    response = client.post('/api/labs/attacks/run', json={'scenario': 'replay'})
    old = response.json()['context_generation']
    context = current_session()
    context.last_used -= session_store.IDLE_SECONDS + 1
    response = client.post('/api/labs/attacks/run', json={'scenario': 'tamper'})
    assert response.status_code == 200 and response.json()['context_generation'] != old
    assert all(not node._worker.is_alive() for node in attack_nodes)


@pytest.mark.parametrize('scenario,expected_calls', [('tamper', 2), ('impersonation', 4), ('replay', 4)])
def test_failure_layer_matches_executed_signature_checks(client, monkeypatch, scenario, expected_calls):
    from blockchain import transaction
    original = transaction.verify_signature
    signatures = []
    def observe(*args):
        signatures.append(args)
        return original(*args)
    monkeypatch.setattr(transaction, 'verify_signature', observe)
    result = client.post('/api/labs/attacks/run', json={'scenario': scenario})
    assert result.status_code == 200
    # Baseline is checked explicitly and by Node admission. Tampering never
    # reaches ECDSA on either attack check; other scenarios do on both checks.
    assert len(signatures) == expected_calls


def test_node_setup_exception_cleans_registered_worker(client, monkeypatch):
    original = Network.create_node
    nodes = []
    def fail(network, *args, **kwargs):
        node = original(network, *args, **kwargs)
        if args[0] != 'Attack-Node':
            return node
        nodes.append(node)
        raise RuntimeError('setup failed after registration')
    monkeypatch.setattr(Network, 'create_node', fail)
    assert client.post('/api/labs/attacks/run', json={'scenario': 'tamper'}).status_code == 500
    assert len(nodes) == 1 and not nodes[0]._worker.is_alive()
