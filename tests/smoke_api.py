import urllib.request, urllib.error, json

# GET wallets - confirm no private key
r = urllib.request.urlopen('http://127.0.0.1:8000/api/wallets')
data = json.loads(r.read())
for w in data:
    assert 'private_key_pem' not in w and 'private_key' not in w, 'PRIVATE KEY LEAK!'
print('GET /api/wallets: no private key present -- PASS')

# POST create
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/wallets',
    data=json.dumps({'name': 'Test Org Live'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
r = urllib.request.urlopen(req)
assert r.status == 201
created = json.loads(r.read())
assert 'private_key_pem' not in created
assert len(created['public_key_hex']) == 130
print('POST /api/wallets: no private key, pub key 130 chars -- PASS id=' + created['id'])

# POST empty name - expect 422
try:
    req2 = urllib.request.Request(
        'http://127.0.0.1:8000/api/wallets',
        data=json.dumps({'name': ''}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    urllib.request.urlopen(req2)
    print('POST empty name: FAIL (should have raised)')
except urllib.error.HTTPError as e:
    assert e.code == 422
    print('POST empty name: 422 returned -- PASS')

# GET by ID
r2 = urllib.request.urlopen('http://127.0.0.1:8000/api/wallets/' + created['id'])
fetched = json.loads(r2.read())
assert fetched['public_key_hex'] == created['public_key_hex']
print('GET /api/wallets/{id}: consistency -- PASS')

# GET unknown
try:
    urllib.request.urlopen('http://127.0.0.1:8000/api/wallets/NOTEXIST')
except urllib.error.HTTPError as e:
    assert e.code == 404
    print('GET unknown id: 404 -- PASS')

print('')
print('All live API checks passed.')
