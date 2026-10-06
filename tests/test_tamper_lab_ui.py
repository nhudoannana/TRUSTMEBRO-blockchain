"""Node-VM handler tests, separate from browser verification."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['controls', 'corruption', 'timeout', 'errors',
                                  'stale_reset', 'page_exit', 'read_timeout', 'failed_prepare'])
def test_tamper_lab_handlers(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),events={},calls=[],testCase=process.argv[1];
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
let clock=0,reads=0,count=0,deferred,holdInit=['controls','page_exit'].includes(testCase),holdRead=false,errorCode=0;
const tip='a'.repeat(64),original='Original title <safe>',edited='<img src=x onerror=alert(1)>',text=e=>e.textContent+e.children.map(text).join(' ');
let snapshot;
function fresh(handle){return {lab_id:handle,lab_handle:handle,credential_id:'credential',original_title:original,edited_title:null,
 prepared:true,ready:false,tampered:false,restored:false,reason:'Awaiting peers',
 nodes:[1,2,3].map(i=>({node_id:'Node-'+i,status:'ONLINE',height:i===1?1:0,block_count:i===1?2:1,
 tip_hash:tip,stored_tip_hash:tip,pending_count:0,chain_valid:true,local_title:i===1?original:null,
 verification:{status:i===1?'VERIFIED':'NOT_FOUND',reason:'Actual reason <safe>'}}))};}
function confirm(){snapshot.ready=true;snapshot.reason=null;snapshot.nodes.forEach(n=>Object.assign(n,{height:1,block_count:2,local_title:original,chain_valid:true,verification:{status:'VERIFIED'}}));}
const ok=data=>({ok:true,json:async()=>structuredClone(data)});
const context=vm.createContext({document,TextEncoder,Uint8Array,AbortController,Option:class extends Element{constructor(label,value){super();this.textContent=label;this.value=value;}},
 Date:{now:()=>clock},setTimeout(fn,ms){if(ms<=250){clock+=ms;queueMicrotask(fn);}else if(testCase==='read_timeout'){clock+=ms;queueMicrotask(fn);}return 1;},clearTimeout(){},
 location:{hash:'#tamper'},window:{addEventListener:(k,f)=>events[k]=f},navigator:{sendBeacon(){}},localStorage:{getItem:()=>null,setItem(){}},structuredClone,
 fetch:async(url,options={})=>{
  assert.ok(url.startsWith('/api/labs/tamper'));const method=options.method||'GET';calls.push({url,method,body:options.body});
  if(errorCode)return {ok:false,status:errorCode,json:async()=>({detail:'Exact backend error <safe>'})};
  if(method==='DELETE')return ok({cleared:true});
  if(method==='POST'&&url==='/api/labs/tamper'){
   snapshot=fresh('handle-'+(++count));
   if(testCase==='failed_prepare'){snapshot.prepared=false;snapshot.reason='Actual backend mining rejection';}
   if(holdInit){holdInit=false;await new Promise(r=>deferred=r);}return ok(snapshot);
  }
  if(method==='GET'){
   reads++;const data=structuredClone(snapshot);
   if(testCase==='read_timeout'&&count>0&&snapshot.ready)await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{name:'AbortError'}))));
   if(holdRead){holdRead=false;await new Promise(r=>deferred=r);return ok(data);}
   if(!snapshot.tampered&&testCase!=='timeout')confirm();return ok(snapshot);
  }
  if(url.endsWith('/edit')){
   assert.deepEqual(Object.keys(JSON.parse(options.body)),['title']);
   const title=JSON.parse(options.body).title;snapshot.edited_title=title;snapshot.ready=false;snapshot.tampered=true;snapshot.restored=false;
   snapshot.reason='Transaction invalid <safe>';Object.assign(snapshot.nodes[1],{local_title:title,chain_valid:false,verification:{status:'INVALID',reason:snapshot.reason}});
   return ok(snapshot);
  }
  if(url.endsWith('/sync')){confirm();snapshot.tampered=false;snapshot.restored=true;return ok(snapshot);}
  throw Error('Unexpected request '+url);
 }});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),context);
const $=id=>document.getElementById(id),run=s=>vm.runInContext(s,context),tick=()=>new Promise(r=>setImmediate(r));
const mutations=suffix=>calls.filter(c=>c.method==='POST'&&c.url.endsWith(suffix));
(async()=>{
 assert.equal($('lab-tamper').hidden,false);assert.equal($('lab-network').hidden,true);
 assert.equal($('tamper-edit').disabled,true);assert.equal($('tamper-sync').disabled,true);
 await run('tamperLabAction("edit")');await run('tamperLabAction("sync")');assert.equal(calls.length,0);
 if(holdInit){
  const pending=run('tamperLabAction("create")');await tick();
  assert.equal($('tamper-create').disabled,true);await run('tamperLabAction("create")');await run('resetTamperLab()');assert.equal(calls.length,1);
  if(testCase==='page_exit')events.pagehide();deferred();await pending;
  if(testCase==='page_exit'){assert.equal(run('tamperLab.handle'),null);assert.equal(calls.filter(c=>c.method==='DELETE').length,1);return;}
 }else await run('tamperLabAction("create")');
 assert.equal(run('tamperLab.handle'),'handle-1');
 if(testCase==='timeout'){
  assert.ok(reads>1&&reads<=20);assert.equal(run('tamperLab.pollFailed'),true);assert.equal($('tamper-error').hidden,false);
  assert.ok(!$('tamper-summary').className.includes('valid'));assert.equal($('tamper-edit').disabled,true);
  assert.equal($('tamper-refresh').disabled,false);return;
 }
 if(testCase==='failed_prepare'){
  assert.equal(reads,0);assert.equal($('tamper-error').textContent,'Actual backend mining rejection');
  assert.equal($('tamper-edit').disabled,true);assert.equal($('tamper-reset').disabled,false);return;
 }
 assert.equal(run('tamperLab.snapshot.ready'),true);assert.equal($('tamper-original').textContent,original);
 assert.equal($('tamper-edit').disabled,false);assert.equal($('tamper-sync').disabled,true);
 if(testCase==='controls'){
  $('tamper-input').value='   ';$('tamper-input').oninput();assert.equal($('tamper-edit').disabled,true);
  $('tamper-input').value=' '+original+' ';$('tamper-input').oninput();assert.equal($('tamper-edit').disabled,true);
  const before=calls.length;await run('tamperLabAction("edit")');assert.equal(calls.length,before);
  $('tamper-input').value=edited;$('tamper-input').oninput();assert.equal($('tamper-edit').disabled,false);
  context.location.hash='#sha';events.hashchange();context.location.hash='#tamper';events.hashchange();
  assert.equal(run('tamperLab.handle'),'handle-1');assert.equal($('tamper-title').focused,true);
 }else if(testCase==='corruption'){
  $('tamper-input').value=edited;$('tamper-input').oninput();const before=reads;await run('tamperLabAction("edit")');
  assert.equal(reads,before);assert.equal(mutations('/sync').length,0); // no automatic repair or ready-poll after edit
  assert.equal(run('tamperLab.snapshot.tampered'),true);assert.equal($('tamper-local').textContent,edited);
  assert.ok(text($('tamper-nodes')).includes(edited));assert.ok(text($('tamper-nodes')).includes('INVALID'));
  assert.ok($('tamper-summary').className.includes('invalid'));assert.equal($('tamper-edit').disabled,true);
  assert.equal($('tamper-sync').disabled,false);assert.equal($('tamper-reason').textContent,'Transaction invalid <safe>');
  const data=JSON.parse($('tamper-technical').textContent);
  assert.ok(data.nodes.every(n=>n.stored_tip_hash===tip));assert.deepEqual(data.nodes.map(n=>n.chain_valid),[true,false,true]);
  await run('tamperLabAction("refresh")');assert.equal(run('tamperLab.snapshot.nodes[1].verification.status'),'INVALID');
  await run('tamperLabAction("sync")');assert.equal(mutations('/sync').length,1);
  assert.equal(run('tamperLab.snapshot.restored'),true);assert.equal($('tamper-local').textContent,original);
  assert.ok($('tamper-summary').className.includes('valid'));assert.ok(Array.from(run('tamperLab.snapshot.nodes')).every(n=>n.verification.status==='VERIFIED'));
 }else if(testCase==='errors'){
  $('tamper-input').value=edited;errorCode=422;await run('tamperLabAction("edit")');
  assert.equal($('tamper-error').textContent,'Exact backend error <safe>');assert.equal(run('tamperLab.snapshot.ready'),true);
  assert.equal($('tamper-edit').disabled,false);errorCode=404;await run('tamperLabAction("refresh")');
  assert.equal(run('tamperLab.handle'),null);assert.equal($('tamper-create').disabled,false);
  assert.equal($('tamper-edit').disabled,true);assert.equal($('tamper-sync').disabled,true);return;
 }else if(testCase==='stale_reset'){
  run('signature.key={key_handle:"other-lab"};comparison.results.pow={created:true};networkLab.handle="keep-network";hashToken=37;merklePrevious={root:"keep"}');
  holdRead=true;const pending=run('tamperLabAction("refresh")');await tick();
  assert.equal($('tamper-reset').disabled,false);await run('resetTamperLab()');await run('tamperLabAction("create")');
  deferred();await pending;assert.equal(run('tamperLab.handle'),'handle-2');assert.equal(run('tamperLab.snapshot.lab_id'),'handle-2');
  assert.equal(run('signature.key.key_handle'),'other-lab');assert.equal(run('comparison.results.pow.created'),true);
  assert.equal(run('networkLab.handle'),'keep-network');assert.equal(run('hashToken'),37);assert.equal(run('merklePrevious.root'),'keep');
  assert.equal(calls.filter(c=>c.method==='DELETE'&&c.url.endsWith('handle-1')).length,1);return;
 }else if(testCase==='read_timeout'){
  await run('tamperLabAction("refresh")');assert.equal($('tamper-error').hidden,false);assert.equal(run('tamperLab.busy'),false);return;
 }
 await run('resetTamperLab()');assert.equal(run('tamperLab.handle'),null);assert.equal($('tamper-nodes').children.length,0);
 assert.equal($('tamper-create').disabled,false);assert.equal($('tamper-sync').disabled,true);
 await run('tamperLabAction("create")');events.pagehide();await tick();
 assert.ok(calls.some(c=>c.method==='DELETE'&&c.url.endsWith('handle-2')));assert.equal(run('tamperLab.handle'),null);
})();
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
