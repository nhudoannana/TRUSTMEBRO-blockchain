"""Run lab handlers in Node VM; real Web Crypto vectors, separate from browser QA."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['hash_vectors', 'hash_reset', 'signature', 'key_reset',
                                  'signature_reset', 'merkle', 'merkle_reset', 'errors'])
def test_lab_handlers_and_isolation(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const elements=new Map(),events={},calls=[],testCase=process.argv[1];
class Element {
 constructor(){this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 add(child){this.children.push(child);}
 querySelectorAll(){return [];}
 setAttribute(k,v){this[k]=v;}
 removeAttribute(k){delete this[k];}
 focus(){}
}
const document={title:'',documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},querySelectorAll(){return [];},createElement(){return new Element();}};
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
}
assert.ok(calls.every(url=>url.startsWith('/api/labs/')));
})();
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
