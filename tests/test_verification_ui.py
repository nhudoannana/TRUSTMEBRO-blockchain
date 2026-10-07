"""Run actual step-6 handlers: copies, pending revocation and stale responses."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['original', 'mismatch', 'revoke', 'mine', 'failure', 'local_reset', 'remote_reset', 'new_credential', 'different_id', 'mined_label', 'duplicate_label', 'wallet_reset', 'id_only', 'outcome_mapping', 'dirty_edit', 'dirty_restore', 'dirty_inflight', 'dirty_recheck', 'presentation_acceptance'])
def test_verification_ui(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=[...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),document={querySelectorAll:()=>[],getElementById(id){
 if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',hidden:true,disabled:false,style:{},focus(){}});
 return elements.get(id);
}};
const mode=process.argv[1],metadata={holder_name:'Holder',title:'Title',issue_date:'2026-10-01',issuer_name:'Issuer'};
const record={credential_id:'cred',credential:metadata,transaction:{tx_id:'issue',signature:'untouched'}};
let calls=0,context;
context=vm.createContext({document,console,record,fetch:async(url,options={})=>{
 if(!options.method)return {ok:true,json:async()=>({reset_count:0,nodes:[{node_id:'Node-1',status:'ONLINE',height:1,pending_count:1}]})};
 calls++;
 const body=JSON.parse(options.body);
 assert.equal(document.getElementById('v-original').disabled,true);
 await vm.runInContext('verificationOperation("verify")',context); // duplicate click ignored
 if(mode==='local_reset')vm.runInContext('state=freshState()',context);
 let data;
 if(mode==='revoke'){
  assert.equal(url,'/api/credentials/cred/revoke');
  assert.deepEqual(body,{node_id:'Node-1',reason:'Expired'});
  data={accepted:true,pending:true,tx_id:'revoke',reason:'backend accepted',reset_count:0};
 }else if(mode==='mine'){
  assert.equal(url,'/api/mining/pow');assert.deepEqual(body,{node_id:'Node-1'});
  data={mined:true,block:{height:2,hash:'real-block'},transaction_ids:['revoke'],reset_count:0};
 }else{
  assert.equal(url,'/api/verify');
  if(mode==='id_only')assert.equal(body.presented_credential,undefined);
  else assert.equal(body.presented_credential.title,mode==='mismatch'?'Edited':'Title');
  data={chain_status:{status:'VERIFIED',reason:'ACTIVE',checks:[['signature',true,'valid']],info:{...metadata,issuer_public_key:'on-chain-issuer-key'}},
   node_id:'Node-1',node_status:'ONLINE',presentation_match:mode==='id_only'?null:mode!=='mismatch',mismatched_fields:mode==='mismatch'?['title']:[],success:mode!=='mismatch',reset_count:mode==='remote_reset'?1:0};
  if(mode==='dirty_inflight'){
   document.getElementById('v-title').value='Edited during request';
   document.getElementById('v-title').oninput();
  }
 }
 return {ok:mode!=='failure',status:500,json:async()=>mode==='failure'?{detail:{message:'actual failure'}}:data};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('state.record=record;state.step=5;state.mempool={generation:0};render=async()=>{}',context);
(async()=>{
 await vm.runInContext('renderStep5()',context);
 if(mode==='presentation_acceptance'){
  for(const status of ['VERIFIED','REVOKED','NOT_FOUND','INVALID']){
   for(const match of [true,false,null])for(const success of [true,false,undefined]){
    context.result={chain_status:{status,reason:'Actual status',checks:[],info:metadata},node_id:'Node-1',node_status:'ONLINE',presentation_match:match,success,mismatched_fields:[]};
    vm.runInContext('state.verification.result=result;showVerification(state.verification)',context);
    const html=document.getElementById('v-result').innerHTML;
    const presentation=html.split('<h4>Bản xuất trình hiện tại</h4>')[1]?.split('<details')[0];
    assert.ok(presentation,'Presentation result must be separate from the chain result');
    assert.equal(/Được chấp nhận: <strong>Có<\/strong>/.test(presentation),status==='VERIFIED'&&match===true&&success===true);
    assert.doesNotMatch(presentation,/true|false|Presentation match/);
   }
  }
  vm.runInContext('state.verification.comparisonDirty=true;showVerification(state.verification)',context);
  assert.doesNotMatch(document.getElementById('v-result').innerHTML.split('<details')[0],/Được chấp nhận: <strong>Có<\/strong>/);
  assert.equal(calls,0);return;
 }
 if(mode==='outcome_mapping'){
  for(const status of ['VERIFIED','REVOKED','NOT_FOUND','INVALID']){
   for(const match of [true,false,null]){
    context.result={chain_status:{status,reason:'Actual reason <unsafe>',checks:[['actual check',false,'Exact failure <unsafe>']],info:metadata},node_id:'Node-3',node_status:'OFFLINE',presentation_match:match,mismatched_fields:match===false?['title']:[],local_chain_warning:'Actual stale warning'};
    vm.runInContext('state.verification.result=result;showVerification(state.verification)',context);
    const html=document.getElementById('v-result').innerHTML;
    assert.match(html,/Actual reason &lt;unsafe&gt;/);assert.match(html,/Exact failure &lt;unsafe&gt;/);
    assert.match(html,/Node-3 OFFLINE/);assert.match(html,/<details class="technical">/);
    const headline=html.match(/<h3>(.*?)<\/h3>/)[1];
    if(status==='VERIFIED'){
      if(match===true)assert.match(headline,/xuất trình khớp/);
      if(match===false)assert.match(headline,/không khớp/);
      if(match===null){assert.doesNotMatch(headline,/xuất trình khớp/);assert.match(html,/Chưa so sánh/);}
    }else assert.doesNotMatch(headline,/xuất trình khớp|đã xác minh/);
   }
  }
  assert.equal(calls,0);return;
 }
 document.getElementById('v-id').value='cred';document.getElementById('v-node').value='Node-1';document.getElementById('v-reason').value='Expired';
 if(mode==='mismatch'){document.getElementById('v-title').value='Edited';document.getElementById('v-title').oninput();}
 if(mode==='mine')vm.runInContext('state.verification.revocation={accepted:true,pending:true,tx_id:"revoke",reason:"accepted"}',context);
 if(mode==='id_only')vm.runInContext('state.verification.originalId=null;state.selectedWalletName="Wrong current wallet"',context);
 const action=['revoke','mine'].includes(mode)?mode:'verify';
 await vm.runInContext('verificationOperation("'+action+'",'+(mode==='mismatch')+')',context);
 assert.equal(calls,1);
 assert.equal(record.transaction.signature,'untouched');assert.equal(record.credential.title,'Title');
 if(['local_reset','remote_reset'].includes(mode)){
  assert.equal(vm.runInContext('state.record',context),null);
  assert.equal(vm.runInContext('state.verification',context),undefined);
 }else if(mode==='failure')assert.match(document.getElementById('v-error').textContent,/actual failure/);
 else if(mode==='revoke'){assert.match(document.getElementById('v-revocation').textContent,/revoke/);assert.equal(vm.runInContext('state.verification.revocation.pending',context),true);}
 else if(mode==='mine'){assert.equal(vm.runInContext('state.verification.revocation.pending',context),false);assert.match(document.getElementById('v-status').textContent,/real-block/);}
 else if(mode==='mismatch'){assert.equal(vm.runInContext('state.verification.result.chain_status.status',context),'VERIFIED');assert.equal(vm.runInContext('state.verification.result.success',context),false);document.getElementById('v-restore').onclick();assert.equal(document.getElementById('v-title').value,'Title');}
 else assert.equal(vm.runInContext('state.verification.result.success',context),true);
 if(mode.startsWith('dirty_')){
  const previous=vm.runInContext('state.verification.result',context),original=JSON.stringify(previous);
  if(mode!=='dirty_inflight'){
   document.getElementById('v-title').value='A newer copy';document.getElementById('v-title').oninput();
   if(['dirty_restore','dirty_recheck'].includes(mode))document.getElementById('v-restore').onclick();
  }
  const html=document.getElementById('v-result').innerHTML;
  assert.doesNotMatch(html,/xuất trình khớp|Hồ sơ xuất trình được chấp nhận: true/);
  assert.match(document.getElementById('v-status').textContent,/Bản xuất trình đã đổi/);
  assert.match(html,/kết quả trước|quan sát trước/i);
  assert.equal(JSON.stringify(previous),original);assert.equal(previous.presentation_match,true);
  assert.equal(calls,1);assert.equal(document.getElementById('v-original').disabled,false);
  if(mode==='dirty_recheck'){
   await vm.runInContext('verificationOperation("verify",true)',context);
   assert.equal(calls,2);assert.match(document.getElementById('v-result').innerHTML,/xuất trình khớp/);
   assert.equal(vm.runInContext('state.verification.comparisonDirty',context),false);
  }
 }
 if(mode==='id_only'){
  assert.equal(vm.runInContext('state.verification.result.presentation_match',context),null);
  assert.match(document.getElementById('v-result').innerHTML,/VERIFIED/);
  assert.match(document.getElementById('v-result').innerHTML,/on-chain-issuer-key/);
  assert.equal(document.getElementById('card-title').textContent,'Issuer');
  assert.doesNotMatch(document.getElementById('v-result').innerHTML,/Wrong current wallet/);
 }
 if(mode==='new_credential'){
  vm.runInContext('state.verification.revocation={pending:true};clearLaterState()',context);
  assert.equal(vm.runInContext('state.verification',context),null);
  assert.equal(vm.runInContext('state.mempool',context),null);
  assert.equal(vm.runInContext('state.mining',context),null);
 }
 if(mode==='different_id'){
  vm.runInContext('state.verification.revocation={pending:true,credential_id:"cred"}',context);
  document.getElementById('v-id').value='different';
  document.getElementById('v-id').oninput();
  assert.equal(vm.runInContext('state.verification.result',context),null);
  assert.equal(vm.runInContext('state.verification.revocation',context),null);
  assert.equal(document.getElementById('v-title').value,'');
 }
 if(mode==='mined_label'){
  vm.runInContext('state.block={hash:"mined"};showSignedCredential()',context);
  assert.doesNotMatch(document.getElementById('c-result').innerHTML,/chưa gửi vào mempool/);
 }
 if(mode==='duplicate_label'){
  vm.runInContext('state.mempool={credentialId:"cred",submission:{accepted:false},nodes:[{transactions:[{tx_id:"issue"}]}]};showSignedCredential()',context);
  assert.doesNotMatch(document.getElementById('c-result').innerHTML,/chưa gửi vào mempool/);
 }
 if(mode==='wallet_reset'){
  vm.runInContext('state.step=0;loadWalletList=async()=>{};apiCreateWallet=async()=>{state=freshState();return {id:"reset-away-wallet",name:"Issuer",public_key_hex:"public"}}',context);
  await vm.runInContext('handleCreateWallet()',context);
  assert.equal(vm.runInContext('state.selectedWalletId',context),null);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, case], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
