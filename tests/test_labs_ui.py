"""Run lab handlers in Node VM; real Web Crypto vectors, separate from browser QA."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['hash_vectors', 'hash_reset', 'signature', 'key_reset',
                                  'signature_reset', 'merkle', 'merkle_reset', 'errors',
                                  'comparison', 'comparison_reset'])
def test_lab_handlers_and_isolation(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const elements=new Map(),events={},calls=[],requests=[],testCase=process.argv[1];
const comparisonControls=['comparison-pow','comparison-pos','comparison-holder','comparison-title','comparison-date','comparison-online','comparison-sample','comparison-submit'];
class Element {
 constructor(id){this.id=id;this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};this.checked=false;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 add(child){this.children.push(child);}
 querySelectorAll(){return this.id==='comparison-form'?comparisonControls.map(id=>document.getElementById(id)):[];}
 set innerHTML(value){throw Error('Unsafe HTML rendering');}
 setAttribute(k,v){this[k]=v;}
 removeAttribute(k){delete this[k];}
 focus(){}
}
const document={title:'',documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);},querySelectorAll(){return [];},createElement(){return new Element();}};
const storage=new Map(),nativeCrypto=crypto.webcrypto;
let deferred,held=false;
const key={key_handle:'handle',public_key_hex:'key',address:'a'.repeat(40),curve:'secp256k1'};
const tree={leaf_hashes:['a','b','c'],levels:[['a','b','c'],['d','e'],['f']],root:'f',proof:null};
const context=vm.createContext({document,crypto:nativeCrypto,TextEncoder,Uint8Array,Option:class extends Element{constructor(label,value){super();this.textContent=label;this.value=value;}},location:{hash:'#sha'},window:{addEventListener:(k,f)=>events[k]=f},navigator:{sendBeacon(url){calls.push(url);}},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},console,
fetch:async(url,options)=>{
 assert.ok(url.startsWith('/api/labs/'));calls.push(url);
 if(testCase==='errors')return {ok:false,status:422,json:async()=>({detail:[{msg:'Actual validation error'}]})};
 if(testCase==='key_reset'&&url.endsWith('/keys')&&!held){held=true;await new Promise(r=>deferred=r);}
 if(testCase==='signature_reset'&&url.endsWith('/verify')&&!held){held=true;await new Promise(r=>deferred=r);}
 if(testCase==='merkle_reset'&&url.endsWith('/merkle')){await new Promise(r=>deferred=r);}
 if(url.endsWith('/consensus/run')){
  const body=JSON.parse(options.body);requests.push(body);
  if(testCase==='comparison_reset'&&!held){held=true;await new Promise(r=>deferred=r);}
  const created=body.node_online&&body.include_sample;
  return {ok:true,json:async()=>({mode:body.mode,node_id:'actual-backend-node',node_status:body.node_online?'ONLINE':'OFFLINE',
   created,stage:created?'complete':body.node_online?'creation':'submission',reason:created?null:'Verbatim backend rejection <sample>',
   transaction_ids:created?['signed-tx']:[],pending_count:0,seconds:0.123456,block:created?{height:1,difficulty:3,nonce:83}:null,attempts:body.mode==='pow'?84:null,
   issuer:{name:'Same organization <issuer>',address:'a'.repeat(40),public_key_hex:'issuer-key'},
   signer:body.mode==='pos'&&created?{name:'Same organization <validator>',address:'b'.repeat(40),public_key_hex:'validator-key',stake:300,selection_weight:.3}:null,
   chain_valid:true,validity_reason:'real validator reason',seed:42,stake_mode:'HYBRID'})};
 }
 let data;
 if(url.endsWith('/keys'))data=key;
 else if(url.endsWith('/reset'))data={cleared:true};
 else if(url.endsWith('/sign'))data={...key,message:JSON.parse(options.body).message,signature_hex:'original-signature'};
 else if(url.endsWith('/verify')){const body=JSON.parse(options.body);assert.equal(body.signature_hex,'original-signature');data={valid:body.message==='Original'&&body.public_key_hex==='key'};}
 else data=structuredClone(tree);
 return {ok:true,json:async()=>data};
},structuredClone});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),context);
const $=id=>document.getElementById(id),run=s=>vm.runInContext(s,context),event={preventDefault(){}};
context.event=event;
(async()=>{
if(testCase==='hash_vectors'){
 assert.equal(await run('hashText("")'),'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
 assert.equal(await run('hashText("abc")'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
 const text='Hồ sơ 🌏';context.text=text;
 assert.equal(await run('hashText(text)'),crypto.createHash('sha256').update(text,'utf8').digest('hex'));
 assert.equal(run('changedHashBits("0".repeat(64),"f".repeat(64))'),256);
 assert.equal(run('changedHashBits("0".repeat(64),"0".repeat(63)+"1")'),1);
 $('hash-a').value='abc';$('hash-b').value='';await run('compareHashes(event)');
 assert.equal($('hash-original').textContent.length,64);assert.equal($('hash-edited').textContent.length,64);
 const different=$('hash-difference').textContent;
 $('hash-b').value='abc';await run('compareHashes(event)');
 assert.equal(run('changedHashBits($("hash-original").textContent,$("hash-edited").textContent)'),0);
 assert.ok($('hash-difference').textContent.startsWith('0/256'));
 assert.notEqual($('hash-difference').textContent,different);
 assert.equal(calls.length,0);
 run('resetHash()');assert.equal($('hash-result').hidden,true);
}else if(testCase==='hash_reset'){
 context.crypto={subtle:{digest:async()=>new Promise(r=>{if(!deferred)deferred=[];deferred.push(r);})}};
 const pending=run('compareHashes(event)');run('resetHash()');for(const resolve of deferred)resolve(new ArrayBuffer(32));await pending;
 assert.equal($('hash-result').hidden,true);assert.equal($('hash-original').textContent,'');
}else if(testCase==='key_reset'){
 const pending=run('signatureAction("create")');await Promise.resolve();await run('resetSignature()');deferred();await pending;
 assert.equal(run('signature.key'),null);assert.ok(calls.includes('/api/labs/signatures/keys/handle/reset'));
}else if(['signature','signature_reset'].includes(testCase)){
 await run('signatureAction("create")');$('sig-message').value='Original';await run('signatureAction("sign")');
 if(testCase==='signature_reset'){
  const pending=run('signatureAction("original")');await Promise.resolve();await run('resetSignature()');deferred();await pending;
  assert.equal(run('signature.result'),null);assert.equal($('sig-result').hidden,true);
 }else{
  await run('signatureAction("original")');assert.equal(run('signature.result.valid'),true);
  $('sig-presented').value='<img src=x onerror=alert(1)>';await run('signatureAction("verify")');
  assert.equal(run('signature.result.valid'),false);assert.equal(run('signature.signed.signature_hex'),'original-signature');
  $('sig-presented').value='Original';run('signature.other={public_key_hex:"wrong",address:"b".repeat(40)}');$('sig-key-choice').value='other';
  await run('signatureAction("verify")');assert.equal(run('signature.result.valid'),false);
  await run('resetSignature()');assert.equal(run('signature.key'),null);assert.equal($('sig-signature').textContent,'');
 }
}else if(testCase==='merkle'){
 assert.deepEqual(Array.from(run('readLeaves("")')),[]);
 assert.deepEqual(Array.from(run('readLeaves("a\\n\\n")')),['a','','']);
 $('merkle-leaves').value='a\nb\nc';await run('computeMerkle(event)');
 const previous=run('merklePrevious');tree.levels[0][0]='changed';tree.levels[1][0]='new-parent';tree.levels[2][0]='new-root';tree.root='new-root';
 await run('computeMerkle(event)');assert.equal($('merkle-root').textContent,'new-root');
 const nodes=$('merkle-tree').children.filter(e=>e.className==='tree-level').flatMap(e=>e.children);
 assert.equal(nodes.filter(e=>e.className.includes('changed')).length,3);
 assert.equal(nodes.filter(e=>!e.className.includes('changed')).length,3);
 run('resetMerkle()');assert.equal($('merkle-result').hidden,true);assert.equal(run('merklePrevious'),null);
}else if(testCase==='merkle_reset'){
 const pending=run('computeMerkle(event)');await Promise.resolve();run('resetMerkle()');deferred();await pending;
 assert.equal($('merkle-result').hidden,true);assert.equal(run('merklePrevious'),null);
}else if(testCase==='errors'){
 await run('signatureAction("create")');assert.equal($('sig-error').textContent,'Actual validation error');
 await run('computeMerkle(event)');assert.equal($('merkle-error').textContent,'Actual validation error');
 await run('runComparison(event)');assert.equal($('comparison-error').textContent,'Actual validation error');
 assert.equal(run('comparison.busy'),false);assert.equal($('comparison-submit').disabled,false);
 assert.equal($('comparison-result-pow').hidden,true);
}else if(['comparison','comparison_reset'].includes(testCase)){
 context.location.hash='#consensus';events.hashchange();assert.equal($('lab-consensus').hidden,false);assert.equal($('lab-sha').hidden,true);
 assert.equal(run('comparison.mode'),'pow');assert.equal($('comparison-pow').checked,true);
 $('comparison-holder').value='Same holder';$('comparison-title').value='<img src=x onerror=alert(1)>';$('comparison-date').value='2026-10-01';
 $('comparison-online').checked=$('comparison-sample').checked=true;
 if(testCase==='comparison_reset'){
  const pending=run('runComparison(event)');await Promise.resolve();assert.equal($('comparison-submit').disabled,true);
  await run('runComparison(event)');assert.equal(requests.length,1);
  run('resetComparison()');assert.equal($('comparison-submit').disabled,false);
  $('comparison-pos').onchange();await run('runComparison(event)');
  assert.equal(run('comparison.results.pos.created'),true);
  deferred();await pending;
  assert.equal(run('comparison.results.pow'),null);assert.equal(run('comparison.results.pos.mode'),'pos');
  assert.equal($('comparison-result-pow').hidden,true);assert.equal(run('comparison.busy'),false);
 }else{
  await run('runComparison(event)');assert.equal(run('comparison.results.pow.created'),true);
  $('comparison-pos').onchange();assert.equal(run('comparison.mode'),'pos');assert.equal($('comparison-pos').checked,true);
  await run('runComparison(event)');assert.equal(run('comparison.results.pos.signer.public_key_hex'),'validator-key');
  assert.equal(run('comparison.results.pos.issuer.public_key_hex'),'issuer-key');
  assert.equal($('comparison-result-pow').hidden,false);assert.equal($('comparison-result-pos').hidden,false);
  for(const field of ['holder_name','title','issue_date'])assert.equal(requests[0][field],requests[1][field]);
  const text=e=>e.textContent+e.children.map(text).join(' ');
  assert.ok(text($('comparison-result-pos')).includes('actual-backend-node'));
  assert.ok(text($('comparison-result-pos')).includes('0.1235'));
  const technical=$('comparison-result-pos').children.find(e=>e.children.length===2).children[1];
  assert.equal(JSON.parse(technical.textContent).seconds,.123456);
  assert.notEqual(JSON.parse(technical.textContent).issuer.public_key_hex,JSON.parse(technical.textContent).signer.public_key_hex);
  $('comparison-sample').checked=false;$('comparison-sample').oninput();
  assert.equal(run('comparison.results.pow'),null);assert.equal(run('comparison.results.pos'),null);
  await run('runComparison(event)');assert.equal(run('comparison.results.pos.created'),false);
  assert.ok(text($('comparison-result-pos')).includes('Verbatim backend rejection <sample>'));
  $('comparison-online').checked=false;$('comparison-online').oninput();await run('runComparison(event)');
  assert.ok(text($('comparison-result-pos')).includes('OFFLINE'));
  run('resetComparison()');assert.equal($('comparison-result-pos').hidden,true);assert.equal($('comparison-result-pow').hidden,true);
 }
}
assert.ok(calls.every(url=>url.startsWith('/api/labs/')));
})();
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
