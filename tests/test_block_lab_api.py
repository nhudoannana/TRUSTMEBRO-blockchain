"""One-block calculations reuse real models and never create a lab Network."""
from copy import deepcopy
import json

import pytest

from api import network_store, wallet_store, wallet_api
from blockchain.block import Block
from blockchain.merkle import calculate_merkle_root
from blockchain.mining import is_acceptable_pow
from blockchain.transaction import Transaction, verify_transaction
from tests.test_mempool_api import client, issue, submit, wait_for_counts


def build(client, **changes):
    response = client.post('/api/labs/block/build', json={'data': 'My independent note', 'difficulty': 2, **changes})
    assert response.status_code == 200, response.text
    return response.json()


def mine(client, candidate):
    response = client.post('/api/labs/block/mine', json={'candidate': candidate})
    assert response.status_code == 200, response.text
    return response.json()


def restore(candidate):
    data = candidate['transaction']
    tx = Transaction(data['tx_type'], data['sender_public_key'], data['payload'],
                     nonce=data['nonce'], timestamp=data['timestamp'])
    tx.tx_id, tx.signature = data['tx_id'], data['signature']
    header = candidate['header']
    block = Block([tx], 1, header['previous_hash'], difficulty=header['difficulty'],
                  nonce=header['nonce'], timestamp=header['timestamp'], version=header['version'])
    block.header.merkle_root = header['merkle_root']
    return block


def test_actual_fields_hash_mining_and_edit_detection(client):
    built = build(client, data='Tự nhập 🌏', previous_hash='a' * 64,
                  timestamp='2026-10-04T12:00:00+07:00', version=2)
    original = built['candidate']
    block = restore(original)
    assert original['header']['version'] == 2
    assert original['header']['previous_hash'] == 'a' * 64
    assert original['header']['timestamp'] == '2026-10-04T12:00:00+07:00'
    assert original['header']['merkle_root'] == calculate_merkle_root([block.transactions[0].tx_id])
    assert built['computed_hash'] == original['stored_hash'] == block.compute_hash()
    assert verify_transaction(block.transactions[0])[0]
    mined = mine(client, original)
    assert mined['stage'] == 'mined' and mined['validation']['valid']
    block = restore(mined['candidate'])
    assert is_acceptable_pow(block)
    assert mined['computed_hash'] == block.compute_hash()
    assert mined['mining']['attempts'] == block.header.nonce + 1
    assert mined['mining']['seconds'] >= 0
    assert mined['candidate']['transaction'] == original['transaction']
    edited = client.post('/api/labs/block/edit', json={
        'candidate': mined['candidate'], 'data': 'Nội dung bị sửa'}).json()
    assert edited['stage'] == 'edited' and not edited['validation']['valid']
    damaged = restore(edited['candidate'])
    assert verify_transaction(damaged.transactions[0]) == (
        edited['validation']['checks']['transaction']['valid'],
        edited['validation']['checks']['transaction']['reason'])
    assert edited['candidate']['header'] == mined['candidate']['header']
    assert edited['candidate']['stored_hash'] == mined['candidate']['stored_hash']
    assert edited['computed_hash'] == mined['computed_hash']  # Header hashes stored tx IDs.
    assert edited['computed_transaction_hash'] != original['transaction']['tx_id']
    for key in ('tx_id', 'signature', 'nonce', 'timestamp'):
        assert edited['candidate']['transaction'][key] == original['transaction'][key]
    assert client.post('/api/labs/block/mine', json={'candidate': edited['candidate']}).status_code == 422
    empty_edit = client.post('/api/labs/block/edit', json={
        'candidate': mined['candidate'], 'data': ''})
    assert empty_edit.status_code == 200
    assert empty_edit.json()['candidate']['transaction']['payload']['lab_data'] == ''
    assert not empty_edit.json()['validation']['valid']
    fresh = build(client, data='Nội dung bị sửa')
    assert fresh['candidate']['transaction']['tx_id'] != original['transaction']['tx_id']
    assert mine(client, fresh['candidate'])['validation']['valid']
    assert 'private' not in str((built, mined, edited)).lower()


@pytest.mark.parametrize('changes', [
    {'data': 'x' * 4001}, {'data': '\ud800'}, {'data': {}},
    {'holder_name': 'no certificate input'}, {'difficulty': 1}, {'difficulty': 6},
    {'difficulty': True}, {'version': 0}, {'previous_hash': 'not a hash'},
    {'timestamp': 'not a date'}, {'timestamp': '2026-01-01'}, {'arbitrary': {}},
])
def test_invalid_build_inputs(client, changes):
    assert client.post('/api/labs/block/build', content=json.dumps({'data': 'valid text', **changes}),
                       headers={'Content-Type': 'application/json'}).status_code == 422


def test_invalid_candidates_and_bounded_incomplete_work(client, monkeypatch):
    candidate = build(client)['candidate']
    for field, value in [('stored_hash', 'a' * 64), ('signature', '00'), ('merkle_root', 'b' * 64)]:
        bad = deepcopy(candidate)
        target = bad if field == 'stored_hash' else bad['transaction'] if field == 'signature' else bad['header']
        target[field] = value
        assert client.post('/api/labs/block/mine', json={'candidate': bad}).status_code == 422
    # Empty/whitespace text is allowed; editing before PoW must fail deterministically.
    block = restore(candidate)
    while is_acceptable_pow(block):
        block.header.nonce += 1
    candidate['header']['nonce'] = block.header.nonce
    candidate['stored_hash'] = block.compute_hash()
    for data in ('', '  ', candidate['transaction']['payload']['lab_data']):
        assert client.post('/api/labs/block/edit', json={'candidate': candidate, 'data': data}).status_code == 409
    monkeypatch.setattr(wallet_api, '_BLOCK_LAB_MAX_ATTEMPTS', 0)
    # Choose a nonce that really fails PoW, avoiding chance success at nonce zero.
    block = restore(candidate)
    while is_acceptable_pow(block):
        block.header.nonce += 1
    candidate['header']['nonce'] = block.header.nonce
    candidate['stored_hash'] = block.compute_hash()
    limited = mine(client, candidate)
    assert limited['stage'] == 'incomplete' and not limited['mining']['completed']
    assert limited['mining']['attempts'] == 0 and limited['mining']['reason']
    assert limited['candidate']['transaction'] == candidate['transaction']
    assert not limited['validation']['checks']['pow']['valid']
    assert client.post('/api/labs/block/edit', json={'candidate': limited['candidate'], 'data': 'edit'}).status_code == 409


def test_block_lab_does_not_touch_guided_or_other_labs(client, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    wait_for_counts(client, [1, 1, 1])
    key = client.post('/api/labs/signatures/keys').json()
    lab = client.post('/api/labs/network').json()['lab_handle']
    def capture():
        network = network_store.get_network()
        return deepcopy(([[b.to_dict() for b in n.blockchain.chain] for n in network.nodes.values()],
                         [[t.to_dict() for t in n.mempool.get_transactions()] for n in network.nodes.values()],
                         wallet_store._store, {k: (c.to_onchain_payload(), tx.to_dict()) for k, (c, tx) in network_store.signed_credentials.items()},
                         [(v.address, v.public_key_hex, v.stake) for v in network.pos_registry.validators.values()], network_store.get_reset_count(),
                         client.get(f'/api/labs/network/{lab}').json()['nodes'], dict(wallet_api._lab_keys)))
    baseline = capture()
    def forbidden(*args, **kwargs):
        raise AssertionError('A single block must not create a Network')
    monkeypatch.setattr(wallet_api, 'Network', forbidden)
    for _ in range(2):
        result = mine(client, build(client)['candidate'])
        assert result['validation']['valid']
    assert capture() == baseline
    assert client.post('/api/labs/signatures/sign', json={'key_handle': key['key_handle'], 'message': 'still here'}).status_code == 200
    client.post(f'/api/labs/network/{lab}/reset')
    client.post(f'/api/labs/signatures/keys/{key["key_handle"]}/reset')


def test_mining_time_limit_busy_and_failure_release(client, monkeypatch):
    candidate = build(client)['candidate']
    monkeypatch.setattr(wallet_api, '_BLOCK_LAB_MAX_SECONDS', 0)
    data = mine(client, candidate)
    assert data['stage'] == 'incomplete' and data['mining']['attempts'] == 0
    assert data['candidate']['header']['nonce'] == candidate['header']['nonce']
    monkeypatch.setattr(wallet_api, '_BLOCK_LAB_MAX_SECONDS', 3)
    wallet_api._block_lab_mining_lock.acquire()
    try:
        assert client.post('/api/labs/block/mine', json={'candidate': candidate}).status_code == 429
    finally:
        wallet_api._block_lab_mining_lock.release()
    backend_mine = wallet_api.mine_block
    def failure(block):
        raise RuntimeError('fixture backend failure')
    monkeypatch.setattr(wallet_api, 'mine_block', failure)
    response = client.post('/api/labs/block/mine', json={'candidate': candidate})
    assert response.status_code == 500 and response.json()['detail']
    monkeypatch.setattr(wallet_api, 'mine_block', backend_mine)
    assert mine(client, candidate)['validation']['valid']
