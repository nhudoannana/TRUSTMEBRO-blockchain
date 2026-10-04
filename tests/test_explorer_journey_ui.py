"""Public guided state round trips through the explorer; Node VM, not a browser."""
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('case', ['pow', 'pos', 'reset', 'restart', 'failure',
                                  'stale', 'blocked_storage', 'verification'])
def test_journey_explorer_return(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=[...fs.readFileSync('ui/trustmebro.html','utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const testCase=process.argv[1],elements=new Map(),calls=[],storage=new Map();
const document={querySelectorAll:()=>[],getElementById(id){if(!elements.has(id))elements.set(id,{value:'Node-2',hidden:true,innerHTML:'',textContent:'',focus(){},scrollIntoView(){}});return elements.get(id);}};
const wallet={id:'issuer-id',name:'Issuer',public_key_hex:'issuer-key',address:'issuer-address',private_key:'DO NOT SAVE'};
const record={credential_id:'credential',credential:{title:'Original'},issuer_wallet_id:wallet.id,issuer_address:wallet.address,transaction:{tx_id:'tx',sender_public_key:wallet.public_key_hex,private_key:'DO NOT SAVE'}};
const result={node_id:'Node-2',mined:testCase!=='pos',forged:testCase==='pos',block:{height:7,hash:'actual-hash',transaction_count:1},transaction_ids:['tx'],seconds:.012,signer:{name:'Issuer',address:'validator-address',public_key_hex:'validator-key'},reset_count:3};
let context,held;
context=vm.createContext({document,record,wallet,result,sessionStorage:{getItem:k=>storage.get(k)||null,setItem(k,v){if(testCase==='blocked_storage')throw Error('blocked');storage.set(k,v);},removeItem:k=>storage.delete(k)},
 fetch:async(url,options={})=>{
  calls.push(url);assert.ok(!options.method||options.method==='GET');
  if(testCase==='stale'&&url.includes('/wallets/'))await new Promise(r=>held=r);
  if(testCase==='failure')throw Error('offline API');
  if(url==='/api/wallets/issuer-id')return {ok:true,json:async()=>({...wallet,public_key_hex:testCase==='restart'?'new-key':wallet.public_key_hex})};
  assert.equal(url,'/api/mempool');return {ok:true,json:async()=>({reset_count:testCase==='reset'?4:3,nodes:[]})};
 }});
vm.runInContext(source.slice(0,source.indexOf('(function initTheme()')),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 run('state.step=3;state.max=3;state.selectedWalletId=wallet.id;state.selectedWallet=wallet;state.record=record;state.block=result.block;miningState().result=result;miningState().mode=result.forged?"pos":"pow";mempoolState().generation=3;mempoolState().submission={accepted:true};showMining(miningState(),mempoolState())');
 const html=document.getElementById('p-result').innerHTML;
 const href=html.match(/href="([^"]*explorer[^\"]*)"/)[1].replaceAll('&amp;','&');
 const url=new URL(href,'http://localhost');assert.equal(url.searchParams.get('node_id'),'Node-2');assert.equal(url.searchParams.get('height'),'7');
 if(testCase==='verification')run('state.step=5;verificationState().copy={title:"Edited presentation"};verificationState().nodeId="Node-3"');
 run('saveJourney()');
 if(testCase==='blocked_storage'){assert.equal(storage.size,0);return;}
 assert.equal(storage.size,1);assert.ok(![...storage.values()][0].includes('DO NOT SAVE'));
 run('state=freshState()');const pending=run('restoreJourney()');
 if(testCase==='stale'){await new Promise(r=>setImmediate(r));run('state=freshState();state.holder="New workflow"');held();}
 const restored=await pending;
 if(['reset','restart','failure','stale'].includes(testCase)){
  assert.equal(restored,false);assert.equal(run('state.record'),null);assert.equal(storage.size,0);
  if(testCase==='stale')assert.equal(run('state.holder'),'New workflow');return;
 }
 assert.equal(restored,true);assert.equal(run('state.step'),testCase==='verification'?5:3);
 assert.equal(run('state.selectedWallet.public_key_hex'),'issuer-key');assert.equal(run('state.block.hash'),'actual-hash');
 assert.equal(run('state.record.transaction.tx_id'),'tx');assert.equal(run('miningState().record===state.record'),true);
 assert.equal(run('miningState().pending'),false);assert.equal(run('mempoolState().submitting'),false);
 assert.equal(run('miningState().mode'),testCase==='pos'?'pos':'pow');assert.equal(run('canContinue(3)'),true);
 if(testCase==='verification')assert.equal(run('verificationState().copy.title'),'Edited presentation');
 assert.equal(calls.length,2);assert.equal(run('state.mempool.generation'),3);
})();
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
