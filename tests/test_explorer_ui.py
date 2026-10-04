"""Behavioral Node-VM explorer checks; not real browser verification."""
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('case', ['loading','genesis','pow','pos','offline','errors',
                                  'reset','stale_list','stale_detail','pagehide','timeout',
                                  'deep_link','missing_link','invalid_link','stale_entry'])
def test_explorer_handlers(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const testCase=process.argv[1],elements=new Map(),events={},calls=[],timers=new Map();
class Element {
 constructor(tag='div'){this.tag=tag;this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);}
 setAttribute(k,v){this[k]=v;}
 set innerHTML(v){throw Error('Unsafe HTML');}
}
const document={documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement:tag=>new Element(tag)};
document.getElementById('explorer-node').value='Node-1';
const text=e=>e.textContent+' '+e.children.map(text).join(' '),tip='a'.repeat(64),genesis='0'.repeat(64);
function block(height,consensus='PoW'){return {height,hash:height?tip:genesis,previous_hash:genesis,merkle_root:'m'.repeat(64),timestamp:'2026-10-04T00:00:00Z',consensus_type:consensus,transaction_count:height?1:0,difficulty:consensus==='PoS'?0:3,nonce:consensus==='PoS'?0:42};}
let consensus=testCase==='pos'?'PoS':'PoW',onlyGenesis=['genesis','loading','offline','stale_list','pagehide','missing_link'].includes(testCase),generation=0,errorCode=0,held=null,holding=['loading','stale_list','pagehide','stale_entry'].includes(testCase),holdDetail=false;
const signed={tx_type:'ISSUE',tx_id:'t'.repeat(64),sender_public_key:'issuer-public-key-full-value',payload:{issuer_name:'Same name',title:'<img src=x onerror=alert(1)>'},signature:'real-signature-from-fixture'};
function list(node){return {node_id:node,status:node==='Node-3'?'OFFLINE':'ONLINE',tip_height:onlyGenesis?0:1,tip_hash:onlyGenesis?genesis:tip,reset_count:generation,local_chain_warning:node==='Node-3'?'Offline local copy <safe>':null,blocks:onlyGenesis?[block(0)]:[block(0),block(1,consensus)]};}
function detail(node,height){const data=list(node),b=block(height,consensus);return {...data,block:b,header:{...b,validator_address:consensus==='PoS'?'validator-address':''},transactions:height?[signed]:[],validator:height&&consensus==='PoS'?{name:'Same name',public_key_hex:'validator-public-key-full-value',address:'validator-address'}:null};}
const ok=data=>({ok:true,json:async()=>structuredClone(data)});
const search=['deep_link','missing_link','stale_entry'].includes(testCase)?'?node_id=Node-2&height=1':testCase==='invalid_link'?'?node_id=unknown&height=-1':'';
const context=vm.createContext({document,AbortController,URLSearchParams,window:{location:{search},addEventListener:(k,f)=>events[k]=f},localStorage:{getItem:()=> 'light',setItem(){}},
 setTimeout(fn,ms){const id=timers.size+1;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);},
 fetch:async(url,options={})=>{
  assert.ok(url.startsWith('/api/explorer/blocks'));assert.ok(!options.method||options.method==='GET');calls.push(url);
  const parsed=new URL(url,'http://localhost'),node=parsed.searchParams.get('node_id'),height=parsed.pathname.split('/')[4];
  const data=height===undefined?list(node):detail(node,Number(height));
  if(holding||(holdDetail&&height!==undefined)){holding=false;holdDetail=false;await new Promise(r=>held=r);}
  if(errorCode)return {ok:false,status:errorCode,json:async()=>({detail:{code:'fixture',message:'Exact backend reason <safe>'}})};
  if(testCase==='timeout'&&height!==undefined)await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(Error('aborted'),{name:'AbortError'}))));
  return ok(data);
 }});
vm.runInContext(fs.readFileSync('ui/explorer.js','utf8'),context);
const $=id=>document.getElementById(id),run=s=>vm.runInContext(s,context),tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await tick();assert.equal(document.documentElement.dataset.theme,'light');
 if(testCase==='deep_link'){
  assert.equal(calls.length,2);assert.equal($('explorer-node').value,'Node-2');
  assert.equal(calls[1],'/api/explorer/blocks/1?node_id=Node-2');
  assert.ok(text($('explorer-detail')).includes('Block #1'));
  events.pagehide();events.pageshow({persisted:true});await tick();
  assert.equal(calls.length,4);assert.ok(text($('explorer-detail')).includes('Block #1'));
  events.pagehide();onlyGenesis=true;generation++;events.pageshow({persisted:true});await tick();
  assert.equal(calls.length,5);assert.equal($('explorer-detail').children.length,0);
  assert.match($('explorer-error').textContent,/Block #1.*reset/);return;
 }
 assert.equal(calls.length,1);
 if(testCase==='missing_link'){
  assert.equal($('explorer-node').value,'Node-2');assert.equal($('explorer-detail').children.length,0);
  assert.equal($('explorer-error').hidden,false);assert.match($('explorer-error').textContent,/Block #1.*reset/);
  assert.equal($('explorer-genesis').hidden,false);return;
 }
 if(testCase==='invalid_link'){
  assert.equal($('explorer-node').value,'Node-1');assert.equal($('explorer-error').hidden,false);
  assert.equal($('explorer-detail').children.length,0);return;
 }
 if(testCase==='stale_entry'){
  $('explorer-node').value='Node-3';await $('explorer-node').onchange();held();await tick();
  assert.equal(run('explorerSnapshot.node_id'),'Node-3');assert.equal(calls.length,2);
  assert.equal($('explorer-detail').children.length,0);return;
 }
 if(['loading','stale_list','pagehide'].includes(testCase)){
  assert.equal($('explorer-refresh').disabled,true);assert.equal($('explorer-node').disabled,false);assert.equal($('explorer-detail').children.length,0);
  if(testCase==='stale_list'){
   $('explorer-node').value='Node-3';await $('explorer-node').onchange();held();await tick();
   assert.equal(run('explorerSnapshot.node_id'),'Node-3');assert.equal($('explorer-warning').textContent,'Offline local copy <safe>');return;
  }
  if(testCase==='pagehide'){events.pagehide();held();await tick();assert.equal(run('explorerSnapshot'),null);assert.equal($('explorer-blocks').children.length,0);return;}
  held();await tick();assert.equal($('explorer-refresh').disabled,false);
 }
 assert.equal($('explorer-detail').children.length,0); // list never automatically selects or polls
 if(testCase==='offline'){
  $('explorer-node').value='Node-3';await $('explorer-node').onchange();assert.equal($('explorer-warning').hidden,false);
  assert.ok(text($('explorer-summary')).includes('OFFLINE'));await run('loadExplorerBlock(0)');return;
 }
 if(testCase==='genesis'||testCase==='loading'){
  assert.equal($('explorer-genesis').hidden,false);assert.equal($('explorer-blocks').children.length,0);
  assert.equal($('explorer-workspace').hidden,true);
  await $('explorer-genesis-blocks').children[0].onclick();assert.equal($('explorer-workspace').hidden,false);
  assert.ok(text($('explorer-detail')).includes('Genesis'));assert.ok(text($('explorer-detail')).includes('Block không có giao dịch.'));
  assert.equal(calls.length,2);return;
 }
 assert.equal($('explorer-blocks').children[0].dataset.height,'1');
 if(testCase==='stale_detail'){
  holdDetail=true;const pending=run('loadExplorerBlock(1)');await tick();
  $('explorer-node').value='Node-3';await $('explorer-node').onchange();held();await pending;
  assert.equal(run('explorerSnapshot.node_id'),'Node-3');assert.equal($('explorer-detail').children.length,0);return;
 }
 if(testCase==='timeout'){
  const pending=run('loadExplorerBlock(1)');await tick();assert.equal($('explorer-refresh').disabled,true);
  [...timers.values()].forEach(fn=>fn());await pending;assert.equal($('explorer-error').hidden,false);
  assert.equal($('explorer-detail').children.length,0);assert.equal($('explorer-refresh').disabled,false);return;
 }
 await run('loadExplorerBlock(1)');const rendered=text($('explorer-detail'));
 assert.ok(rendered.includes('ISSUE'));assert.ok(rendered.includes(signed.payload.title));assert.ok(rendered.includes(signed.sender_public_key));
 assert.ok(rendered.includes(tip));assert.equal($('explorer-prompt').hidden,true);
 if(testCase==='pow')assert.ok(rendered.includes('Nonce: 42')&&rendered.includes('Độ khó: 3'));
 if(testCase==='pos'){
  assert.ok(rendered.includes('Validator tạo block'));assert.ok(rendered.includes('validator-public-key-full-value'));
  assert.ok(rendered.includes('Ví phát hành'));assert.ok(!rendered.includes('Nonce:'));
 }
 if(testCase==='errors'){
  errorCode=500;await run('loadExplorerBlock(0)');assert.equal($('explorer-error').textContent,'Exact backend reason <safe>');
  assert.equal($('explorer-detail').children.length,0);assert.equal($('explorer-refresh').disabled,false);
  errorCode=404;await run('loadExplorerBlock(1)');assert.equal(run('explorerSnapshot'),null);assert.equal($('explorer-blocks').children.length,0);return;
 }
 if(testCase==='reset'){
  generation++;await run('loadExplorerBlock(1)');assert.equal(run('explorerSnapshot'),null);assert.equal($('explorer-detail').children.length,0);
  onlyGenesis=true;await $('explorer-refresh').onclick();assert.equal(run('explorerSnapshot.reset_count'),1);assert.equal($('explorer-genesis').hidden,false);return;
 }
 signed.tx_type='REVOKE';signed.payload={credential_id:'credential',reason:'revoke <safe>'};await run('loadExplorerBlock(1)');
 assert.ok(text($('explorer-detail')).includes('REVOKE')&&text($('explorer-detail')).includes('revoke <safe>'));
 const pending=$('explorer-refresh').onclick();assert.equal($('explorer-detail').children.length,0);await pending;
 events.pagehide();assert.equal($('explorer-detail').children.length,0);
})();
"""
    result = subprocess.run(['node','-e',script,case], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
