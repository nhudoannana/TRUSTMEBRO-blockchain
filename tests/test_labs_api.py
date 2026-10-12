"""Disposable keys and exact backend Merkle conventions, isolated from the journey."""
from api.session_store import current_session

import json

import pytest

from api import wallet_api, network_store, wallet_store
from blockchain.hash import sha256_hex
from blockchain.merkle import build_merkle_tree, generate_merkle_proof
from tests.test_mempool_api import client
from tests.test_merkle import SAMPLE_LEAVES


@pytest.fixture(autouse=True)
def clear_lab_keys():
    current_session().lab_keys.clear()
    yield
    current_session().lab_keys.clear()


def key(client):
    response = client.post('/api/labs/signatures/keys')
    assert response.status_code == 201
    return response.json()


def sign(client, k, message='TrustMeBro'):
    response = client.post('/api/labs/signatures/sign', json={
        'key_handle': k['key_handle'], 'message': message})
    assert response.status_code == 200
    return response.json()


def verify(client, k, signed, message='TrustMeBro'):
    response = client.post('/api/labs/signatures/verify', json={
        'message': message, 'signature_hex': signed['signature_hex'],
        'public_key_hex': k['public_key_hex']})
    assert response.status_code == 200
    return response.json()['valid']


@pytest.mark.parametrize('message', ['TrustMeBro', '', '  Hồ sơ\n你好 🌏  '])
def test_actual_signature_modified_message_and_wrong_key(client, message):
    k, other = key(client), key(client)
    signed = sign(client, k, message)
    assert signed['message'] == message
    assert signed['public_key_hex'] == k['public_key_hex']
    assert verify(client, k, signed, message) is True
    assert verify(client, k, signed, message + '!') is False
    assert verify(client, other, signed, message) is False
    for public, signature in [('not-hex', signed['signature_hex']),
                              (k['public_key_hex'], 'zz'), (k['public_key_hex'], '')]:
        result = client.post('/api/labs/signatures/verify', json={
            'message': message, 'public_key_hex': public, 'signature_hex': signature})
        assert result.status_code == 200 and result.json()['valid'] is False
    for data in [k, other, signed]:
        assert 'private' not in json.dumps(data).lower()
        assert 'BEGIN' not in json.dumps(data)


def test_lab_reset_deletes_only_disposable_key(client):
    k, other = key(client), key(client)
    signed = sign(client, k)
    path = f"/api/labs/signatures/keys/{k['key_handle']}/reset"
    assert client.post(path).json() == {'cleared': True}
    assert client.post(path).json() == {'cleared': False}
    assert client.post('/api/labs/signatures/sign', json={
        'key_handle': k['key_handle'], 'message': 'text'}).status_code == 404
    assert verify(client, k, signed) is True  # deleting a key does not undo signatures
    assert sign(client, other)['signature_hex']


def test_key_expiry_and_capacity_are_bounded(client, monkeypatch):
    monkeypatch.setattr(wallet_api, '_LAB_KEY_LIMIT', 2)
    k = key(client)
    key(client)
    assert client.post('/api/labs/signatures/keys').status_code == 429
    future = wallet_api.time.monotonic() + wallet_api._LAB_KEY_TTL + 1
    monkeypatch.setattr(wallet_api.time, 'monotonic', lambda: future)
    assert client.post('/api/labs/signatures/sign', json={
        'key_handle': k['key_handle'], 'message': 'text'}).status_code == 404
    assert len(current_session().lab_keys) == 0
    assert key(client)['key_handle'] != k['key_handle']


def test_labs_do_not_mutate_journey_and_shared_reset_does_not_reset_lab(client):
    net = network_store.get_network()
    registry = net.pos_registry
    before = (wallet_store.list_wallets(), client.get('/api/network').json(),
              client.get('/api/mempool').json(), dict(current_session().signed_credentials))
    k = key(client)
    sign(client, k)
    client.post('/api/labs/merkle', json={'leaves': ['a', 'b', 'c'], 'proof_index': 2})
    client.post(f"/api/labs/signatures/keys/{k['key_handle']}/reset")
    after = (wallet_store.list_wallets(), client.get('/api/network').json(),
             client.get('/api/mempool').json(), dict(current_session().signed_credentials))
    assert before == after
    assert network_store.get_network() is net and net.pos_registry is registry
    other = key(client)
    client.post('/api/session/reset')
    assert sign(client, other)['signature_hex']


@pytest.mark.parametrize('leaves', [[], [''], ['tx0'], ['tx0', 'tx1', 'tx2'],
                                   ['tx0', 'tx1', 'tx2', 'tx3'],
                                   [f'leaf{i}' for i in range(5)], [f'leaf{i}' for i in range(7)]])
def test_merkle_levels_root_and_proofs_match_existing_backend(client, leaves):
    hashes = [sha256_hex(x) for x in leaves]
    if len(leaves) == 4:
        assert hashes == SAMPLE_LEAVES
    response = client.post('/api/labs/merkle', json={
        'leaves': leaves, 'proof_index': len(leaves) - 1 if leaves else None})
    assert response.status_code == 200
    data = response.json()
    assert data['leaf_hashes'] == hashes
    assert data['levels'] == build_merkle_tree(hashes)
    assert data['root'] == build_merkle_tree(hashes)[-1][0]
    if leaves:
        proof = data['proof']
        assert proof['index'] == len(leaves) - 1 and proof['valid'] is True
        assert proof['siblings'] == [list(x) for x in generate_merkle_proof(hashes, len(leaves) - 1)]
    else:
        assert data['proof'] is None and data['root'] == sha256_hex('')


@pytest.mark.parametrize('path,body', [
    ('signatures/sign', {'key_handle': 'missing', 'message': 'x' * 10001}),
    ('signatures/sign', {'key_handle': 'missing', 'message': 123}),
    ('signatures/verify', {'message': '', 'signature_hex': 'a' * 1025, 'public_key_hex': '04'}),
    ('merkle', {'leaves': ['a'] * 17}), ('merkle', {'leaves': ['a' * 2001]}),
    ('merkle', {'leaves': [], 'proof_index': 0}),
    ('merkle', {'leaves': ['a'], 'proof_index': 1}),
    ('merkle', {'leaves': ['a'], 'private_key': 'no'}),
])
def test_lab_validation(client, path, body):
    assert client.post('/api/labs/' + path, json=body).status_code == 422


@pytest.mark.parametrize("count", [1, 3, 5, 8, 16])
def test_custom_merkle_verification_trace_and_tampering(client, count):
    import hashlib
    from copy import deepcopy
    h = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    leaves = [f"Leaf {i + 1}" for i in range(count)]
    index = 2 if count >= 5 else 0
    generated = client.post("/api/labs/merkle", json={"leaves": leaves, "proof_index": index}).json()
    body = {"leaf_text": leaves[index], "proof": generated["proof"]["siblings"],
            "expected_root": generated["root"]}
    response = client.post("/api/labs/merkle/verify", json=body)
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"leaf_hash", "computed_root", "expected_root", "valid", "trace"}
    assert data["valid"] and data["leaf_hash"] == h(leaves[index])
    current = h(leaves[index])
    for step, ((sibling, direction), row) in enumerate(zip(body["proof"], data["trace"]), 1):
        parent = h(sibling + current if direction == "left" else current + sibling)
        assert row == {"step": step, "current_hash": current, "sibling_hash": sibling,
                       "direction": direction, "parent_hash": parent}
        current = parent
    assert len(data["trace"]) == len(body["proof"])
    assert data["computed_root"] == current == data["expected_root"]
    if count == 8:
        assert [row[1] for row in body["proof"]] == ["right", "left", "right"]
    uppercase = deepcopy(body)
    uppercase["expected_root"] = uppercase["expected_root"].upper()
    uppercase["proof"] = [[value.upper(), direction] for value, direction in uppercase["proof"]]
    assert client.post("/api/labs/merkle/verify", json=uppercase).json() == data
    for field in ["leaf_text", "expected_root", "sibling", "direction"]:
        if not body["proof"] and field in ["sibling", "direction"]:
            continue
        changed = deepcopy(body)
        if field == "leaf_text":
            changed[field] += " changed"
        elif field == "expected_root":
            changed[field] = h("another root")
        elif field == "sibling":
            changed["proof"][0][0] = h("another sibling")
        else:
            changed["proof"][0][1] = "left" if changed["proof"][0][1] == "right" else "right"
        result = client.post("/api/labs/merkle/verify", json=changed)
        assert result.status_code == 200 and result.json()["valid"] is False


def test_custom_merkle_empty_text_and_unicode_limit(client):
    import hashlib
    for text in ["", "  a\n ", "🌏" * 2000]:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        result = client.post("/api/labs/merkle/verify",
                             json={"leaf_text": text, "proof": [], "expected_root": digest})
        assert result.status_code == 200
        assert result.json() == {"leaf_hash": digest, "computed_root": digest,
                                "expected_root": digest, "valid": True, "trace": []}
    empty = client.post("/api/labs/merkle", json={"leaves": []}).json()
    one_empty = client.post("/api/labs/merkle", json={"leaves": [""], "proof_index": 0}).json()
    assert empty["root"] == one_empty["root"] and empty["proof"] is None
    assert one_empty["proof"]["siblings"] == []


@pytest.mark.parametrize("override", [
    {"leaf_text": 1}, {"leaf_text": None}, {"leaf_text": "x" * 2001}, {"leaf_text": "\ud800"},
    {"proof": None}, {"proof": "bad"}, {"proof": [["a" * 64, "left"]] * 5},
    {"proof": [["a" * 64]]}, {"proof": [["a" * 64, "right", "extra"]]},
    {"proof": [{"hash": "a" * 64, "direction": "left"}]},
    {"proof": [["a" * 64, "LEFT"]]}, {"proof": [["a" * 64, 1]]},
    {"proof": [["a" * 63, "right"]]}, {"proof": [["g" * 64, "right"]]},
    {"proof": [[1, "right"]]}, {"proof": [[" " + "a" * 64, "right"]]},
    {"expected_root": "a" * 65}, {"expected_root": "a" * 63},
    {"expected_root": "0x" + "a" * 64}, {"expected_root": "z" * 64},
    {"expected_root": 1}, {"expected_root": None}, {"expected_root": "a" * 64 + "\n"},
    {"leaf_hash": "a" * 64}, {"extra": True},
])
def test_custom_merkle_rejects_malformed_not_mismatch(client, override):
    body = {"leaf_text": "text", "proof": [], "expected_root": "a" * 64, **override}
    # Escaped JSON allows the invalid Unicode test to reach request validation.
    result = client.post("/api/labs/merkle/verify", content=json.dumps(body),
                         headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    assert "detail" in result.json() and "valid" not in result.json()


@pytest.mark.parametrize("missing", ["leaf_text", "proof", "expected_root"])
def test_custom_merkle_requires_all_fields(client, missing):
    body = {"leaf_text": "text", "proof": [], "expected_root": "a" * 64}
    del body[missing]
    assert client.post("/api/labs/merkle/verify", json=body).status_code == 422
