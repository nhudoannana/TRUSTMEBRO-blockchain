"""Step C checks through TestClient; no browser or live server."""

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api import network_store, wallet_store
from api.wallet_api import app
from blockchain.transaction import verify_transaction


@pytest.fixture
def client():
    with TestClient(app) as client:
        client.post('/api/session/reset')
        yield client
        client.post('/api/session/reset')


def body(client):
    wallet = client.get('/api/wallets').json()[0]
    return dict(issuer_wallet_id=wallet['id'], holder_name=' Người học DEMO-001 ',
                title=' Chứng chỉ Phân tích dữ liệu ', issue_date='2026-10-01')


def test_signed_issuance_and_no_network_submission(client):
    request = body(client)
    network = network_store.get_network()
    chains = {key: deepcopy(node.blockchain.chain) for key, node in network.nodes.items()}
    responses = [client.post('/api/credentials', json=request) for _ in range(2)]
    assert all(r.status_code == 201 for r in responses)
    a, b = [r.json() for r in responses]
    assert a['credential_id'] != b['credential_id']
    assert str(UUID(a['credential_id'])) == a['credential_id']
    with network_store.session_lock:
        credential, tx = network_store.signed_credentials[a['credential_id']]
        assert verify_transaction(tx)[0]
        assert a['transaction'] == tx.to_dict()
        assert a['credential'] == credential.to_onchain_payload() == tx.payload
        assert tx.payload['holder_name'] == request['holder_name'].strip()
        assert tx.payload['claims_root'] == ''
        altered = deepcopy(tx)
        altered.payload['title'] = 'Tampered'
        altered.tx_id = altered.compute_hash()
        assert not verify_transaction(altered)[0]
    wallet = client.get('/api/wallets/' + request['issuer_wallet_id']).json()
    assert a['issuer_wallet_id'] == wallet['id']
    assert a['issuer_address'] == wallet['address']
    assert a['transaction']['sender_public_key'] == wallet['public_key_hex']
    assert a['credential']['issuer_name'] == wallet['name']
    for response in responses:
        assert 'private_key' not in response.text
        assert wallet_store.get_private_key_pem(wallet['id']) not in response.text
    for key, node in network.nodes.items():
        assert not node.mempool.get_transactions()
        assert [block.compute_hash() for block in node.blockchain.chain] == [block.compute_hash() for block in chains[key]]


def test_unknown_and_reset_wallet(client):
    request = body(client)
    assert client.post('/api/credentials', json={**request, 'issuer_wallet_id': 'unknown'}).status_code == 404
    assert client.post('/api/credentials', json=request).status_code == 201
    client.post('/api/session/reset')
    assert not network_store.signed_credentials
    assert client.post('/api/credentials', json=request).status_code == 404


@pytest.mark.parametrize('field,value', [
    ('issuer_wallet_id', ''), ('issuer_wallet_id', '  '), ('issuer_wallet_id', 'x' * 81),
    ('holder_name', ''), ('holder_name', '  '), ('holder_name', 'x' * 201),
    ('title', ''), ('title', '  '), ('title', 'x' * 201),
    ('issue_date', ''), ('issue_date', '2026-02-30'), ('issue_date', 'invalid'),
    ('issue_date', '20261001'), ('issue_date', 0),
])
def test_invalid_input(client, field, value):
    assert client.post('/api/credentials', json={**body(client), field: value}).status_code == 422


@pytest.mark.parametrize('field', ['issuer_wallet_id', 'holder_name', 'title', 'issue_date'])
def test_required_input(client, field):
    request = body(client)
    del request[field]
    assert client.post('/api/credentials', json=request).status_code == 422


def test_client_cannot_supply_identity_or_claims(client):
    for field in ['credential_id', 'issuer_name', 'claims', 'claims_root']:
        assert client.post('/api/credentials', json={**body(client), field: 'fake'}).status_code == 422


def test_same_name_wallet_uses_selected_key(client):
    first, selected = [client.post('/api/wallets', json={'name': 'Same Org'}).json() for _ in range(2)]
    response = client.post('/api/credentials', json={**body(client), 'issuer_wallet_id': selected['id']})
    assert response.status_code == 201
    assert response.json()['transaction']['sender_public_key'] == selected['public_key_hex'] != first['public_key_hex']
