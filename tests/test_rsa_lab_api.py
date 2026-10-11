"""RSA1 API calculations are real; injected clocks/failures exercise lifecycle limits."""
import base64
import json
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from api.wallet_api import app
from api import session_store
from tests.session_helpers import SessionTestClient

@pytest.fixture
def client():
    with SessionTestClient(app) as c:
        yield c

def key(c):
    r = c.post('/api/labs/rsa/keys', json={'purpose':'oaep'})
    assert r.status_code == 201, r.text
    return r.json()

def encrypt(c, k, text='TrustMeBro'):
    return c.post('/api/labs/rsa/encrypt', content=json.dumps({'message':text,'public_key_pem':k['public_key_pem']}), headers={'Content-Type':'application/json'})

def decrypt(c, k, cipher):
    return c.post('/api/labs/rsa/decrypt', json={'key_handle':k['key_handle'],'ciphertext_b64':cipher})

@pytest.mark.parametrize('text', ['', 'TrustMeBro', '  Hồ sơ\n你好 🌏  ', 'a'*190, '🌏'*47])
def test_actual_oaep_exact_roundtrip(client, text):
    k=key(client); r=encrypt(client,k,text); assert r.status_code==200,r.text
    d=r.json(); assert d['message']==text and d['message_utf8_bytes']==len(text.encode())
    assert len(base64.b64decode(d['ciphertext_b64'],validate=True))==256
    result=decrypt(client,k,d['ciphertext_b64']); assert result.status_code==200,result.text
    assert result.json()['decrypted'] is True
    assert result.json()['plaintext']==text and result.json()['plaintext_utf8_bytes']==len(text.encode())
    public=serialization.load_pem_public_key(k['public_key_pem'].encode())
    der=public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    assert k['public_key_fingerprint']==hashlib.sha256(der).hexdigest()
    assert public.key_size==2048 and public.public_numbers().e==65537
    assert not any('private' in field for field in k)

@pytest.mark.parametrize('text', ['a'*191,'🌏'*48,'\ud800'])
def test_utf8_budget_and_surrogate_rejected(client,text):
    k=key(client); assert encrypt(client,k,text).status_code==422

def test_wrong_key_tamper_and_oaep_hash_are_domain_failures(client):
    a,b=key(client),key(client); c=encrypt(client,a).json()['ciphertext_b64']
    for target,cipher in [(b,c),(a,base64.b64encode(bytes(256)).decode())]:
        d=decrypt(client,target,cipher); assert d.status_code==200
        assert d.json()['outcome']['code']=='decryption_failed'
        assert d.json()['decrypted'] is False and d.json()['plaintext'] is None
    pub=serialization.load_pem_public_key(a['public_key_pem'].encode())
    sha1=pub.encrypt(b'x',padding.OAEP(padding.MGF1(hashes.SHA1()),hashes.SHA1(),None))
    assert decrypt(client,a,base64.b64encode(sha1).decode()).json()['outcome']['code']=='decryption_failed'

def test_non_utf8_plaintext_is_not_oaep_failure(client):
    k=key(client); pub=serialization.load_pem_public_key(k['public_key_pem'].encode())
    c=pub.encrypt(b'\xff',padding.OAEP(padding.MGF1(hashes.SHA256()),hashes.SHA256(),None))
    d=decrypt(client,k,base64.b64encode(c).decode()).json()
    assert d['decrypted'] is True and d['plaintext'] is None
    assert d['outcome']['code']=='plaintext_not_utf8'

@pytest.mark.parametrize('cipher', ['', 'zz!', ' '*344, base64.b64encode(bytes(255)).decode(), base64.urlsafe_b64encode(b'\xff'*256).decode()])
def test_malformed_base64_is_format_error(client,cipher):
    k=key(client); assert decrypt(client,k,cipher).status_code==422

@pytest.mark.parametrize('kind',['bad','ec','1024','e3','private','double','tail'])
def test_public_key_policy_before_crypto(client,kind):
    k=key(client)
    if kind=='bad': pem='not PEM'
    elif kind=='ec': pem=ec.generate_private_key(ec.SECP256K1()).public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    elif kind in ('1024','e3','private'):
        p=rsa.generate_private_key(3 if kind=='e3' else 65537,1024 if kind=='1024' else 2048)
        pem=p.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode() if kind=='private' else p.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    elif kind=='double': pem=k['public_key_pem']*2
    else: pem=k['public_key_pem']+'junk'
    assert encrypt(client,{'public_key_pem':pem}).status_code==422

def test_key_ownership_reset_expiry_and_public_encrypt(client,monkeypatch):
    k=key(client); base='/api/labs/rsa/keys/'+k['key_handle']
    other=SessionTestClient(app)
    assert other.get(base).status_code==404
    assert other.delete(base).status_code==404
    assert decrypt(other,k,base64.b64encode(bytes(256)).decode()).status_code==404
    other.close()
    assert client.delete(base).json()=={'cleared':True}
    assert client.delete(base).json()=={'cleared':False}
    assert decrypt(client,k,base64.b64encode(bytes(256)).decode()).status_code==404
    assert encrypt(client,k).status_code==200
    from api import rsa_lab
    new=key(client); now=rsa_lab.time.monotonic()
    monkeypatch.setattr(rsa_lab.time,'monotonic',lambda:now+901)
    assert client.get('/api/labs/rsa/keys/'+new['key_handle']).status_code==404
    assert session_store.current_session().rsa_keys=={}

def test_key_capacity_no_lost_keys_and_unsupported_purpose(client):
    keys=[key(client) for _ in range(4)]
    assert client.post('/api/labs/rsa/keys',json={'purpose':'oaep'}).status_code==429
    assert all(client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==200 for k in keys)
    assert client.post('/api/labs/rsa/keys',json={'purpose':'unsupported'}).status_code==422
    assert client.post('/api/labs/rsa/sign',json={}).status_code==422

def test_key_and_crypto_operational_failures_release_guards(client,monkeypatch):
    k=key(client)
    from api import rsa_lab
    original=rsa_lab.generate_rsa_key
    def broken(): raise RuntimeError('private secret must not leak')
    with monkeypatch.context() as m:
        m.setattr(rsa_lab,'generate_rsa_key',broken)
        r=client.post('/api/labs/rsa/keys',json={'purpose':'oaep'})
        assert r.status_code==503 and 'private secret' not in r.text
    assert key(client)['key_handle']!=k['key_handle']
    with monkeypatch.context() as m:
        m.setattr(rsa_lab,'decrypt_text',lambda *args:(_ for _ in ()).throw(RuntimeError('secret')))
        r=decrypt(client,k,base64.b64encode(bytes(256)).decode())
        assert r.status_code==500 and r.json()['detail']['code']=='rsa_operation_failed'
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==200

def test_generation_session_and_global_limits(client,monkeypatch):
    key(client)
    from api import rsa_lab
    context=session_store.current_session()
    context.rsa_generation_lock.acquire()
    try: assert client.post('/api/labs/rsa/keys',json={'purpose':'oaep'}).status_code==429
    finally: context.rsa_generation_lock.release()
    assert rsa_lab.generation_slots.acquire(False) and rsa_lab.generation_slots.acquire(False)
    try: assert client.post('/api/labs/rsa/keys',json={'purpose':'oaep'}).status_code==429
    finally: rsa_lab.generation_slots.release();rsa_lab.generation_slots.release()
    assert key(client)

def test_rsa_independent_labs_and_journey_reset(client):
    k=key(client); sig=client.post('/api/labs/signatures/keys').json()
    fork=client.post('/api/labs/fork',json={}).json()
    client.post('/api/session/reset')
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==200
    client.delete('/api/labs/rsa/keys/'+k['key_handle'])
    assert client.post('/api/labs/signatures/sign',json={'key_handle':sig['key_handle'],'message':''}).status_code==200
    assert client.get('/api/labs/fork/'+fork['lab_handle']).status_code==200
    client.delete('/api/labs/fork/'+fork['lab_handle'])

def test_context_close_clears_private_keys(client):
    k=key(client); context=session_store.current_session();context.close()
    assert context.rsa_keys=={}
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==404

@pytest.mark.parametrize('body',[{}, {'purpose':'oaep','session_id':'fake'}, {'purpose':123}])
def test_key_schema_strict(client,body):
    assert client.post('/api/labs/rsa/keys',json=body).status_code==422

def test_absolute_expiry_is_not_extended_by_get(client,monkeypatch):
    k=key(client)
    from api import rsa_lab
    now=rsa_lab.time.monotonic()
    monkeypatch.setattr(rsa_lab.time,'monotonic',lambda:now+800)
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==200
    monkeypatch.setattr(rsa_lab.time,'monotonic',lambda:now+901)
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==404

def test_expiry_during_decrypt_discards_plaintext(client,monkeypatch):
    k=key(client);cipher=encrypt(client,k,'secret').json()['ciphertext_b64']
    from api import rsa_lab
    original=rsa_lab.decrypt_text;now=rsa_lab.time.monotonic()
    def expires(cipher,key):
        result=original(cipher,key)
        monkeypatch.setattr(rsa_lab.time,'monotonic',lambda:now+901)
        return result
    monkeypatch.setattr(rsa_lab,'decrypt_text',expires)
    r=decrypt(client,k,cipher)
    assert r.status_code==404 and 'secret' not in r.text

def test_private_decryption_and_reset_are_serialized(client,monkeypatch):
    k=key(client);cipher=encrypt(client,k,'held').json()['ciphertext_b64']
    from api import rsa_lab
    original=rsa_lab.decrypt_text;entered=threading.Event();release=threading.Event();deleting=threading.Event()
    def held(*args):
        entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(rsa_lab,'decrypt_text',held)
    def remove():
        deleting.set();return client.delete('/api/labs/rsa/keys/'+k['key_handle'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        operation=pool.submit(decrypt,client,k,cipher)
        assert entered.wait(5)
        removal=pool.submit(remove)
        try:
            assert deleting.wait(5) and not removal.done()
        finally: release.set()
        assert operation.result().json()['plaintext']=='held'
        assert removal.result().json()['cleared'] is True
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==404

def test_retiring_generation_does_not_publish_and_releases_slots(client,monkeypatch):
    key(client)
    from api import rsa_lab
    context=session_store.current_session();original=rsa_lab.generate_rsa_key
    def retire():
        private=original();context.retiring=True;return private
    with monkeypatch.context() as m:
        m.setattr(rsa_lab,'generate_rsa_key',retire)
        assert client.post('/api/labs/rsa/keys',json={'purpose':'oaep'}).status_code==503
    assert context.rsa_keys=={}
    assert key(client)

def test_pem_normalization_and_exact_crlf_text(client):
    k=key(client);formatted={'public_key_pem':'  '+k['public_key_pem'].replace('\n','\r\n')+'  '}
    r=encrypt(client,formatted,'a\r\nb');assert r.status_code==200
    assert decrypt(client,k,r.json()['ciphertext_b64']).json()['plaintext']=='a\r\nb'

def test_encrypt_schema_extra_type_and_oversized_public_key(client):
    k=key(client)
    for body in [{'message':123,'public_key_pem':k['public_key_pem']},
                 {'message':'','public_key_pem':k['public_key_pem'],'padding':'none'},
                 {'message':'','public_key_pem':'x'*2049}]:
        assert client.post('/api/labs/rsa/encrypt',json=body).status_code==422

# RSA2: actual PSS, independent of OAEP/Wallet contracts.
def pss_key(c):
    r=c.post('/api/labs/rsa/keys',json={'purpose':'pss'})
    assert r.status_code==201,r.text
    return r.json()

def pss_sign(c,k,text='TrustMeBro'):
    return c.post('/api/labs/rsa/sign',content=json.dumps({'key_handle':k['key_handle'],'message':text}),headers={'Content-Type':'application/json'})

def pss_verify(c,k,sig,text='TrustMeBro'):
    return c.post('/api/labs/rsa/verify',content=json.dumps({'message':text,'signature_b64':sig,'public_key_pem':k['public_key_pem']}),headers={'Content-Type':'application/json'})

@pytest.mark.parametrize('text',['','TrustMeBro','  H\u1ed3 s\u01a1\n\u4f60\u597d \U0001f30f  ','a'*4096,'\U0001f30f'*1024,'a\r\nb'])
def test_pss_actual_exact_text_and_parameters(client,text):
    k=pss_key(client);r=pss_sign(client,k,text);assert r.status_code==200,r.text
    d=r.json();raw=text.encode('utf-8');sig=base64.b64decode(d['signature_b64'],validate=True)
    assert len(sig)==256 and d['signature_bytes']==256
    assert d['message']==text and d['message_utf8_bytes']==len(raw)
    assert d['message_sha256']==hashlib.sha256(raw).hexdigest()
    assert d['salt_bytes']==32 and d['scheme']=='RSA-PSS' and d['hash']==d['mgf1_hash']=='SHA-256'
    public=serialization.load_pem_public_key(k['public_key_pem'].encode())
    public.verify(sig,raw,padding.PSS(padding.MGF1(hashes.SHA256()),32),hashes.SHA256())
    result=pss_verify(client,k,d['signature_b64'],text)
    assert result.status_code==200 and result.json()['valid'] is True
    assert result.json()['message_sha256']==d['message_sha256']

@pytest.mark.parametrize('text',['a'*4097,'\U0001f30f'*1025,'\ud800'])
def test_pss_utf8_limits_before_sign_or_verify(client,text):
    k=pss_key(client)
    assert pss_sign(client,k,text).status_code==422
    assert pss_verify(client,k,base64.b64encode(bytes(256)).decode(),text).status_code==422

def test_pss_changed_text_key_signature_and_randomness(client):
    a,b=pss_key(client),pss_key(client)
    first=pss_sign(client,a).json()['signature_b64'];second=pss_sign(client,a).json()['signature_b64']
    assert first!=second  # Observe real randomized output; never pin a signature fixture.
    raw=bytearray(base64.b64decode(first));raw[20]^=1
    for k,sig,text in [(a,first,'changed'),(b,first,'TrustMeBro'),(a,base64.b64encode(raw).decode(),'TrustMeBro')]:
        r=pss_verify(client,k,sig,text);assert r.status_code==200 and r.json()['valid'] is False
        assert r.json()['outcome']['code']=='signature_invalid'
    assert pss_verify(client,a,second).json()['valid']

@pytest.mark.parametrize('kind',['pkcs1','salt20','mgf1sha1'])
def test_pss_rejects_actual_wrong_padding_parameters(client,kind):
    private=rsa.generate_private_key(65537,2048)
    public={'public_key_pem':private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    pad=padding.PKCS1v15() if kind=='pkcs1' else padding.PSS(padding.MGF1(hashes.SHA1() if kind=='mgf1sha1' else hashes.SHA256()),20 if kind=='salt20' else 32)
    signature=base64.b64encode(private.sign(b'TrustMeBro',pad,hashes.SHA256())).decode()
    r=pss_verify(client,public,signature);assert r.status_code==200 and r.json()['valid'] is False

@pytest.mark.parametrize('sig',['','bad!',' '*344,base64.b64encode(bytes(255)).decode(),base64.urlsafe_b64encode(b'\xff'*256).decode()])
def test_pss_malformed_signature_is_422(client,sig):
    k=pss_key(client);r=pss_verify(client,k,sig)
    assert r.status_code==422
    assert 'signature_b64' in r.text

def test_pss_format_and_operational_failures_remain_distinct(client,monkeypatch):
    k=pss_key(client);sig=pss_sign(client,k).json()['signature_b64']
    assert pss_verify(client,{'public_key_pem':'private or invalid'},sig).status_code==422
    from api import rsa_lab
    for function,operation in [('verify_text',lambda:pss_verify(client,k,sig)),('sign_text',lambda:pss_sign(client,k))]:
        with monkeypatch.context() as m:
            m.setattr(rsa_lab,function,lambda *a:(_ for _ in ()).throw(RuntimeError('do not leak secret')))
            r=operation();assert r.status_code==500
            assert r.json()['detail']['code']=='rsa_operation_failed' and 'do not leak' not in r.text

def test_pss_purpose_ownership_and_public_after_delete(client):
    a=key(client);p=pss_key(client);sig=pss_sign(client,p).json()['signature_b64']
    assert pss_sign(client,a).status_code==409
    assert decrypt(client,p,base64.b64encode(bytes(256)).decode()).status_code==409
    other=SessionTestClient(app)
    try: assert pss_sign(other,p).status_code==404
    finally: other.close()
    assert client.delete('/api/labs/rsa/keys/'+p['key_handle']).json()['cleared']
    assert pss_sign(client,p).status_code==404 and pss_verify(client,p,sig).json()['valid']
    assert client.get('/api/labs/rsa/keys/'+a['key_handle']).status_code==200

def test_combined_rsa_capacity_is_per_purpose_and_total(client):
    oaep=[key(client) for _ in range(3)];pss=[pss_key(client) for _ in range(4)]
    assert client.post('/api/labs/rsa/keys',json={'purpose':'pss'}).status_code==429
    oaep.append(key(client))
    for purpose in ['pss','oaep']:
        assert client.post('/api/labs/rsa/keys',json={'purpose':purpose}).status_code==429
    assert len(session_store.current_session().rsa_keys)==8
    client.delete('/api/labs/rsa/keys/'+pss[0]['key_handle'])
    assert pss_key(client)
    assert all(client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==200 for k in oaep)

def test_pss_absolute_expiry_and_expiry_during_sign(client,monkeypatch):
    from api import rsa_lab
    k=pss_key(client);sig=pss_sign(client,k).json()['signature_b64'];now=rsa_lab.time.monotonic()
    original=rsa_lab.sign_text
    def slow(*args):
        result=original(*args)
        monkeypatch.setattr(rsa_lab.time,'monotonic',lambda:now+901)
        return result
    monkeypatch.setattr(rsa_lab,'sign_text',slow)
    assert pss_sign(client,k).status_code==404
    assert pss_verify(client,k,sig).json()['valid']
    assert client.get('/api/labs/rsa/keys/'+k['key_handle']).status_code==404

def test_pss_delete_serializes_with_sign(client,monkeypatch):
    from api import rsa_lab
    k=pss_key(client);context=session_store.current_session();entered=threading.Event();release=threading.Event()
    original=rsa_lab.sign_text
    def held(*args):entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(rsa_lab,'sign_text',held)
    with ThreadPoolExecutor(2) as pool:
        signing=pool.submit(lambda:pss_sign(client,k))
        assert entered.wait(5)
        deleting=pool.submit(lambda:client.delete('/api/labs/rsa/keys/'+k['key_handle']))
        try:
            assert context.rsa_key_lock.acquire(False) is False
            assert not deleting.done()
        finally:release.set()
        signed=signing.result(5);assert signed.status_code==200
        assert deleting.result(5).json()['cleared']
    assert pss_sign(client,k).status_code==404
    assert pss_verify(client,k,signed.json()['signature_b64']).json()['valid']

def test_pss_journey_reset_and_session_close(client):
    a,p=key(client),pss_key(client);s=pss_sign(client,p).json()['signature_b64']
    client.post('/api/session/reset')
    assert pss_sign(client,p).status_code==200 and client.get('/api/labs/rsa/keys/'+a['key_handle']).status_code==200
    context=session_store.current_session();context.close()
    assert not context.rsa_keys
    assert pss_verify(client,p,s).json()['valid']


@pytest.mark.parametrize('field,value',[('signature_b64',123),('message',123),('public_key_pem','x'*2049),('extra',True)])
def test_pss_strict_verify_schema(client,field,value):
    p=pss_key(client)
    body={'message':'','signature_b64':base64.b64encode(bytes(256)).decode(),'public_key_pem':p['public_key_pem']}
    body[field]=value;assert client.post('/api/labs/rsa/verify',json=body).status_code==422

def test_pss_private_pem_rejected_before_verify(client):
    private=rsa.generate_private_key(65537,2048)
    pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    assert pss_verify(client,{'public_key_pem':pem},base64.b64encode(bytes(256)).decode()).status_code==422
