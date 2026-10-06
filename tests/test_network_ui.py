"""Step F frontend state guards, using the actual inline handlers."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['early_access', 'divergent', 'different_full_tip', 'offline', 'agreement', 'failure', 'timeout', 'local_reset', 'remote_reset'])
def test_network_ui(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=[...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map();
const document={querySelectorAll:()=>[],getElementById(id){
 if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',disabled:false,hidden:true,focus(){}});
 return elements.get(id);
}};
const mode=process.argv[1];
const snapshot={reset_count:0,nodes:[1,2,3].map(i=>({node_id:'Node-'+i,status:'ONLINE',height:0,block_count:1,tip_hash:'genesis',pending_count:0,chain_valid:true,validity_reason:'valid'})),
 online_nodes_valid:true,online_nodes_agree:false,online_nodes_synchronized:false,all_nodes_synchronized:false,events:['actual backend event']};
if(mode==='different_full_tip'){
 snapshot.nodes.forEach(n=>n.tip_hash='a'.repeat(60)+(n.node_id==='Node-3'?'2222':'1111'));
}
if(mode==='offline')snapshot.nodes[2]={...snapshot.nodes[2],status:'OFFLINE',height:0,tip_hash:'older-tip',pending_count:7};
if(mode==='agreement'){snapshot.all_nodes_synchronized=true;snapshot.online_nodes_agree=true;}
let reads=0,context;
context=vm.createContext({document,console,setTimeout:fn=>fn(),fetch:async(url,options={})=>{
 if(options.method==='POST')return {ok:true,json:async()=>({completed:false,reason:'backend rejection verbatim',network:snapshot})};
 reads++;
 if(mode==='local_reset')vm.runInContext('state=freshState()',context);
 return {ok:true,json:async()=>({...snapshot,reset_count:mode==='remote_reset'?1:0})};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('render=async()=>{};state.step=4;',context);
(async()=>{
 if(mode==='early_access'){
  vm.runInContext('state.step=0;goToStep(4);renderJourneyNav()',context);
  assert.equal(vm.runInContext('state.step',context),4);
  assert.equal(vm.runInContext('state.max',context),0);
  assert.equal(vm.runInContext('state.record',context),null);
  assert.equal(vm.runInContext('state.block',context),null);
  assert.doesNotMatch(document.getElementById('journey').innerHTML,/class="done"/);
 }else{
  vm.runInContext('networkState()',context);
  if(mode==='remote_reset')vm.runInContext('state.record={credential_id:"old"};state.network.snapshot={reset_count:0}',context);
  if(mode==='failure')await vm.runInContext('networkOperation("/api/network/sync",null)',context);
  else await vm.runInContext('loadNetwork(state,networkState(),'+(mode==='timeout')+')',context);
  if(mode.endsWith('reset')){
   assert.equal(vm.runInContext('state.record',context),null);
   if(mode==='local_reset')assert.equal(vm.runInContext('state.network',context),undefined);
   else assert.match(vm.runInContext('state.network.error',context),/reset/);
  }else{
   assert.equal(vm.runInContext('state.network.snapshot.nodes[0].tip_hash',context),snapshot.nodes[0].tip_hash);
   assert.match(document.getElementById('n-events').textContent,/actual backend event/);
   if(mode==='failure')assert.equal(vm.runInContext('state.network.error',context),'backend rejection verbatim');
   if(mode==='timeout'){assert.equal(reads,10);assert.ok(vm.runInContext('state.network.error',context));}
   if(mode==='divergent')assert.match(document.getElementById('n-summary').textContent,/tip/);
   if(mode==='different_full_tip'){
    assert.match(document.getElementById('n-nodes').innerHTML,/Khác height hoặc tip/);
   }
   if(mode==='offline'){
    const html=document.getElementById('n-nodes').innerHTML;
    assert.match(html,/OFFLINE — bản sao cục bộ có thể cũ/);
    assert.match(html,/older-tip/);assert.match(html,/metric-number">7</);
    assert.equal(reads,1);
   }
   if(mode==='agreement'){
    assert.match(document.getElementById('n-nodes').innerHTML,/Cùng height và tip/);
    assert.match(document.getElementById('n-summary').textContent,/Quan sát/);
    assert.equal(reads,1);
   }
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
