"""Reviewed release gate: only the approved initial subset reaches clients."""
import json
from collections import Counter
from pathlib import Path
import pytest

SOURCE_IDS = [23,25,61,62,67,98,100,101,102,104,109,110,125,158,159,160]
IDS = {f"src-{n:03}" for n in SOURCE_IDS} | {
    f"lab-{topic}-{n:02}" for topic, count in
    [('ecdsa',2),('merkle',4),('fork',4),('oaep',4),('pss',6)]
    for n in range(1,count+1)}
BANK = Path('ui/quiz_questions.json')

def test_reviewed_subset_and_stable_ids():
    bank = json.loads(BANK.read_text(encoding='utf-8'))
    assert bank['schemaVersion'] == 1
    assert bank['reviewedAgainst'] == '1226846e7a60a18d40f48cff764c8173cb4fc367'
    rows = bank['questions']
    assert len(rows) == 36 and {q['id'] for q in rows} == IDS
    assert Counter(q['topicId'] for q in rows) == dict(sha=8,ecdsa=3,blocks=2,merkle=7,fork=4,oaep=6,pss=6)
    for q in rows:
        assert q['scope'] == 'implemented-labs' and q['reviewStatus'] == 'reviewed'
        assert [o['id'] for o in q['options']] == list('abcd')
        assert len({o['text'] for o in q['options']}) == 4
        assert q['correctOptionId'] in 'abcd'
        assert q['explanation'].strip() and q['evidence']
        assert q['labLinks']
        for link in q['labLinks']:
            assert link['href'] in {f'/ui/labs.html#{t}' for t in ['sha','signatures','blocks','merkle','fork','rsa-oaep','rsa-pss']}
    assert not {31,74,386} & {q['sourceId'] for q in rows if q['sourceId']}

def test_learner_facing_prompts_and_fixed_keys():
    rows = json.loads(BANK.read_text(encoding='utf-8'))['questions']
    # Source keys and stable new keys are checked independently of the runtime validator.
    expected = {23:'c',25:'a',61:'c',62:'a',67:'c',98:'d',100:'b',101:'b',102:'c',104:'c',109:'b',110:'c',125:'b',158:'a',159:'d',160:'c'}
    for q in rows:
        visible = q['prompt'] + ' '.join(o['text'] for o in q['options'])
        assert not any(s in visible for s in ['/api/', 'handle', 'HTTP 200', 'HTTP200', 'sign_message', 'salt_length', 'leftHex'])
        if q['sourceId']: assert q['correctOptionId'] == expected[q['sourceId']]
        else:
            keys={'ecdsa':'bd','merkle':'acbd','fork':'acbd','oaep':'bcad','pss':'bcadbc'}
            topic,num=q['id'].removeprefix('lab-').rsplit('-',1)
            assert q['correctOptionId'] == keys[topic][int(num)-1]

def test_links_resolve_to_existing_labs_and_utf8_hash_vector():
    import hashlib
    html=Path('ui/labs.html').read_text(encoding='utf-8')
    rows=json.loads(BANK.read_text(encoding='utf-8'))['questions']
    for q in rows:
        for link in q['labLinks']:
            assert f'id="lab-{link["href"].split("#")[1]}"' in html
    empty=next(q for q in rows if q['id']=='src-125')
    assert empty['options'][1]['text'].startswith(hashlib.sha256(b'').hexdigest()[:8])
