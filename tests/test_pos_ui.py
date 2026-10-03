"""Node VM checks of real PoS handlers; these are not browser verification."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('outcome', ['forged', 'rejected', 'remote_reset', 'local_reset', 'prediction_reset'])
def test_pos_ui_selection_signer_and_stale_guards(outcome):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=[...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map();
const document={querySelectorAll:()=>[],getElementById(id){if(!elements.has(id))elements.set(id,{value:'',hidden:true,disabled:false,textContent:'',innerHTML:''});return elements.get(id);}};
const outcome=process.argv[1],record={credential_id:'cred',credential:{issuer_name:'Actual'},issuer_address:'issuer-full-address',transaction:{tx_id:'issuer-signed',sender_public_key:'issuer-full-public-key'}};
const actual={name:'Actual',address:'actual-full-address',public_key_hex:'actual-full-public-key',institution_type:'Test',stake:500,is_active:true,eligible:true,selection_weight:0.5};
let posts=0,returned=false,context;
context=vm.createContext({document,console,record,fetch:async(url,options={})=>{
 if(options.method==='POST'){
  posts++;assert.equal(url,'/api/mining/pos');assert.deepEqual(JSON.parse(options.body),{node_id:'Node-1'});
  assert.equal(document.getElementById('p-mode').disabled,true);
  assert.doesNotMatch(document.getElementById('p-status').textContent,/nonce/);
  await vm.runInContext('handlePowMining({preventDefault(){}})',context);
  if(outcome==='local_reset')vm.runInContext('state=freshState()',context);
  returned=true;
  return {ok:true,json:async()=>({node_id:'Node-1',forged:outcome!=='rejected',reason:'backend rejection',signer:actual,
   block:{height:1,hash:'pos-hash',previous_hash:'parent',merkle_root:'root',transaction_count:1,validator_address:actual.address},
   transaction_ids:['issuer-signed'],seconds:0.002,reset_count:outcome==='remote_reset'?1:0})};
 }
 if(url==='/api/mempool')return {ok:true,json:async()=>({reset_count:0,nodes:[{node_id:'Node-1',status:'ONLINE',pending_count:returned?0:1,transactions:[]}]})};
 if(url.startsWith('/api/consensus/pos'))return {ok:true,json:async()=>({node_id:'Node-1',status:'ONLINE',validators:[actual],stake_mode:'HYBRID',seed:42,target_height:2,previous_hash:'pos-hash',
  predicted_validator:{...actual,name:'Next provisional',address:'different-address'},reset_count:outcome==='prediction_reset'?1:0})};
 assert.equal(url,'/api/network');return {ok:true,json:async()=>({reset_count:0,nodes:[{node_id:'Node-1',status:'ONLINE',height:1,pending_count:0,chain_valid:true}]})};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('state.record=record;state.step=3;render=async()=>{};',context);
(async()=>{
 await vm.runInContext('renderStep3()',context);
 assert.equal(document.getElementById('p-mode').value,'pow');
 document.getElementById('p-node').value='Node-1';document.getElementById('p-mode').value='pos';
 await document.getElementById('p-mode').onchange();
 if(outcome==='prediction_reset'){
  assert.equal(vm.runInContext('state.record',context),null);assert.equal(posts,0);return;
 }
 assert.match(document.getElementById('p-pos').innerHTML,/block #2/);
 assert.match(document.getElementById('p-pos').innerHTML,/không đảm bảo tần suất/);
 await vm.runInContext('handlePowMining({preventDefault(){}})',context);
 assert.equal(posts,1);
 if(outcome.includes('reset')){
  assert.equal(vm.runInContext('state.record',context),null);assert.equal(vm.runInContext('state.block',context),null);
 }else if(outcome==='rejected'){
  assert.match(document.getElementById('p-status').textContent,/backend rejection/);
  assert.equal(vm.runInContext('state.block',context),null);
 }else{
  const html=document.getElementById('p-result').innerHTML;
  assert.match(html,/Actual/);assert.match(html,/actual-full-public-key/);assert.match(html,/actual-full-address/);
  assert.doesNotMatch(html,/Next provisional|lần hash/);
  assert.equal(vm.runInContext('state.block.hash',context),'pos-hash');
  assert.equal(document.getElementById('p-submit').disabled,true); // real empty mempool after forging
  assert.equal(document.getElementById('p-next').disabled,false);
  assert.match(document.getElementById('p-pos').innerHTML,/block tiếp theo #2/);
  const summary=html.slice(0,html.indexOf('<details'));
  assert.match(summary,/Actual/);assert.doesNotMatch(summary,/Next provisional|actual-full-public-key|Test/);
  assert.match(document.getElementById('card-identity').innerHTML,/issuer-full-public-key/);
  assert.doesNotMatch(document.getElementById('card-identity').innerHTML,/actual-full-public-key/);
  assert.doesNotMatch(document.getElementById('rail-note').innerHTML,/nonce|difficulty/);
  document.getElementById('p-mode').value='pow';await document.getElementById('p-mode').onchange();
  assert.equal(document.getElementById('p-pos').hidden,true);assert.equal(document.getElementById('p-submit').textContent,'Tạo block PoW');
  assert.match(document.getElementById('rail-note').innerHTML,/nonce/);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, outcome],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
