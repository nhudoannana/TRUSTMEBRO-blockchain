"""Real disposable consensus runs; no shared journey network mutations."""
import json

import pytest

from api import network_store, wallet_store
from blockchain.node import Network, Node
from blockchain.mining import is_acceptable_pow
from blockchain.transaction import verify_transaction
from tests.test_mempool_api import client, issue, submit


def run(client, mode='pow', **options):
    return client.post('/api/labs/consensus/run', json={
        'mode': mode, 'holder_name': 'Demo', 'title': 'Certificate',
        'issue_date': '2026-10-01', **options})


@pytest.fixture
def lab_nodes(monkeypatch):
    nodes = []
    original = Network.create_node
    def capture(network, *args, **kwargs):
        node = original(network, *args, **kwargs)
        nodes.append(node)
        return node
    monkeypatch.setattr(Network, 'create_node', capture)
    return nodes


def test_equivalent_real_blocks_identity_and_cleanup(client, lab_nodes):
    responses = [run(client, mode) for mode in ['pow', 'pos']]
    assert all(response.status_code == 200 for response in responses)
    results = [response.json() for response in responses]
    assert len(lab_nodes) == 2
    first, second = results
    for result, node in zip(results, lab_nodes):
        assert result['created'] and result['submission']['accepted']
        block = node.blockchain.get_latest_block()
        assert result['block'] == block.to_dict()
        assert result['transaction'] == block.transactions[0].to_dict()
        assert verify_transaction(block.transactions[0])[0]
        assert result['transaction_ids'] == [block.transactions[0].tx_id]
        assert node.height == 1 and result['pending_count'] == 0
        assert node.blockchain.is_chain_valid(pos_registry=node.network.pos_registry)[0]
        assert result['chain_valid'] is True
        assert result['seconds'] >= 0
        assert result['elapsed_scope'] == f"{'mine' if result['mode'] == 'pow' else 'forge_pos'}_pending call"
        assert not node._worker.is_alive()
        assert 'private' not in json.dumps(result).lower() and 'BEGIN' not in json.dumps(result)
    assert lab_nodes[0].network is not lab_nodes[1].network
    for field in ['issuer_name', 'holder_name', 'title', 'issue_date', 'claims_root']:
        assert first['transaction']['payload'][field] == second['transaction']['payload'][field]
    assert first['transaction']['tx_id'] != second['transaction']['tx_id']
    assert first['transaction']['payload']['credential_id'] != second['transaction']['payload']['credential_id']
    assert is_acceptable_pow(lab_nodes[0].blockchain.get_latest_block())
    assert first['block']['difficulty'] == 3
    assert first['attempts'] == first['backend_timing']['attempts']
    assert first['block']['nonce'] == first['backend_timing']['nonce']
    assert first['signer'] is None
    block = lab_nodes[1].blockchain.get_latest_block()
    registry = lab_nodes[1].network.pos_registry
    expected = registry.select_validator(block.height, lab_nodes[1].network.consensus_seed,
                                         block.header.previous_hash)
    signer = second['signer']
    assert signer['address'] == block.header.validator_address == expected.address
    assert signer['public_key_hex'] == expected.public_key_hex
    assert signer['stake'] == expected.stake
    assert signer['selection_weight'] == pytest.approx(expected.stake / registry.total_active_stake())
    assert signer['public_key_hex'] != second['issuer']['public_key_hex']
    assert second['issuer']['public_key_hex'] == second['transaction']['sender_public_key']
    assert second['attempts'] is None
    assert second['stake_mode'] == registry.stake_mode and second['seed'] == lab_nodes[1].network.consensus_seed


def test_guided_session_and_stake_unchanged(client, lab_nodes, monkeypatch):
    # Preserve an actual pending guided credential, not just an empty network.
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    shared = network_store.get_network()
    registry = shared.pos_registry
    def snapshot():
        return (wallet_store.list_wallets(), dict(network_store.signed_credentials),
                client.get('/api/session').json(), client.get('/api/network').json(),
                client.get('/api/mempool').json(),
                client.get('/api/consensus/pos?node_id=Node-1').json())
    # Let the guided transaction's asynchronous queue propagation finish first.
    from tests.test_mempool_api import wait_for_counts
    wait_for_counts(client, [1, 1, 1])
    before = snapshot()
    from blockchain.pos import PoSRegistry
    def forbidden(*args, **kwargs):
        pytest.fail('Lab must not sync/change stake')
    monkeypatch.setattr(PoSRegistry, 'sync_with_blockchain', forbidden)
    for mode in ['pow', 'pos']:
        assert run(client, mode).json()['created']
    assert snapshot() == before
    assert network_store.get_network() is shared and shared.pos_registry is registry
    for node in lab_nodes:
        assert [v.stake for v in node.network.pos_registry.validators.values()] == [500, 300, 200]
        assert all(v.credentials_issued == 0 for v in node.network.pos_registry.validators.values())
        assert not node._worker.is_alive()


@pytest.mark.parametrize('mode', ['pow', 'pos'])
def test_empty_offline_and_rejections_keep_real_reasons(client, lab_nodes, monkeypatch, mode):
    empty = run(client, mode, include_sample=False).json()
    assert not empty['created'] and empty['reason'] == (
        'Mempool trống — không có TX để mine' if mode == 'pow'
        else 'Mempool trống — không có TX để tạo khối PoS')
    assert empty['block'] is None and empty['transaction'] is None
    offline = run(client, mode, node_online=False).json()
    assert not offline['created'] and offline['stage'] == 'submission'
    assert offline['reason'] == f"Lab-{mode.upper()} đang OFFLINE"
    assert offline['node_status'] == 'OFFLINE'
    def reject(*args):
        return False, 'fixture: backend candidate rejection'
    monkeypatch.setattr(Node, '_validate_candidate', reject)
    rejected = run(client, mode).json()
    assert not rejected['created'] and rejected['reason'] == 'fixture: backend candidate rejection'
    assert rejected['pending_count'] == 1
    assert all(not node._worker.is_alive() for node in lab_nodes)


def test_failed_backend_cleans_workers_and_next_run_is_fresh(client, lab_nodes, monkeypatch):
    original = Node.mine_pending
    def fail(node):
        raise RuntimeError('fixture backend failure')
    monkeypatch.setattr(Node, 'mine_pending', fail)
    response = run(client)
    assert response.status_code == 500
    assert not lab_nodes[0]._worker.is_alive()
    assert len(lab_nodes[0].mempool.get_transactions()) == 1
    monkeypatch.setattr(Node, 'mine_pending', original)
    assert run(client).json()['created']
    assert lab_nodes[1].network is not lab_nodes[0].network
    assert lab_nodes[1].height == 1
    assert not lab_nodes[1]._worker.is_alive()


def test_no_eligible_validator_reuses_backend_reason(client, lab_nodes, monkeypatch):
    original = Network.create_node
    def inactive(network, *args, **kwargs):
        node = original(network, *args, **kwargs)
        for validator in network.pos_registry.validators.values():
            validator.is_active = False
        return node
    monkeypatch.setattr(Network, 'create_node', inactive)
    result = run(client, 'pos').json()
    assert not result['created'] and result['signer'] is None
    assert result['reason'] == 'Không tìm thấy validator hợp lệ trong mạng PoS'
    assert result['pending_count'] == 1
    assert all(v['selection_weight'] == 0 and not v['eligible'] for v in result['validators'])
    assert not lab_nodes[0]._worker.is_alive()


def test_existing_submission_and_block_broadcast_only_once(client, lab_nodes, monkeypatch):
    broadcasts = []
    original = Network.broadcast
    def capture(network, sender, message):
        broadcasts.append((network, message.msg_type))
        return original(network, sender, message)
    monkeypatch.setattr(Network, 'broadcast', capture)
    for mode in ['pow', 'pos']:
        assert run(client, mode).json()['created']
    for node in lab_nodes:
        assert [kind for network, kind in broadcasts if network is node.network] == ['TX', 'BLOCK']


def test_no_attempt_count_is_invented(client, monkeypatch):
    original = Node.mine_pending
    def no_count(node):
        block, result = original(node)
        del result['attempts']
        return block, result
    monkeypatch.setattr(Node, 'mine_pending', no_count)
    result = run(client).json()
    assert result['created'] and result['attempts'] is None
    assert 'attempts' not in result['backend_timing']


@pytest.mark.parametrize('body', [{}, {'mode': 'fake'}, {'mode': 'pow', 'node_online': 'false'},
    {'mode': 'pos', 'include_sample': 0}, {'mode': 'pow', 'holder_name': ' '},
    {'mode': 'pos', 'title': 'x' * 201}, {'mode': 'pow', 'issue_date': '2026-02-30'},
    {'mode': 'pos', 'validator': 'manual'}, {'mode': 'pow', 'difficulty': 0}])
def test_request_validation(client, body):
    assert client.post('/api/labs/consensus/run', json=body).status_code == 422
