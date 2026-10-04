"""Behavior of guided navigation and explicit node recovery under Node VM."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['navigation', 'signing_pending', 'sidebar', 'offline', 'mining_offline', 'remote_reset', 'local_reset', 'failure', 'hint_states'])
def test_guided_journey(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=[...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),document={querySelectorAll:()=>[],getElementById(id){
 if(!elements.has(id))elements.set(id,{value:'',checked:false,disabled:false,hidden:true,innerHTML:'',textContent:'',focus(){},scrollIntoView(){}});
 return elements.get(id);
}};
const testCase=process.argv[1],record={credential_id:'credential',credential:{issuer_name:'Same name'},issuer_address:'issuer-address',transaction:{tx_id:'signed-tx',sender_public_key:'issuer-key'}};
const prefix=testCase==='mining_offline'?'p':'m';
let posts=0, reads=0,context;
const rows=online=>[{node_id:'Node-1',status:online?'ONLINE':'OFFLINE',pending_count:1,transactions:[record.transaction]}];
context=vm.createContext({document,console,record,fetch:async(url,options={})=>{
 if(url==='/api/credentials'){
  assert.equal(document.getElementById('c-next').disabled,true);
  return {ok:false,status:422,json:async()=>({detail:[{msg:'fixture validation failure'}]})};
 }
 if(options.method==='POST'){
  posts++; assert.equal(url,'/api/network/nodes/Node-1/status');assert.deepEqual(JSON.parse(options.body),{online:true});
  assert.equal(document.getElementById(prefix+'-submit').disabled,true);
  await vm.runInContext('enableJourneyNode("'+prefix+'")',context);
  if(testCase==='local_reset')vm.runInContext('state=freshState()',context);
  return {ok:testCase!=='failure',status:500,json:async()=>testCase==='failure'?{detail:{message:'actual failure'}}:{network:{reset_count:testCase==='remote_reset'?1:0,nodes:rows(true)}}};
 }
 reads++;assert.equal(url,'/api/mempool');return {ok:true,json:async()=>({reset_count:0,nodes:rows(posts>0)})};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('render=async()=>{}',context);
(async()=>{
 if(testCase==='hint_states'){
  const run=s=>vm.runInContext(s,context),hint=()=>run('journeyGuidance()');
  const empty=hint();run('state.selectedWalletId="wallet"');assert.notEqual(hint().next,empty.next);
  run('state.step=1;state.signing=true');const pending=hint();assert.equal(run('canContinue(1)'),false);
  run('state.signing=false;state.record=record');assert.notEqual(hint().observed,pending.observed);assert.equal(run('canContinue(1)'),true);
  run('state.step=2;state.mempool={credentialId:record.credential_id,nodes:[],submission:{accepted:false,reason:"Actual rejection <safe>"}}');
  assert.ok(hint().observed.includes('Actual rejection <safe>'));assert.equal(run('canContinue(2)'),false);
  const rejected=hint();run('state.mempool.submission.accepted=true');assert.equal(run('canContinue(2)'),true);assert.notEqual(hint().observed,rejected.observed);
  run('state.step=3;state.mining={pending:true}');const waiting=hint();assert.equal(run('canContinue(3)'),false);
  run('state.mining={pending:false,result:{mined:false,reason:"Bounded search incomplete"}}');assert.ok(hint().observed.includes('Bounded search incomplete'));
  run('state.block={height:1};state.mining.result={mined:true,transaction_ids:[record.transaction.tx_id]}');assert.notEqual(hint().observed,waiting.observed);
  run('state.step=4;state.network={snapshot:{online_nodes_synchronized:true}}');assert.equal(run('canContinue(4)'),true);const online=hint();
  run('state.network.snapshot.all_nodes_synchronized=true');assert.notEqual(hint().observed,online.observed);
  run('state.network.error="Actual timeout"');assert.equal(run('canContinue(4)'),false);assert.equal(hint().observed,'Actual timeout');
  run('state.step=5;state.verification={result:{chain_status:{status:"VERIFIED"},presentation_match:null}}');const idOnly=hint().observed;
  run('state.verification.result.presentation_match=true');const match=hint().observed;assert.notEqual(match,idOnly);
  run('state.verification.result.presentation_match=false');assert.notEqual(hint().observed,match);
  for(const status of ['NOT_FOUND','REVOKED','INVALID']){
   context.status=status;run('state.verification.result.chain_status={status,reason:"Actual chain reason"}');assert.ok(hint().observed.includes(status));
  }
  run('state.verification.revocation={pending:true}');const revoking=hint().next;
  run('state.verification.busy=true');assert.notEqual(hint().next,revoking);
  document.getElementById('v-error').hidden=false;document.getElementById('v-error').textContent='<img src=x> API failure';
  run('showJourneyGuidance()');assert.ok(document.getElementById('journey-observed').textContent.includes('<img src=x> API failure'));
  assert.equal(document.getElementById('journey-observed').innerHTML,'');assert.equal(posts,0);assert.equal(reads,0);
 }else if(testCase==='navigation'){
  vm.runInContext('state.step=1;showContinuation(1,"c-next")',context);
  document.getElementById('c-next').onclick();
  assert.equal(vm.runInContext('state.step',context),1);
  assert.equal(vm.runInContext('canContinue(1)',context),false);
  vm.runInContext('state.record=record',context);
  assert.equal(vm.runInContext('canContinue(1)',context),true);
  vm.runInContext('showContinuation(1,"c-next")',context);
  assert.equal(document.getElementById('c-next').disabled,false);
  assert.equal(vm.runInContext('state.step',context),1); // result does not auto-advance
  document.getElementById('c-next').onclick();
  assert.equal(vm.runInContext('state.step',context),2);
  assert.equal(vm.runInContext('canContinue(2)',context),false);
  vm.runInContext('state.mempool={credentialId:record.credential_id,nodes:[],submission:{accepted:false}}',context);
  assert.equal(vm.runInContext('canContinue(2)',context),false);
  vm.runInContext('state.mempool.nodes=[{transactions:[record.transaction]}]',context);
  assert.equal(vm.runInContext('canContinue(2)',context),true);
  assert.equal(vm.runInContext('canContinue(3)',context),false);
  vm.runInContext('state.block={height:1};state.mining={result:{transaction_ids:["other"]}};state.network={snapshot:{online_nodes_synchronized:true}}',context);
  assert.equal(vm.runInContext('canContinue(3)',context),true);
  assert.equal(vm.runInContext('canContinue(4)',context),false);
  vm.runInContext('state.mining.result.transaction_ids=[record.transaction.tx_id]',context);
  assert.equal(vm.runInContext('canContinue(4)',context),true);
  vm.runInContext('state.network.error="timeout"',context);
  assert.equal(vm.runInContext('canContinue(4)',context),false);
  vm.runInContext('state=freshState();goToStep(4)',context);
  assert.equal(vm.runInContext('state.step',context),4);assert.equal(vm.runInContext('state.block',context),null);
 }else if(testCase==='signing_pending'){
  vm.runInContext('state.step=1;state.record=record;state.selectedWalletId="issuer";renderStep1()',context);
  assert.equal(document.getElementById('c-next').disabled,false);
  await vm.runInContext('handleCredentialCreate({preventDefault(){}})',context);
  assert.match(document.getElementById('c-error').textContent,/fixture validation failure/);
  assert.equal(document.getElementById('c-next').disabled,false); // previous signed record remains valid
 }else if(testCase==='sidebar'){
  vm.runInContext('state.step=3;state.record=record;miningState().mode="pow";renderRail()',context);
  assert.match(document.getElementById('rail-note').innerHTML,/nonce/);
  vm.runInContext('miningState().mode="pos";renderRail()',context);
  assert.doesNotMatch(document.getElementById('rail-note').innerHTML,/nonce|difficulty|độ khó/);
  assert.match(document.getElementById('rail-note').innerHTML,/stake/);
 }else{
  vm.runInContext('state.record=record;state.step='+(prefix==='m'?2:3),context);
  await vm.runInContext(prefix==='m'?'renderStep2()':'renderStep3()',context);
  document.getElementById(prefix+'-node').value='Node-1';
  vm.runInContext(prefix==='m'?'showMempool(mempoolState())':'showMining(miningState(),mempoolState())',context);
  assert.equal(document.getElementById(prefix+'-submit').disabled,true);
  assert.equal(document.getElementById(prefix+'-enable').hidden,false);
  await vm.runInContext((prefix==='m'?'handleMempoolSubmit':'handlePowMining')+'({preventDefault(){}})',context);
  assert.equal(posts,0);
  await vm.runInContext('enableJourneyNode("'+prefix+'")',context);
  assert.equal(posts,1);
  if(testCase.endsWith('reset'))assert.equal(vm.runInContext('state.record',context),null);
  else if(testCase==='failure')assert.match(document.getElementById('m-error').textContent,/actual failure/);
  else{
   assert.equal(document.getElementById(prefix+'-submit').disabled,false);
   assert.equal(document.getElementById(prefix+'-enable').hidden,true);
   assert.equal(document.getElementById(prefix+'-node').value,'Node-1');
   assert.equal(vm.runInContext('state.mempool.submission',context),null);
   assert.equal(vm.runInContext('state.block',context),null);
   assert.equal(reads,3);
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
