"""Run lab handlers in Node VM; real Web Crypto vectors, separate from browser QA."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['hash_vectors', 'hash_reset', 'signature', 'key_reset',
                                  'signature_reset', 'merkle', 'merkle_reset', 'errors',
                                  'comparison', 'comparison_reset', 'example_safety',
                                  'result_guidance', 'sha_navigation', 'sha_preservation',
                                  'lab_learning', 'merkle_svg', 'merkle_previews', 'metric_mapping', 'merkle_selection_stale', 'public_learning'])
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
 focus(){document.activeElement=this;}
}
const document={title:'',documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);},querySelectorAll(){return [];},createElement(){return new Element();},createElementNS(ns,tag){const e=new Element();e.tag=tag;return e;}};
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
if(testCase==='public_learning'){
 context.location.hash='#blocks';events.hashchange();await new Promise(r=>setImmediate(r));
 assert.equal($('blocks-theory').hidden,false);assert.equal(run('chainLab.result'),null);
 for(let i=0;i<4;i++)$('blocks-topic-'+i).onclick();
 context.location.hash='#sha';events.hashchange();$('sha-tab-practice').onclick();
 $('hash-a').value='abc';$('hash-b').value='abd';await run('compareHashes(event)');
 assert.match($('hash-difference').textContent,/122\/256/);assert.equal(calls.length,0);
}else if(testCase==='merkle_selection_stale'){
 $('merkle-leaves').value='A\nB\nC';$('merkle-proof').value='0';
 await run('computeMerkle(event)');
 const count=calls.length,proof=$('merkle-proof-result').textContent,tree=$('merkle-tree').children;
 $('merkle-proof').value='2';$('merkle-proof').onchange?.();
 assert.match($('merkle-status').textContent,/lần tính trước/);
 assert.equal($('merkle-proof-result').textContent,proof);assert.equal($('merkle-tree').children,tree);
 assert.equal(calls.length,count);await run('computeMerkle(event)');
 assert.doesNotMatch($('merkle-status').textContent,/lần tính trước/);
}else if(testCase==='lab_learning'){
 run('signature.key={key_handle:"keep"};signature.signed={signature_hex:"keep-signature"};chainLab.result={chain:["keep-chain"]};networkLab.handle="keep-network";networkLab.snapshot={keep:true};comparison.results.pow={keep:true}');
 const owners=run('[signature,chainLab,networkLab,comparison]');
 const snapshot=run('JSON.stringify([signature,chainLab,networkLab,comparison])');
 $('sig-message').value='Keep my message';$('merkle-leaves').value='Keep my leaves';$('chain-data').value='Keep my draft';
 for(const name of ['signatures','merkle','blocks','consensus','network']){
  assert.equal(run('labLearning["'+name+'"].tab'),'theory');
  assert.equal($(name+'-previous').disabled,true);$(name+'-previous').onclick();
  assert.equal(run('labLearning["'+name+'"].topic'),0);
  for(let i=1;i<4;i++){$(name+'-next').onclick();assert.equal($(name+'-lesson-'+i).hidden,false);assert.equal($(name+'-topic-'+i)['aria-pressed'],'true');}
  $(name+'-next').onclick();assert.equal($(name+'-practice').hidden,false);
  assert.equal(document.activeElement,$(run('labPracticeFocus["'+name+'"]')));
  $(name+'-tab-theory').onclick();$(name+'-topic-1').onclick();
  context.location.hash='#sha';events.hashchange();context.location.hash='#'+name;events.hashchange();
  assert.equal(run('labLearning["'+name+'"].topic'),1);assert.equal($(name+'-lesson-1').hidden,false);
  $(name+'-tab-theory').onkeydown({key:'End',preventDefault(){}});
  assert.equal($(name+'-tab-practice')['aria-selected'],'true');assert.equal($(name+'-tab-practice').tabIndex,0);
  $(name+'-tab-practice').onkeydown({key:'ArrowLeft',preventDefault(){}});
  assert.equal($(name+'-theory').hidden,false);
 }
 assert.equal(run('JSON.stringify([signature,chainLab,networkLab,comparison])'),snapshot);
 run('[signature,chainLab,networkLab,comparison]').forEach((owner,i)=>assert.equal(owner,owners[i]));
 assert.equal($('sig-message').value,'Keep my message');assert.equal($('merkle-leaves').value,'Keep my leaves');assert.equal($('chain-data').value,'Keep my draft');
 assert.equal(calls.length,0);assert.equal(run('hashToken'),0);
}else if(testCase==='sha_navigation'){
 assert.equal(run('shaTab'),'theory');assert.equal(run('shaTopic'),0);
 assert.equal($('sha-theory').hidden,false);assert.equal($('sha-practice').hidden,true);
 assert.equal($('sha-previous').disabled,true);
 $('sha-previous').onclick();assert.equal(run('shaTopic'),0);
 for(let i=1;i<=4;i++){
  $('sha-next').onclick();assert.equal(run('shaTopic'),i);
  assert.equal($('sha-lesson-'+i).hidden,false);
  assert.equal($('sha-topic-'+i)['aria-pressed'],'true');
  assert.equal($('sha-lesson-'+(i-1)).hidden,true);
 }
 run('selectShaTopic(99)');assert.equal(run('shaTopic'),4);
 $('sha-next').onclick();assert.equal(run('shaTopic'),4);assert.equal(run('shaTab'),'practice');
 assert.equal(document.activeElement,$('hash-a'));assert.equal($('sha-practice').hidden,false);
 $('sha-tab-theory').onclick();assert.equal(run('shaTopic'),4);
 $('sha-previous').onclick();assert.equal(run('shaTopic'),3);
 $('sha-topic-1').onclick();assert.equal(run('shaTopic'),1);
 let prevented=false;$('sha-tab-theory').onkeydown({key:'ArrowRight',preventDefault(){prevented=true;}});
 assert.equal(prevented,true);assert.equal(run('shaTab'),'practice');
 assert.equal(document.activeElement,$('sha-tab-practice'));assert.equal($('sha-tab-practice').tabIndex,0);
 assert.equal($('sha-tab-theory').tabIndex,-1);assert.equal($('sha-tab-practice')['aria-selected'],'true');
 $('sha-tab-practice').onkeydown({key:'Home',preventDefault(){}});assert.equal(run('shaTab'),'theory');
 assert.equal(calls.length,0);assert.equal(run('hashToken'),0);
}else if(testCase==='sha_preservation'){
 $('sha-tab-practice').onclick();$('hash-a').value='abc';$('hash-b').value='abd';
 await run('compareHashes(event)');
 const before=['hash-a','hash-b','hash-original','hash-edited','hash-difference','hash-status'].map(id=>[$(id).value,$(id).textContent]);
 const token=run('hashToken');context.crypto={subtle:{digest(){throw Error('Navigation must not compute');}}};
 $('sha-tab-theory').onclick();$('sha-topic-3').onclick();
 context.location.hash='#merkle';events.hashchange();context.location.hash='#sha';events.hashchange();
 assert.equal(run('shaTab'),'theory');assert.equal(run('shaTopic'),3);
 assert.equal($('sha-lesson-3').hidden,false);$('sha-tab-practice').onclick();
 assert.deepEqual(['hash-a','hash-b','hash-original','hash-edited','hash-difference','hash-status'].map(id=>[$(id).value,$(id).textContent]),before);
 assert.equal($('hash-result').hidden,false);assert.equal(run('hashToken'),token);assert.equal(calls.length,0);
 run('resetHash()');assert.equal($('hash-result').hidden,true);assert.equal(run('shaTab'),'practice');assert.equal(run('shaTopic'),3);
}else if(testCase==='example_safety'){
 let accepted=false,prompts=0;
 context.window.confirm=()=>{prompts++;return accepted;};
 $('merkle-leaves').value='My own data';
 $('merkle-one').onclick();assert.equal($('merkle-leaves').value,'My own data');
 assert.equal(calls.length,0);assert.equal(prompts,1);
 accepted=true;$('merkle-one').onclick();assert.notEqual($('merkle-leaves').value,'My own data');
 assert.equal(calls.length,0);assert.equal(run('merklePrevious'),null);
 $('chain-data').value='Keep this';accepted=false;$('chain-example').onclick();
 assert.equal($('chain-data').value,'Keep this');
 accepted=true;$('chain-example').onclick();assert.notEqual($('chain-data').value,'Keep this');
 assert.equal(calls.length,0);assert.equal(run('chainLab.result'),null);
 run('chainLab.busy=true');$('chain-data').value='Pending';$('chain-example').onclick();
 assert.equal($('chain-data').value,'Pending');
 $('merkle-leaves').value='';const before=prompts;$('merkle-odd').onclick();
 assert.equal(prompts,before);assert.equal(run('readLeaves($("merkle-leaves").value).length'),3);
 assert.equal(calls.length,0);
}else if(testCase==='result_guidance'){
 run('showSignature()');assert.equal($('sig-sign').disabled,true);
 const empty=$('sig-control-note').textContent;
 await run('signatureAction("create")');assert.equal($('sig-sign').disabled,false);
 assert.notEqual($('sig-control-note').textContent,empty);
 $('sig-message').value='Original';await run('signatureAction("sign")');
 assert.equal($('sig-original').disabled,false);
 await run('signatureAction("original")');const valid=$('sig-result').textContent;
 assert.equal($('sig-result').className,'result valid');
 $('sig-presented').value='Edited';await run('signatureAction("verify")');
 assert.equal($('sig-result').className,'result invalid');assert.notEqual($('sig-result').textContent,valid);
 assert.equal(run('signature.signed.message'),'Original');
 assert.equal(run('signature.signed.signature_hex'),'original-signature');
 context.data={root:'a'.repeat(64),levels:[['a'.repeat(64)]],proof:null};
 run('showMerkle(data,null,1)');assert.equal($('merkle-root').title,'a'.repeat(64));
 assert.equal($('merkle-root-full').textContent,'a'.repeat(64));
 assert.ok($('merkle-root').textContent.length<64);
}else if(testCase==='metric_mapping'){
 const parent=document.createElement('div');
 run('resultMetric($("metric-test"),"Attempts",null,"tries");resultMetric($("metric-test"),"Attempts",undefined,"tries")');
 assert.equal($('metric-test').children.length,0);
 run('resultMetric($("metric-test"),"Nonce",0,"nonce");resultMetric($("metric-test"),"Attempts",137,"tries")');
 assert.equal($('metric-test').children.length,2);
 assert.equal($('metric-test').children[0].children[1].textContent,'0');
 assert.equal($('metric-test').children[1].children[1].textContent,'137');
 run('powHash($("hash-test"),"0000abcdef",3)');
 assert.equal($('hash-test').children[0].children[0].children[0].textContent,'000');
 assert.equal($('hash-test').children[0].children[0].children[1].textContent,'0abcdef');
 run('powHash($("hash-not-target"),"00abcdef",3)');
 assert.equal($('hash-not-target').children[0].children[0].children.length,1);
 assert.equal(calls.length,0);
}else if(testCase==='hash_vectors'){
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
 assert.equal($('hash-metrics').children[0].children[1].textContent,'0.00');
 assert.equal($('hash-metrics').children[1].children[1].textContent,'0');
 $('hash-b').value='Changed';$('hash-b').oninput();
 assert.ok($('hash-result-context').textContent.includes('lần tính trước'));
 assert.equal($('hash-metrics').children[1].children[1].textContent,'0');
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
}else if(testCase==='merkle_previews'){
 const all=e=>[e,...e.children.flatMap(all)];
 context.inputs=['<img src=x>','', '  spaces  ', 'Last input'];
 context.data={levels:[['a','b','c','d'],['ab','cd'],['r']],root:'r',proof:null};
 run('showMerkle(data,null,4,inputs)');
 let nodes=all($('merkle-tree'));
 const leaves=nodes.filter(e=>e.dataset.node?.startsWith('0:'));
 assert.equal(leaves.length,4);
 assert.ok(all(leaves[0]).some(e=>e.textContent==='<img src=x>'));
 assert.ok(all(leaves[2]).some(e=>e.textContent==='  spaces  '));
 assert.equal(nodes.filter(e=>e.dataset.duplicateNote==='true').length,0);
 const details=nodes.find(e=>e.dataset.fullNode==='0:0');
 assert.ok(details.children.some(e=>e.textContent==='<img src=x>'));
 const levels=$('merkle-tree').children.find(e=>e.children[0]?.textContent==='Chi tiết các tầng');
 assert.notEqual(levels.open,true);
 leaves[0].onkeydown({key:' ',preventDefault(){}});assert.equal(levels.open,true);assert.equal(details.open,true);
 context.data={levels:[['a','b','c'],['ab','cc'],['r']],root:'r',proof:null};
 run('showMerkle(data,null,3,inputs)');nodes=all($('merkle-tree'));
 assert.equal(nodes.filter(e=>e.dataset.duplicateNote==='true').length,1);
 assert.equal(calls.length,0);
}else if(testCase==='merkle_svg'){
 const all=e=>[e,...e.children.flatMap(all)];
 const draw=(d,previous,count)=>{context.d=d;context.previous=previous;run('showMerkle(d,previous,'+count+')');return all($('merkle-tree'));};
 const d={levels:[['a','b','c'],['ab','cc'],['root']],root:'root',proof:{index:2,siblings:[['c','right'],['ab','left']],valid:false}};
 let nodes=draw(d,null,3),groups=nodes.filter(e=>e.tag==='g'&&e.dataset.node!==undefined),edges=nodes.filter(e=>e.tag==='path');
 assert.equal(groups.length,6);assert.equal(edges.length,6);
 assert.equal(edges.filter(e=>e.dataset.duplicate==='true').length,1);
 assert.ok(edges.some(e=>e.dataset.from==='0:2'&&e.dataset.to==='1:1'));
 assert.ok(edges.some(e=>e.dataset.from==='1:0'&&e.dataset.to==='2:0'));
 assert.equal(groups.filter(e=>e['class'].includes('proof-path')).length,3);
 assert.equal(groups.filter(e=>e['class'].includes('proof-sibling')).length,2);
 assert.ok($('merkle-proof-result').textContent.includes('không hợp lệ'));
 const leaf=groups.find(e=>e.dataset.node==='0:2');leaf.onkeydown({key:'Enter',preventDefault(){}});
 assert.equal(nodes.find(e=>e.dataset.fullNode==='0:2').open,true);
 assert.ok(Number(groups.find(e=>e.dataset.node==='2:0').dataset.y)<Number(leaf.dataset.y));
 const previous=structuredClone(d);d.levels[0][0]='new';d.levels[1][0]='new-parent';d.levels[2][0]='new-root';d.root='new-root';
 nodes=draw(d,previous,3);assert.equal(nodes.filter(e=>e.tag==='g'&&e.dataset.node!==undefined&&e['class'].includes('changed')).length,3);
 nodes=draw({levels:[['one']],root:'one',proof:{index:0,siblings:[],valid:true}},null,1);
 assert.equal(nodes.filter(e=>e.tag==='g'&&e.dataset.node!==undefined).length,1);assert.equal(nodes.filter(e=>e.tag==='path').length,0);
 assert.ok(nodes.find(e=>e.tag==='g'&&e.dataset.node!==undefined)['aria-label'].includes('Lá / Merkle root'));
 nodes=draw({levels:[['empty']],root:'empty',proof:null},null,0);
 assert.equal(nodes.filter(e=>e.tag==='g'&&e.dataset.node!==undefined).length,1);assert.equal(nodes.filter(e=>e.tag==='path').length,0);
 nodes=draw({levels:[['a','b','c','d','e'],['ab','cd','ee'],['abcd','eeee'],['r']],root:'r',proof:null},null,5);
 assert.equal(nodes.filter(e=>e.tag==='g'&&e.dataset.node!==undefined).length,11);
 assert.equal(nodes.filter(e=>e.tag==='path').length,12);
 assert.equal(nodes.filter(e=>e.tag==='path'&&e.dataset.duplicate==='true').length,2);
 assert.equal(calls.length,0);
}else if(testCase==='merkle'){
 assert.deepEqual(Array.from(run('readLeaves("")')),[]);
 assert.deepEqual(Array.from(run('readLeaves("a\\n\\n")')),['a','','']);
 $('merkle-leaves').value='a\nb\nc';await run('computeMerkle(event)');
 const previous=run('merklePrevious');tree.levels[0][0]='changed';tree.levels[1][0]='new-parent';tree.levels[2][0]='new-root';tree.root='new-root';
 await run('computeMerkle(event)');assert.equal($('merkle-root').textContent,'new-root');
 const descend=e=>[e,...e.children.flatMap(descend)];const nodes=descend($('merkle-tree')).filter(e=>e.className==='tree-level').flatMap(e=>e.children);
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
  const posMetrics=$('comparison-result-pos').children.find(e=>e.className==='result-metrics');
  assert.equal(posMetrics.children.length,1);
  assert.ok(!text(posMetrics).includes('Nonce'));assert.ok(!text(posMetrics).includes('Số lần thử'));
  const powMetrics=$('comparison-result-pow').children.find(e=>e.className==='result-metrics');
  assert.equal(powMetrics.children[1].children[1].textContent,'83');
  assert.equal(powMetrics.children[2].children[1].textContent,'84');
  const technical=$('comparison-result-pos').children.find(e=>e.className==='technical').children[1];
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
