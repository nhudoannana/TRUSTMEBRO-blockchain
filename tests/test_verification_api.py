"""Step G uses actual local chains, issuer keys and pending REVOKE transactions."""
from api.session_store import current_session

import pytest

from api import network_store, wallet_store
from tests.test_mempool_api import client, issue, submit
from tests.test_mining_api import low_difficulty, mine
from tests.test_network_api import wait_for, status


def verify(client, credential_id, node='Node-1', presented=None):
    body = {'credential_id': credential_id, 'node_id': node}
    if presented is not None:
        body['presented_credential'] = presented
    response = client.post('/api/verify', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def issued(client):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    assert mine(client).json()['mined']
    assert client.post('/api/network/sync').json()['completed']
    return credential


def presentation(credential):
    return {key: credential['credential'][key] for key in ['holder_name', 'title', 'issue_date', 'issuer_name']}


def revoke(client, credential_id, **extra):
    return client.post(f'/api/credentials/{credential_id}/revoke', json={'node_id':'Node-1','reason':'Expired', **extra})


def test_original_and_each_changed_field_without_adapter_record(client, low_difficulty):
    credential = issued(client)
    current_session().signed_credentials.clear()
    original = presentation(credential)
    result = verify(client, credential['credential_id'], presented=original)
    assert result['success'] and result['presentation_match']
    assert result['record_verified'] and result['presented_document_accepted']
    assert result['chain_status']['status'] == 'VERIFIED'
    assert len(result['chain_status']['checks']) == 12
    for field in original:
        changed = {**original, field: '2026-01-02' if field == 'issue_date' else 'Changed'}
        result = verify(client, credential['credential_id'], presented=changed)
        assert result['chain_status']['status'] == 'VERIFIED'
        assert not result['success'] and not result['presentation_match']
        assert result['record_verified'] and not result['presented_document_accepted']
        assert result['mismatched_fields'] == [field]
    id_only = verify(client, credential['credential_id'])
    assert id_only['presentation_match'] is None
    assert id_only['success'] and id_only['record_verified']
    assert not id_only['presented_document_accepted']


def test_landing_navigation_and_static_boundary(client):
    response = client.get('/landing.html')
    assert response.status_code == 200
    assert 'href="/ui/modes.html"' in response.text
    assert 'href="/ui/trustmebro.html"' in client.get('/ui/modes.html').text
    assert 'href="/landing.html"' in client.get('/ui/trustmebro.html').text
    assert client.get('/requirements.txt').status_code == 404
    assert client.get('/.git/config').status_code == 404


def test_selected_offline_node_and_catchup(client, low_difficulty):
    status(client, False)
    credential = issued(client)
    result = verify(client, credential['credential_id'], 'Node-3', presentation(credential))
    assert result['node_id'] == 'Node-3' and result['node_status'] == 'OFFLINE'
    assert result['chain_status']['status'] == 'NOT_FOUND'
    assert not result['success'] and result['presentation_match'] is None
    status(client, True)
    wait_for(client, lambda data: data['all_nodes_synchronized'])
    assert verify(client, credential['credential_id'], 'Node-3')['success']


def test_issuer_identity_pending_revoke_mining_and_reset(client, low_difficulty):
    credential = issued(client)
    cid = credential['credential_id']
    same_name = client.post('/api/wallets', json={'name':credential['credential']['issuer_name']}).json()
    assert revoke(client, cid, issuer_wallet_id=same_name['id']).status_code == 403
    response = revoke(client, cid, issuer_wallet_id=credential['issuer_wallet_id'])
    assert response.status_code == 200
    result = response.json()
    assert result['accepted'] and result['pending']
    assert result['transaction']['tx_type'] == 'REVOKE'
    assert result['transaction']['sender_public_key'] == credential['transaction']['sender_public_key']
    assert 'PRIVATE' not in response.text and 'private_key' not in response.text
    assert verify(client, cid)['chain_status']['status'] == 'VERIFIED'
    duplicate = revoke(client, cid).json()
    assert not duplicate['accepted'] and duplicate['reason_source'] == 'adapter'
    assert mine(client).json()['mined']
    wait_for(client, lambda data: data['all_nodes_synchronized'] and data['nodes'][0]['height'] == 2)
    result = verify(client, cid, 'Node-3', presentation(credential))
    assert result['chain_status']['status'] == 'REVOKED'
    assert result['presentation_match'] and not result['success']
    assert not revoke(client, cid).json()['accepted']
    client.post('/api/session/reset')
    assert verify(client, cid)['chain_status']['status'] == 'NOT_FOUND'
    assert revoke(client, cid).status_code == 404


def test_missing_key_invalid_chain_authorization_and_unknown_node(client, low_difficulty):
    credential = issued(client)
    cid = credential['credential_id']
    wallet_store.reset_wallets()
    assert revoke(client, cid).status_code == 409
    node = low_difficulty
    with node._state_lock:
        node.mempool.authorized_issuers = {'another-public-key'}
    result = verify(client, cid, presented=presentation(credential))
    assert result['chain_status']['status'] == 'INVALID'
    assert not result['success'] and result['presentation_match'] is None
    assert client.post('/api/verify', json={'credential_id':cid,'node_id':'missing'}).status_code == 404
    assert revoke(client, cid, node_id='missing').status_code == 404


@pytest.mark.parametrize('body', [{}, {'credential_id':' ','node_id':'Node-1'}, {'credential_id':'id','node_id':'Node-1','presented_credential':{'title':'x'}}])
def test_verification_validation(client, body):
    assert client.post('/api/verify', json=body).status_code == 422


def test_pos_registry_fixture_verifies_and_rejects_forged_signature(client):
    credential = issue(client)
    node = network_store.get_network().nodes['Node-1']
    registry = node.network.pos_registry
    with node._state_lock:
        tx = current_session().signed_credentials[credential['credential_id']][1]
        validator = next(iter(registry.validators.values()))
        block = registry.forge_block(validator, [tx], 1, node.blockchain.chain[0].compute_hash())
        node.blockchain.add_block(block)
        assert node.blockchain.verify_credential(credential['credential_id'])[1] == 'INVALID'
    assert verify(client, credential['credential_id'])['success']
    with node._state_lock:
        block.header.validator_signature = 'forged'
    result = verify(client, credential['credential_id'], presented=presentation(credential))
    assert result['chain_status']['status'] == 'INVALID'
    assert result['presentation_match'] is None and not result['success']


def test_offline_revoke_preserves_backend_reason_and_validation(client, low_difficulty):
    credential = issued(client)
    client.post('/api/network/nodes/Node-1/status', json={'online':False})
    result = revoke(client, credential['credential_id']).json()
    assert not result['accepted'] and not result['pending']
    assert result['reason'] == 'Node-1 đang OFFLINE' and result['reason_source'] == 'backend'
    assert revoke(client, credential['credential_id'], reason=' ').status_code == 422
