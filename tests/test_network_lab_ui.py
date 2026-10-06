"""Behavioral Node-VM checks; these do not constitute browser verification."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['controls', 'propagation', 'reconnect', 'timeout',
                                  'errors', 'stale_reset', 'page_exit', 'read_timeout', 'http_mode', 'http_reconnect'])
def test_network_lab_handlers(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),events={},calls=[],beacons=[],testCase=process.argv[1];
class Element {
 constructor(id){this.id=id;this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 add(child){this.children.push(child);}
 querySelectorAll(){return [];}
 set innerHTML(value){throw Error('Unsafe HTML rendering');}
 setAttribute(k,v){this[k]=v;}
 removeAttribute(k){delete this[k];}
 focus(){this.focused=true;}
}
const document={documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);},querySelectorAll(){return [];},createElement(){return new Element();}};
let clock=0,reads=0,handleCount=0,deferred,holdInit=['controls','page_exit'].includes(testCase),holdRead=false,errorCode=0;
const tip='a'.repeat(64),genesis='0'.repeat(64),text=e=>e.textContent+e.children.map(text).join(' ');
let snapshot,manuallySynced=false;
function fresh(handle){return {lab_handle:handle,credential_id:null,transaction:null,mining:null,
 nodes:[1,2,3].map(i=>({node_id:'Node-'+i,status:'ONLINE',height:0,block_count:1,tip_hash:genesis,pending_count:0,chain_valid:true,verification:null,local_chain_warning:null})),
 online_nodes_agree:true,online_nodes_valid:true,online_nodes_synchronized:true,all_nodes_synchronized:true};}
function flags(){
 const online=snapshot.nodes.filter(n=>n.status==='ONLINE');
 snapshot.online_nodes_agree=new Set(online.map(n=>n.height+':'+n.tip_hash)).size===1;
 snapshot.online_nodes_valid=online.every(n=>n.chain_valid);
 snapshot.online_nodes_synchronized=snapshot.online_nodes_agree&&snapshot.online_nodes_valid;
 snapshot.all_nodes_synchronized=online.length===3&&snapshot.online_nodes_synchronized;
}
function catchUp(node){Object.assign(node,{height:1,block_count:2,tip_hash:tip,pending_count:0,verification:{status:'VERIFIED',reason:'verified <safe>'},local_chain_warning:null});}
const ok=data=>({ok:true,json:async()=>structuredClone(data)});
const context=vm.createContext({document,TextEncoder,Uint8Array,AbortController,Option:class extends Element{constructor(label,value){super();this.textContent=label;this.value=value;}},
 Date:{now:()=>clock},setTimeout(fn,ms){if(ms<=250){clock+=ms;queueMicrotask(fn);}else if(testCase==='read_timeout'){clock+=ms;queueMicrotask(fn);}return 1;},clearTimeout(){},
 location:{hash:'#network'},window:{addEventListener:(k,f)=>events[k]=f},navigator:{sendBeacon:url=>beacons.push(url)},localStorage:{getItem:()=>null,setItem(){}},structuredClone,
 fetch:async(url,options={})=>{
  assert.ok(url.startsWith('/api/labs/network'));const method=options.method||'GET';calls.push({url,method,body:options.body});
  if(errorCode)return {ok:false,status:errorCode,json:async()=>({detail:'Exact backend error <safe>'})};
  if(method==='POST'&&url==='/api/labs/network'){
   const data=fresh('handle-'+(++handleCount));data.transport=options.body?JSON.parse(options.body).transport:'queue';snapshot=data;
   if(holdInit){holdInit=false;await new Promise(r=>deferred=r);}return ok(data);
  }
  if(url.endsWith('/reset'))return ok({cleared:true});
  if(method==='GET'){
   reads++;
   if(testCase==='read_timeout')await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{name:'AbortError'}))));
   const data=structuredClone(snapshot);
   if(holdRead){holdRead=false;await new Promise(r=>deferred=r);return ok(data);}
   if(snapshot.credential_id&&testCase!=='timeout')snapshot.nodes.filter(n=>n.status==='ONLINE'&&(!testCase.startsWith('http_')||n.node_id!=='Node-3'||manuallySynced)).forEach(catchUp);
   flags();return ok(snapshot);
  }
  if(url.endsWith('/status')){
   const online=JSON.parse(options.body).online;snapshot.nodes[2].status=online?'ONLINE':'OFFLINE';flags();
   return ok({changed:true,catch_up_requested:online&&snapshot.transport!=='http',snapshot});
  }
  if(url.endsWith('/mine')){
   snapshot.credential_id='credential';snapshot.transaction={tx_id:'tx'};snapshot.mining={block:{height:1,difficulty:3,hash:tip}};
   catchUp(snapshot.nodes[0]);snapshot.nodes[1].pending_count=1;
   if(snapshot.nodes[2].status==='OFFLINE'){snapshot.nodes[2].verification={status:'NOT_FOUND'};snapshot.nodes[2].local_chain_warning='stale node <safe>';}flags();
   return ok({mined:true,block:snapshot.mining.block,snapshot});
  }
  if(url.endsWith('/sync')){manuallySynced=true;snapshot.nodes.filter(n=>n.status==='ONLINE').forEach(n=>{if(snapshot.credential_id)catchUp(n);});flags();return ok({completed:snapshot.all_nodes_synchronized,reason:snapshot.all_nodes_synchronized?null:'Node offline',snapshot});}
  throw Error('Unexpected request '+url);
 }});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),context);
const $=id=>document.getElementById(id),run=s=>vm.runInContext(s,context),tick=()=>new Promise(r=>setImmediate(r));
const posts=suffix=>calls.filter(c=>c.method==='POST'&&c.url.endsWith(suffix));
(async()=>{
 assert.equal($('lab-network').hidden,false);assert.equal($('lab-consensus').hidden,true);
 assert.equal($('network-mine').disabled,true);assert.equal($('network-online').disabled,true);
 await run('networkLabAction("mine")');assert.equal(calls.length,0);
 if(testCase.startsWith('http_')){
  assert.equal(typeof $('network-transport').onchange,'function');
  $('network-transport').value='http';$('network-transport').onchange();
  assert.equal(calls.length,0); // Selection alone must not allocate servers.
 }
 if(testCase==='controls'||testCase==='page_exit'){
  const pending=run('networkLabAction("init")');await tick();
  assert.equal($('network-init').disabled,true);await run('networkLabAction("init")');await run('resetNetworkLab()');assert.equal(calls.length,1);
  if(testCase==='page_exit')events.pagehide();deferred();await pending;
  if(testCase==='page_exit'){assert.equal(run('networkLab.handle'),null);assert.equal(posts('/handle-1/reset').length,1);return;}
 }else await run('networkLabAction("init")');
 assert.equal(run('networkLab.handle'),'handle-1');assert.equal($('network-offline').disabled,false);assert.equal($('network-online').disabled,true);
 assert.equal($('network-mine').disabled,false);assert.equal($('network-reset').disabled,false);
 if(testCase==='http_mode'){
  assert.equal(JSON.parse(calls[0].body).transport,'http');assert.equal($('network-transport').disabled,true);
  assert.ok($('network-transport-note').textContent.includes('HTTP'));
  $('network-transport').value='queue';$('network-transport').onchange();
  assert.equal(run('networkLab.transport'),'http');assert.equal(calls.length,1);
  await run('resetNetworkLab()');assert.equal($('network-transport').disabled,false);
  assert.equal(run('networkLab.transport'),'http');return;
 }
 if(testCase==='http_reconnect'){
  await run('networkLabAction("offline")');await run('networkLabAction("mine")');
  const readsBefore=reads;
  await run('networkLabAction("online")');
  assert.equal(reads,readsBefore);assert.equal(posts('/sync').length,0);
  assert.equal(run('networkLab.snapshot.nodes[2].height'),0);
  assert.equal(run('networkLab.snapshot.all_nodes_synchronized'),false);
  assert.ok($('network-status').textContent.includes('Đồng bộ'));
  assert.ok(!text($('network-summary')).includes('Cả ba node ONLINE'));
  await run('networkLabAction("sync")');assert.equal(posts('/sync').length,1);
  assert.equal(run('networkLab.snapshot.all_nodes_synchronized'),true);return;
 }
 if(testCase==='controls'){
  await run('networkLabAction("offline")');assert.equal($('network-offline').disabled,true);assert.equal($('network-online').disabled,false);
  assert.equal(run('networkLab.snapshot.nodes[2].status'),'OFFLINE');assert.equal($('network-mine').disabled,false);
  context.location.hash='#sha';events.hashchange();context.location.hash='#network';events.hashchange();
  assert.equal(run('networkLab.handle'),'handle-1');assert.equal($('network-title').focused,true);
 }else if(['propagation','reconnect','timeout'].includes(testCase)){
  await run('networkLabAction("offline")');await run('networkLabAction("mine")');
  if(testCase==='timeout'){
   assert.ok(reads>1&&reads<=20);assert.equal(run('networkLab.pollFailed'),true);
   assert.equal($('network-error').hidden,false);assert.ok(!$('network-summary').className.includes('valid'));
   assert.equal(run('networkLab.snapshot.nodes[1].height'),0);assert.equal(run('networkLab.busy'),false);
   assert.equal($('network-refresh').disabled,false);return;
  }
  assert.deepEqual(Array.from(run('networkLab.snapshot.nodes.map(n=>n.height)')),[1,1,0]);
  assert.equal(run('networkLab.snapshot.all_nodes_synchronized'),false);assert.equal($('network-mine').disabled,true);
  assert.ok(text($('network-nodes')).includes('NOT_FOUND'));assert.ok(text($('network-nodes')).includes('stale node <safe>'));
  assert.equal(JSON.parse($('network-technical').textContent).mining.block.hash,tip);
  if(testCase==='reconnect'){
   await run('networkLabAction("sync")');assert.equal(run('networkLab.snapshot.nodes[2].height'),0);
   assert.equal(run('networkLab.snapshot.all_nodes_synchronized'),false);
   await run('networkLabAction("online")');assert.equal(posts('/sync').length,1); // no extra sync on reconnect
   assert.equal(run('networkLab.snapshot.all_nodes_synchronized'),true);assert.ok($('network-summary').className.includes('valid'));
   assert.ok(Array.from(run('networkLab.snapshot.nodes')).every(n=>n.verification.status==='VERIFIED'&&n.tip_hash===tip));
  }
 }else if(testCase==='errors'){
  errorCode=503;await run('networkLabAction("sync")');assert.equal($('network-error').textContent,'Exact backend error <safe>');
  assert.equal(run('networkLab.busy'),false);assert.equal($('network-refresh').disabled,false);
  errorCode=404;await run('networkLabAction("refresh")');assert.equal(run('networkLab.handle'),null);assert.equal($('network-init').disabled,false);
  assert.equal($('network-mine').disabled,true);assert.equal($('network-error').textContent,'Exact backend error <safe>');return;
 }else if(testCase==='stale_reset'){
  run('signature.key={key_handle:"other-lab"};comparison.results.pow={created:true};hashToken=37;merklePrevious={root:"keep"}');
  holdRead=true;const pending=run('networkLabAction("refresh")');await tick();
  assert.equal($('network-reset').disabled,false);await run('resetNetworkLab()');await run('networkLabAction("init")');
  deferred();await pending;assert.equal(run('networkLab.handle'),'handle-2');assert.equal(run('networkLab.snapshot.lab_handle'),'handle-2');
  assert.equal(run('signature.key.key_handle'),'other-lab');assert.equal(run('comparison.results.pow.created'),true);
  assert.equal(run('hashToken'),37);assert.equal(run('merklePrevious.root'),'keep');assert.equal(posts('/handle-1/reset').length,1);return;
 }else if(testCase==='read_timeout'){
  await run('networkLabAction("refresh")');assert.equal($('network-error').hidden,false);assert.equal(run('networkLab.busy'),false);return;
 }
 await run('resetNetworkLab()');assert.equal(run('networkLab.handle'),null);assert.equal($('network-nodes').children.length,0);
 assert.equal($('network-init').disabled,false);assert.equal($('network-sync').disabled,true);
 await run('networkLabAction("init")');events.pagehide();assert.ok(beacons.includes('/api/labs/network/handle-2/reset'));
 assert.equal(run('networkLab.handle'),null);
})();
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
