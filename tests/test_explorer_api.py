"""Read-only snapshots of the guided network, never disposable lab chains."""
from api.session_store import current_session

from copy import deepcopy
from dataclasses import asdict

from api import network_store, wallet_store
from tests.test_mempool_api import client, issue, submit
from tests.test_mining_api import low_difficulty, mine
from tests.test_pos_api import forge
from tests.test_verification_api import revoke
from tests.test_network_api import status, wait_for


def blocks(client, node='Node-1'):
    response = client.get('/api/explorer/blocks', params={'node_id': node})
    assert response.status_code == 200, response.text
    return response.json()


def detail(client, height, node='Node-1'):
    response = client.get(f'/api/explorer/blocks/{height}', params={'node_id': node})
    assert response.status_code == 200, response.text
    return response.json()


def test_genesis_and_no_wallet_seeding(client):
    # The reset endpoint seeds wallets in its response; model an unseeded store explicitly.
    with current_session().lock:
        wallet_store.reset_wallets()
    assert not current_session().wallets._seeded and not current_session().wallets._store
    data = blocks(client)
    assert data['node_id'] == 'Node-1' and data['status'] == 'ONLINE'
    assert data['tip_height'] == 0 and data['local_chain_warning'] is None
    genesis = network_store.get_network().nodes['Node-1'].blockchain.chain[0]
    assert data['blocks'] == [genesis.to_dict()]
    result = detail(client, 0)
    assert result['block'] == genesis.to_dict()
    assert result['header'] == asdict(genesis.header)
    assert result['transactions'] == [] and result['validator'] is None
    assert result['tip_hash'] == data['tip_hash'] == genesis.compute_hash()
    assert not current_session().wallets._seeded and not current_session().wallets._store


def test_pow_issue_revoke_and_reset(client, low_difficulty):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    mined = mine(client).json()
    result = detail(client, 1)
    assert result['block'] == mined['block']
    assert result['transactions'] == [credential['transaction']]
    assert result['header']['nonce'] == mined['block']['nonce']
    assert result['header']['difficulty'] == 1 and result['validator'] is None
    assert revoke(client, credential['credential_id']).json()['accepted']
    assert mine(client).json()['mined']
    wait_for(client, lambda d: d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 2)
    assert [b['height'] for b in blocks(client)['blocks']] == [2,1,0]
    revocation = detail(client, 2)['transactions'][0]
    assert revocation['tx_type'] == 'REVOKE'
    assert revocation['payload']['credential_id'] == credential['credential_id']
    old_reset = result['reset_count']
    client.post('/api/session/reset')
    assert blocks(client)['tip_height'] == 0
    assert blocks(client)['reset_count'] == old_reset + 1
    assert client.get('/api/explorer/blocks/1?node_id=Node-1').status_code == 404


def test_pos_identity_uses_signature_and_public_key_not_name(client, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    forged = forge(client).json()
    wait_for(client, lambda d:d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 1)
    network = network_store.get_network()
    # Giving all organizations the same display name must not select the first key.
    for v in network.pos_registry.validators.values():
        v.name = 'Same name'
    result = detail(client, 1, 'Node-2')
    signer = forged['signer']
    assert result['block'] == forged['block']
    assert result['validator'] == {'name':'Same name', 'address':signer['address'], 'public_key_hex':signer['public_key_hex']}
    assert result['header']['validator_address'] == signer['address']
    assert result['transactions'][0]['sender_public_key'] == credential['transaction']['sender_public_key']
    assert result['validator']['public_key_hex'] != result['transactions'][0]['sender_public_key']
    assert 'private' not in str(result).lower() and 'BEGIN' not in str(result)
    validator = network.pos_registry.validators[signer['address']]
    other = next(v for v in network.pos_registry.validators.values() if v.address != signer['address'])
    monkeypatch.setattr(validator, 'public_key_hex', other.public_key_hex)
    assert detail(client, 1)['validator'] is None  # Wrong registry key cannot supply a signer label.


def test_offline_local_scope_and_errors(client, low_difficulty):
    status(client, False)
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    assert mine(client).json()['mined']
    wait_for(client, lambda d:d['nodes'][1]['height'] == 1)
    offline = blocks(client, 'Node-3')
    assert offline['status'] == 'OFFLINE' and offline['tip_height'] == 0
    assert offline['local_chain_warning']
    assert detail(client, 0, 'Node-3')['local_chain_warning'] == offline['local_chain_warning']
    assert client.get('/api/explorer/blocks/1?node_id=Node-3').status_code == 404
    for route in ('/api/explorer/blocks','/api/explorer/blocks/0'):
        response = client.get(route, params={'node_id':'unknown'})
        assert response.status_code == 404 and response.json()['detail']['code'] == 'node_not_found'
    assert client.get('/api/explorer/blocks/100?node_id=Node-1').json()['detail']['code'] == 'block_not_found'
    assert client.get('/api/explorer/blocks/-1?node_id=Node-1').status_code == 404
    assert client.get('/api/explorer/blocks/not-a-height?node_id=Node-1').status_code == 422


def test_reads_are_detached_and_do_not_mutate_any_session_state(client, low_difficulty, monkeypatch):
    credential = issue(client)
    assert submit(client, credential).json()['accepted']
    assert mine(client).json()['mined']
    pending = issue(client)
    assert submit(client, pending).json()['accepted']
    wait_for(client, lambda d:d['all_nodes_synchronized'] and d['nodes'][0]['height'] == 1)
    from tests.test_mempool_api import wait_for_counts
    wait_for_counts(client, [1,1,1])
    network = network_store.get_network()
    def capture():
        return deepcopy(([([b.to_dict() for b in n.blockchain.chain],
                           [[tx.to_dict() for tx in b.transactions] for b in n.blockchain.chain],
                           [tx.to_dict() for tx in n.mempool.get_transactions()]) for n in network.nodes.values()],
                         current_session().wallets._store,
                         {k:(c.__dict__, tx.to_dict()) for k,(c,tx) in current_session().signed_credentials.items()},
                         [(v.address,v.public_key_hex,v.stake,v.is_active) for v in network.pos_registry.validators.values()],
                         network_store.get_reset_count()))
    baseline = capture()
    def forbidden(*args, **kwargs):raise AssertionError('Explorer attempted mutation')
    for name in ('broadcast','sync_all_nodes'):
        monkeypatch.setattr(network, name, forbidden)
    for node in network.nodes.values():
        for name in ('mine_pending','forge_pos_pending','go_online','go_offline','submit_transaction'):
            monkeypatch.setattr(node, name, forbidden)
    for node_id in network.nodes:
        blocks(client, node_id); detail(client, 1, node_id)
    assert capture() == baseline
    # Even direct handler callers must not receive a reference to live tx.payload.
    from api.wallet_api import api_explorer_block
    data = api_explorer_block(1, 'Node-1')
    data['transactions'][0]['payload']['title'] = 'caller edit'
    assert capture() == baseline
    # Disposable lab blocks are not explorer blocks.
    lab = client.post('/api/labs/tamper').json()
    assert lab['lab_id'] != 'Node-1'
    assert blocks(client)['tip_hash'] == baseline[0][0][0][-1]['hash']
