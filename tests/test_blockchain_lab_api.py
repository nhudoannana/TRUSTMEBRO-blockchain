"""Independent text chains use the production models and validation rules."""
from copy import deepcopy
import json
import threading

import pytest

from api import wallet_api, network_store, wallet_store
from blockchain.blockchain import Blockchain
from blockchain.mining import is_acceptable_pow
from blockchain.transaction import verify_transaction
from tests.test_block_lab_api import build, mine, restore
from tests.test_mempool_api import client, issue, submit, wait_for_counts


def init(client):
    response = client.post('/api/labs/blockchain/init')
    assert response.status_code == 200, response.text
    return response.json()


def action(client, action, chain, **fields):
    response = client.post('/api/labs/blockchain/' + action, json={'chain': chain, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def sample_chain(client, count=3):
    state = init(client)
    for n in range(count):
        state = action(client, 'add', state['chain'], data=f'Block data {n} 🌏', difficulty=2)
        assert state['mining']['completed']
    return state


def backend_chain(records):
    chain = Blockchain()
    for record in records[1:]:
        block = restore(record)
        block.height = record['height']
        chain.chain.append(block)
    return chain


def test_genesis_repeated_text_blocks_actual_headers_and_validation(client):
    state = init(client)
    genesis = Blockchain().chain[0]
    assert state['chain'][0]['header']['previous_hash'] == '0' * 64
    assert state['chain'][0]['stored_hash'] == genesis.compute_hash()
    assert state['chain'][0]['transaction'] is None
    assert state['validation']['valid']
    for text in ('', '  arbitrary\ntext 🌏  ', '{"this": "is text, not a transaction"}'):
        state = action(client, 'add', state['chain'], data=text, difficulty=2)
        chain = backend_chain(state['chain'])
        assert chain.is_chain_valid()[0]
        block = chain.chain[-1]
        assert is_acceptable_pow(block)
        assert verify_transaction(block.transactions[0])[0]
        assert block.transactions[0].payload['lab_data'] == text
        assert state['chain'][-1]['header']['merkle_root'] == block.header.merkle_root
        assert state['chain'][-1]['stored_hash'] == block.compute_hash()
        assert block.header.previous_hash == chain.chain[-2].compute_hash()
        assert state['mining']['attempts'] == block.header.nonce + 1
        assert state['mining']['seconds'] >= 0
    checked = action(client, 'validate', state['chain'])
    assert all(b['own_validation']['valid'] and b['link_valid'] and b['prefix_valid'] for b in checked['blocks'])
    assert 'private' not in json.dumps(state).lower()


def test_optional_headers_and_recorded_versus_computed_transaction_hash(client):
    initial = init(client)
    state = action(client, 'add', initial['chain'], data='Custom header', difficulty=2,
                   version=2, timestamp='2026-10-04T12:00:00+07:00')
    header = state['chain'][1]['header']
    assert header['version'] == 2 and header['timestamp'] == '2026-10-04T12:00:00+07:00'
    assert header['previous_hash'] == initial['chain'][0]['stored_hash']
    tx = backend_chain(state['chain']).chain[1].transactions[0]
    assert state['blocks'][1]['computed_transaction_hash'] == tx.tx_id == tx.compute_hash()
    edited = action(client, 'edit', state['chain'], height=1, data='Changed content')
    tx = backend_chain(edited['chain']).chain[1].transactions[0]
    assert edited['blocks'][1]['computed_transaction_hash'] == tx.compute_hash()
    assert edited['blocks'][1]['computed_transaction_hash'] != tx.tx_id
    assert client.post('/api/labs/blockchain/add', json={
        'chain': initial['chain'], 'data': 'Cannot override tip', 'previous_hash': 'a' * 64}).status_code == 422


def test_middle_edit_keeps_evidence_descendants_and_actual_backend_reason(client):
    state = sample_chain(client)
    records = deepcopy(state['chain'])
    edited = action(client, 'edit', records, height=2, data='<img src=x> altered middle')
    assert edited['chain'][1] == records[1] and edited['chain'][3] == records[3]
    target = edited['chain'][2]
    assert target['header'] == records[2]['header']
    assert target['stored_hash'] == records[2]['stored_hash']
    for key in ('tx_id', 'signature', 'nonce', 'timestamp'):
        assert target['transaction'][key] == records[2]['transaction'][key]
    result = backend_chain(edited['chain']).is_chain_valid()
    assert result == (False, edited['validation']['invalid_height'], edited['validation']['reason'])
    assert edited['blocks'][1]['prefix_valid']
    assert not edited['blocks'][2]['own_validation']['checks']['transaction']['valid']
    assert edited['blocks'][3]['own_validation']['valid']  # Its own hash/proof is unchanged.
    assert edited['blocks'][3]['link_valid'] and not edited['blocks'][3]['prefix_valid']
    checked = action(client, 'validate', edited['chain'])
    assert checked['validation'] == edited['validation']
    assert client.post('/api/labs/blockchain/add', json={
        'chain': edited['chain'], 'data': 'Do not extend an invalid chain'}).status_code == 409


def test_recompute_breaks_next_reference_without_resigning_or_remining(client):
    state = sample_chain(client)
    edited = action(client, 'edit', state['chain'], height=1, data='Changed first block')
    before = deepcopy(edited['chain'])
    recomputed = action(client, 'recompute', before, height=1)
    target = recomputed['chain'][1]
    assert target['transaction']['tx_id'] != before[1]['transaction']['tx_id']
    assert target['header']['merkle_root'] != before[1]['header']['merkle_root']
    assert target['stored_hash'] != before[1]['stored_hash']
    assert target['transaction']['signature'] == before[1]['transaction']['signature']
    assert target['header']['nonce'] == before[1]['header']['nonce']
    assert recomputed['chain'][2:] == before[2:]
    block = backend_chain(recomputed['chain']).chain[1]
    assert not verify_transaction(block.transactions[0])[0]  # Old signature cannot authenticate a new tx ID.
    assert recomputed['blocks'][2]['own_validation']['valid']
    assert not recomputed['blocks'][2]['link_valid']
    assert not recomputed['blocks'][3]['prefix_valid']
    assert recomputed['blocks'][3]['link_valid'] and recomputed['blocks'][3]['own_validation']['valid']
    assert not recomputed['validation']['valid']
    assert recomputed['change']['before'] == before[1]


@pytest.mark.parametrize('fields', [
    {'height': 0, 'data': 'genesis'}, {'height': 1, 'data': 'same'},
    {'height': True, 'data': 'bad'}, {'height': 12, 'data': 'missing'},
])
def test_rejected_edit_targets(client, fields):
    state = action(client, 'add', init(client)['chain'], data='same', difficulty=2)
    response = client.post('/api/labs/blockchain/edit', json={'chain': state['chain'], **fields})
    assert response.status_code in (422, 404)
    assert action(client, 'validate', state['chain'])['validation']['valid']


def test_input_bounds_genesis_integrity_and_incomplete_no_append(client, monkeypatch):
    state = init(client)
    for fields in ({'data': 'x' * 4001}, {'data': 32}, {'data': 'x', 'difficulty': 1},
                   {'data': 'x', 'difficulty': 6}, {'data': 'x', 'difficulty': True},
                   {'data': 'x', 'version': 0}, {'data': 'x', 'version': True},
                   {'data': 'x', 'timestamp': ''}, {'data': 'x', 'timestamp': '2026-01-01'},
                   {'data': 'x', 'timestamp': 'bad timestamp'},
                   {'data': '\ud800'}):
        response = client.post('/api/labs/blockchain/add',
                               content=json.dumps({'chain': state['chain'], **fields}),
                               headers={'Content-Type': 'application/json'})
        assert response.status_code == 422
    bad = deepcopy(state['chain'])
    bad[0]['header']['nonce'] += 1
    assert client.post('/api/labs/blockchain/validate', json={'chain': bad}).status_code == 422
    assert client.post('/api/labs/blockchain/validate', json={'chain': state['chain'] * 14}).status_code == 422
    monkeypatch.setattr(wallet_api, '_BLOCK_LAB_MAX_ATTEMPTS', 0)
    limited = action(client, 'add', state['chain'], data='bounded')
    assert limited['chain'] == state['chain'] and limited['validation']['valid']
    assert not limited['mining']['completed'] and limited['mining']['attempts'] == 0
    assert limited['candidate']['height'] == 1


def test_length_limit_busy_and_recompute_noop(client):
    state = sample_chain(client, 12)
    response = client.post('/api/labs/blockchain/add', json={'chain': state['chain'], 'data': '13th'})
    assert response.status_code == 422
    assert client.post('/api/labs/blockchain/recompute', json={'chain': state['chain'], 'height': 1}).status_code == 409
    wallet_api._blockchain_lab_mining_lock.acquire()
    try:
        assert client.post('/api/labs/blockchain/add', json={'chain': init(client)['chain'], 'data': 'busy'}).status_code == 429
    finally:
        wallet_api._blockchain_lab_mining_lock.release()


def test_isolation_reset_repeat_no_workers_and_guided_validation(client, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    wait_for_counts(client, [1, 1, 1])
    other = mine(client, build(client, data='Independent Block')['candidate'])
    key = client.post('/api/labs/signatures/keys').json()
    lab = client.post('/api/labs/network').json()['lab_handle']
    def capture():
        network = network_store.get_network()
        return deepcopy(([[b.to_dict() for b in n.blockchain.chain] for n in network.nodes.values()],
                         [[t.to_dict() for t in n.mempool.get_transactions()] for n in network.nodes.values()],
                         wallet_store._store, list(network_store.signed_credentials),
                         network_store.get_reset_count(), client.get(f'/api/labs/network/{lab}').json()['nodes'],
                         dict(wallet_api._lab_keys)))
    baseline, workers = capture(), set(threading.enumerate())
    def forbidden(*args, **kwargs):
        raise AssertionError('No Network is needed by this experiment')
    monkeypatch.setattr(wallet_api, 'Network', forbidden)
    for _ in range(3):
        state = sample_chain(client, 1)
        assert state['validation']['valid']
        assert len(init(client)['chain']) == 1  # Fresh snapshot affects only this experiment.
    assert set(threading.enumerate()) == workers and capture() == baseline
    assert mine(client, other['candidate'])['validation']['valid']
    assert client.post('/api/credentials', json={'issuer_wallet_id': credential['issuer_wallet_id'],
                                               'holder_name': '', 'title': '', 'issue_date': '2026-01-01'}).status_code == 422
    client.post(f'/api/labs/network/{lab}/reset')
    client.post(f'/api/labs/signatures/keys/{key["key_handle"]}/reset')
