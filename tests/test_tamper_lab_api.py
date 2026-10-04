"""Actual local corruption/recovery; no guided-session tampering endpoint."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from api import wallet_api, network_store
from blockchain.blockchain import Blockchain
from fastapi.testclient import TestClient
from tests.test_mempool_api import client


def path(handle='', suffix=''):
    return '/api/labs/tamper' + ('/' + handle if handle else '') + suffix


def create(client):
    response = client.post(path())
    assert response.status_code == 201, response.text
    return response.json()


def read(client, handle):
    response = client.get(path(handle))
    assert response.status_code == 200, response.text
    return response.json()


def ready(client, data):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        data = read(client, data['lab_id'])
        if data['ready']:
            return data
        time.sleep(.02)
    pytest.fail(f'Preparation did not converge: {data}')


def edit(client, handle, title='Edited sample title'):
    return client.post(path(handle, '/edit'), json={'title': title})


def test_prepare_independent_corruption_and_real_sync(client, monkeypatch):
    registries = []
    verify = Blockchain.verify_credential
    def capture(chain, *args, **kwargs):
        registries.append(kwargs['pos_registry'])
        return verify(chain, *args, **kwargs)
    monkeypatch.setattr(Blockchain, 'verify_credential', capture)
    data = ready(client, create(client))
    handle = data['lab_id']
    entry = wallet_api._lab_networks[handle]
    network = entry['network']
    assert data['prepared'] and not data['tampered'] and not data['restored']
    assert all(n['chain_valid'] and n['verification']['status'] == 'VERIFIED' for n in data['nodes'])
    assert all(n['height'] == 1 for n in data['nodes'])
    assert len({n['stored_tip_hash'] for n in data['nodes']}) == 1
    assert data['mining']['block']['difficulty'] == 3
    original = {name:deepcopy(node.blockchain.chain[1].transactions[0].to_dict()) for name,node in network.nodes.items()}
    blocks = {name:node.blockchain.chain[1].to_dict() for name,node in network.nodes.items()}
    broadcasts = []
    broadcast = network.broadcast
    monkeypatch.setattr(network, 'broadcast', lambda sender,msg:(broadcasts.append(msg.msg_type),broadcast(sender,msg))[1])
    # Even an accidentally shared whole block must not allow cross-node mutation.
    with network.nodes['Node-2']._state_lock:
        network.nodes['Node-2'].blockchain.chain[1] = network.nodes['Node-1'].blockchain.chain[1]
    changed_title = '<img src=x onerror=alert(1)>'
    response = edit(client, handle, changed_title)
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed['tampered'] and not changed['ready'] and not changed['restored']
    assert changed['original_title'] == original['Node-1']['payload']['title']
    assert changed['edited_title'] == changed_title
    assert [n['chain_valid'] for n in changed['nodes']] == [True,False,True]
    assert [n['verification']['status'] for n in changed['nodes']] == ['VERIFIED','INVALID','VERIFIED']
    for name,node in network.nodes.items():
        block = node.blockchain.chain[1]
        tx = block.transactions[0]
        assert block.to_dict() == blocks[name]  # Stored header commitments stayed unchanged.
        if name == 'Node-2':
            expected = deepcopy(original[name]);expected['payload']['title'] = changed_title
            assert tx.to_dict() == expected
            assert tx is not network.nodes['Node-1'].blockchain.chain[1].transactions[0]
            assert tx.payload is not network.nodes['Node-1'].blockchain.chain[1].transactions[0].payload
        else:
            assert tx.to_dict() == original[name]
    node2 = network.nodes['Node-2']
    valid, _, reason = node2.blockchain.is_chain_valid(pos_registry=network.pos_registry)
    assert not valid and changed['nodes'][1]['validity_reason'] == reason
    checks, status, info = node2.blockchain.verify_credential(data['credential_id'],pos_registry=network.pos_registry)
    assert changed['nodes'][1]['verification']['reason'] == checks[-1][2] and status == 'INVALID'
    assert not broadcasts  # No re-signing or broadcast disguised as tampering.
    assert [n['stored_tip_hash'] for n in changed['nodes']] == [n['stored_tip_hash'] for n in data['nodes']]
    # GET does not silently repair the corruption.
    assert read(client,handle)['nodes'][1]['verification']['status'] == 'INVALID'
    restored = client.post(path(handle,'/sync')).json()
    assert restored['ready'] and restored['restored'] and not restored['tampered']
    assert wallet_api._lab_networks[handle]['network'] is network
    assert all(n['local_title'] == data['original_title'] and n['chain_valid']
               and n['verification']['status'] == 'VERIFIED' for n in restored['nodes'])
    assert len({n['stored_tip_hash'] for n in restored['nodes']}) == 1
    assert all(registry is network.pos_registry for registry in registries)
    assert client.post(path(handle,'/sync')).json()['restored']  # Idempotent recovery.
    assert 'private' not in json.dumps(restored).lower() and 'BEGIN' not in json.dumps(restored)


@pytest.mark.parametrize('body', [{}, {'title':''}, {'title':'   '}, {'title':'x'*201},
                                  {'title':'ok','node_id':'Node-1'}, {'title':'ok','path':'payload.title'}])
def test_only_title_and_valid_input(client, body):
    data = ready(client,create(client))
    response = client.post(path(data['lab_id'],'/edit'),json=body)
    assert response.status_code == 422
    assert read(client,data['lab_id'])['ready']


def test_noop_wrong_type_missing_and_invalid_lifecycle(client):
    network_lab = client.post('/api/labs/network').json()
    network_handle = network_lab['lab_handle']
    for suffix in ('/edit','/sync'):
        assert client.post(path(network_handle,suffix),json={'title':'changed'}).status_code == 404
    assert client.delete(path(network_handle)).status_code == 404
    assert client.get('/api/labs/network/'+network_handle).status_code == 200
    assert client.get(path('missing')).status_code == 404
    assert edit(client,'missing').status_code == 404
    data = ready(client,create(client));handle = data['lab_id']
    assert edit(client,handle,' '+data['original_title']+' ').status_code == 422
    assert client.post(path(handle,'/sync')).status_code == 409
    for suffix in ('/mine','/sync','/reset','/nodes/Node-3/status'):
        assert client.post('/api/labs/network/'+handle+suffix,json={'online':False}).status_code == 404
    assert read(client,handle)['ready']
    assert edit(client,handle).status_code == 200
    assert edit(client,handle,'another edit').status_code == 409
    assert client.delete(path(handle)).json()['cleared']
    assert not client.delete(path(handle)).json()['cleared']
    assert edit(client,handle).status_code == 404


def test_pending_preparation_cannot_be_edited(client,monkeypatch):
    broadcast = wallet_api.Network.broadcast
    def skip_block(network,sender,message):
        if message.msg_type != 'BLOCK':
            broadcast(network,sender,message)
    monkeypatch.setattr(wallet_api.Network,'broadcast',skip_block)
    data = create(client)
    assert data['prepared'] and not data['ready']
    assert edit(client,data['lab_id']).status_code == 409
    assert not read(client,data['lab_id'])['tampered']


def test_failed_sync_never_fabricates_recovery(client,monkeypatch):
    data = ready(client,create(client));handle = data['lab_id']
    assert edit(client,handle).status_code == 200
    network = wallet_api._lab_networks[handle]['network']
    monkeypatch.setattr(network,'sync_all_nodes',lambda **kwargs:None)
    response = client.post(path(handle,'/sync'))
    assert response.status_code == 200
    result = response.json()
    assert not result['restored'] and not result['ready'] and result['tampered']
    assert result['reason'] == result['nodes'][1]['validity_reason']
    def fail(**kwargs):
        raise RuntimeError('fixture sync failure')
    monkeypatch.setattr(network, 'sync_all_nodes', fail)
    assert client.post(path(handle,'/sync')).status_code == 500
    assert read(client, handle)['tampered']


def test_prepare_backend_rejection_preserves_pending_and_reason(client, monkeypatch):
    from blockchain.node import Node
    monkeypatch.setattr(Node, '_validate_candidate', lambda node, block:(False, 'fixture: actual backend block rejection'))
    data = create(client)
    assert not data['prepared'] and not data['ready']
    assert data['reason'] == 'fixture: actual backend block rejection'
    entry = wallet_api._lab_networks[data['lab_id']]
    assert len(entry['network'].nodes['Node-1'].mempool.get_transactions()) == 1
    assert read(client, data['lab_id'])['transaction']['tx_id'] == entry['tx'].tx_id
    assert edit(client, data['lab_id']).status_code == 409


def test_reset_serializes_with_sync(client, monkeypatch):
    data = ready(client, create(client)); handle = data['lab_id']
    assert edit(client, handle).status_code == 200
    network = wallet_api._lab_networks[handle]['network']
    entered, release, resetting = threading.Event(), threading.Event(), threading.Event()
    sync = network.sync_all_nodes
    def paused_sync(**kwargs):
        entered.set()
        assert release.wait(timeout=3)
        return sync(**kwargs)
    def reset():
        resetting.set()
        return client.delete(path(handle))
    monkeypatch.setattr(network, 'sync_all_nodes', paused_sync)
    with ThreadPoolExecutor(max_workers=2) as pool:
        syncing = pool.submit(client.post, path(handle, '/sync'))
        assert entered.wait(timeout=3)
        closing = pool.submit(reset)
        assert resetting.wait(timeout=3) and not closing.done()
        release.set()
        assert syncing.result(timeout=5).json()['restored']
        assert closing.result(timeout=5).json()['cleared']
    assert all(not n._worker.is_alive() for n in network.nodes.values())
    assert client.get(path(handle)).status_code == 404


def test_expiry_timer_stops_workers_without_another_request(client, monkeypatch):
    # A short test TTL, not a change to the app's 15-minute lifetime.
    monkeypatch.setattr(wallet_api, '_LAB_NETWORK_TTL', 2)
    data = create(client); handle = data['lab_id']
    entry = wallet_api._lab_networks[handle]
    entry['timer'].join(timeout=4)
    assert not entry['timer'].is_alive()
    assert handle not in wallet_api._lab_networks
    assert all(not n._worker.is_alive() for n in entry['network'].nodes.values())
    assert edit(client, handle).status_code == 404


def test_isolation_capacity_expiry_reset_and_shutdown(client,monkeypatch):
    network_handle = client.post('/api/labs/network').json()['lab_handle']
    other = wallet_api._lab_networks[network_handle]['network']
    key = client.post('/api/labs/signatures/keys').json()
    baseline = (client.get('/api/network').json(),client.get('/api/session').json(),client.get('/api/wallets').json(),dict(network_store.signed_credentials))
    for _ in range(3):
        data = ready(client,create(client));handle = data['lab_id']
        entry = wallet_api._lab_networks[handle]
        assert edit(client,handle).status_code == 200
        assert client.post(path(handle,'/sync')).json()['restored']
        assert client.delete(path(handle)).json()['cleared']
        entry['timer'].join(timeout=1)
        assert not entry['timer'].is_alive()
        assert all(not n._worker.is_alive() for n in entry['network'].nodes.values())
    assert baseline == (client.get('/api/network').json(),client.get('/api/session').json(),client.get('/api/wallets').json(),dict(network_store.signed_credentials))
    assert wallet_api._lab_networks[network_handle]['network'] is other
    assert all(n['height']==0 for n in client.get('/api/labs/network/'+network_handle).json()['nodes'])
    assert client.post('/api/labs/signatures/sign',json={'key_handle':key['key_handle'],'message':'kept'}).status_code == 200
    monkeypatch.setattr(wallet_api,'_LAB_NETWORK_LIMIT',2)
    data=create(client);entry=wallet_api._lab_networks[data['lab_id']]
    assert client.post(path()).status_code == 429
    assert client.post('/api/labs/network').status_code == 429
    entry['expires']=time.monotonic()-1
    assert edit(client,data['lab_id']).status_code == 404
    assert data['lab_id'] not in wallet_api._lab_networks
    assert all(not n._worker.is_alive() for n in entry['network'].nodes.values())


def test_shutdown_and_unexpected_prepare_failure_stop_workers(monkeypatch):
    captured=[]
    create_node=wallet_api.Network.create_node
    def capture(network,*args,**kwargs):
        node=create_node(network,*args,**kwargs);captured.append(node);return node
    monkeypatch.setattr(wallet_api.Network,'create_node',capture)
    with TestClient(wallet_api.app) as local:
        create(local)
    assert all(not n._worker.is_alive() for n in captured)
    assert not wallet_api._lab_networks
    from blockchain.node import Node
    def fail(node):raise RuntimeError('fixture mining failure')
    monkeypatch.setattr(Node,'mine_pending',fail)
    with TestClient(wallet_api.app) as local:
        assert local.post(path()).status_code == 500
        assert not wallet_api._lab_networks
    assert all(not n._worker.is_alive() for n in captured)
