"""Run real step-3 handlers with Node's VM; not browser verification."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('outcome', ['accepted', 'rejected', 'stale'])
def test_mempool_ui_contract_and_bounded_polling(outcome):
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('ui/trustmebro.html','utf8');
const source = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements = new Map();
const document = {querySelectorAll:()=>[],getElementById(id){
  if (!elements.has(id)) elements.set(id,{value:'',textContent:'',hidden:true,disabled:false});
  return elements.get(id);
}};
const outcome = process.argv[1];
const record = {credential_id:'stored-credential',transaction:{tx_id:'signed-tx'}};
let reads = 0, posted = false;
const context = vm.createContext({document,console,record,setTimeout:cb=>cb(),fetch:async(url,options={})=>{
  assert.equal(url,'/api/mempool');
  if (options.method === 'POST') {
    assert.equal(document.getElementById('m-submit').disabled,true);
    assert.deepEqual(JSON.parse(options.body),{credential_id:record.credential_id,node_id:'Node-1'});
    posted = true;
    if (outcome === 'stale') return {ok:false,json:async()=>({detail:{code:'credential_not_found'}})};
    return {ok:true,json:async()=>({accepted:outcome==='accepted',reason:'backend <verbatim>',
      reason_source:'backend',node_id:'Node-1',tx_id:'signed-tx',reset_count:0})};
  }
  reads++;
  return {ok:true,json:async()=>({reset_count:0,nodes:[1,2,3].map(i=>({node_id:'Node-'+i,
    status:'ONLINE',pending_count:posted&&i===1?1:0,
    transactions:posted&&i===1?[record.transaction]:[]}))})};
}});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
vm.runInContext('state.record=record;state.step=2;render=async()=>{};',context);
(async()=>{
  await vm.runInContext('renderStep2()',context);
  document.getElementById('m-node').value = 'Node-1';
  await vm.runInContext('handleMempoolSubmit({preventDefault(){}})',context);
  assert.equal(posted,true);
  if (outcome==='stale') {
    assert.equal(vm.runInContext('state.record',context),null);
    assert.equal(vm.runInContext('state.step',context),1);
    assert.match(document.getElementById('c-error').textContent,/reset/);
  } else {
    assert.equal(document.getElementById('m-submit').disabled,false);
    assert.match(document.getElementById('m-status').textContent,/backend <verbatim>/);
    assert.equal(reads,outcome==='accepted'?7:2); // initial read plus bounded refresh
    if (outcome==='accepted') assert.match(document.getElementById('m-propagation').textContent,/1\/3/);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, outcome],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
