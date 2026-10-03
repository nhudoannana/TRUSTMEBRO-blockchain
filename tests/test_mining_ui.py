"""Actual frontend handlers under Node VM; separate from browser checks."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('outcome', ['mined', 'empty', 'remote_reset', 'local_reset', 'reset_after_result'])
def test_mining_ui_pending_and_session_guard(outcome):
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = [...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements = new Map();
const document = {querySelectorAll:()=>[],getElementById(id){
  if(!elements.has(id))elements.set(id,{value:'',hidden:true,disabled:false,textContent:'',innerHTML:''});
  return elements.get(id);
}};
const outcome=process.argv[1];
let posts=0, returned=false;
let context;
const record={credential_id:'cred',transaction:{tx_id:'signed-tx'}};
const result={node_id:'Node-1',mined:outcome!=='empty',reason:outcome==='empty'?'Mempool trống — không có TX để mine':null,
  block:{height:1,hash:'000hash',previous_hash:'parent',merkle_root:'root',difficulty:3,nonce:10,transaction_count:1},
  transaction_ids:['signed-tx'],seconds:0.012,attempts:11,reset_count:outcome==='remote_reset'?1:0};
context=vm.createContext({document,console,record,fetch:async(url,options={})=>{
  if(options.method==='POST'){
    posts++;
    assert.equal(url,'/api/mining/pow');
    assert.deepEqual(JSON.parse(options.body),{node_id:'Node-1'});
    assert.equal(document.getElementById('p-submit').disabled,true);
    assert.match(document.getElementById('p-status').textContent,/Hãy chờ/);
    await vm.runInContext('handlePowMining({preventDefault(){}})',context); // repeat click is ignored
    if(outcome==='local_reset')vm.runInContext('state=freshState()',context);
    return {ok:true,json:async()=>{returned=true;return result;}};
  }
  if(url==='/api/network')return {ok:true,json:async()=>({reset_count:0,nodes:[{node_id:'Node-1',status:'ONLINE'}],online_nodes_agree:true,online_nodes_valid:true})};
  assert.equal(url,'/api/mempool');
  return {ok:true,json:async()=>({reset_count:outcome==='reset_after_result'&&returned?1:0,
    nodes:[{node_id:'Node-1',status:'ONLINE',pending_count:returned?0:1,transactions:returned?[]:[record.transaction]}]})};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('state.record=record;state.step=3;render=async()=>{};',context);
(async()=>{
  await vm.runInContext('renderStep3()',context);
  document.getElementById('p-node').value='Node-1';
  await vm.runInContext('handlePowMining({preventDefault(){}})',context);
  assert.equal(posts,1);
  if(outcome.includes('reset')){
    assert.equal(vm.runInContext('state.block',context),null);
    assert.equal(vm.runInContext('state.record',context),null);
    if(outcome!=='local_reset')assert.match(document.getElementById('c-error').textContent,/reset/);
  }else{
    assert.equal(document.getElementById('p-submit').disabled,true); // no pending TXs: prevent an empty repeat
    assert.equal(document.getElementById('p-next').disabled,outcome!=='mined');
    assert.equal(vm.runInContext('state.mempool.nodes[0].pending_count',context),0);
    if(outcome==='mined'){
      assert.equal(vm.runInContext('state.block.hash',context),'000hash');
      assert.match(document.getElementById('p-result').innerHTML,/0.012/);
      assert.match(document.getElementById('p-result').innerHTML,/signed-tx/);
    }else{
      assert.match(document.getElementById('p-status').textContent,/Mempool trống/);
      assert.equal(vm.runInContext('state.block',context),null);
    }
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, outcome],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
