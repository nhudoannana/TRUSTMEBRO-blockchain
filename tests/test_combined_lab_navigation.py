"""Legacy Block URLs must enter the same initialized chain workspace."""
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('url', ['#block', '#blockchain', '#blocks'])
def test_combined_workspace_initializes_once_and_retains_chain_on_navigation(url):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),events={},elements=new Map(),calls=[];
class E{
 constructor(){this.value='';this.children=[];this.dataset={};this.hidden=false;this.disabled=false;}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}focus(){}setAttribute(){}removeAttribute(){}querySelectorAll(){return [];}
 set innerHTML(v){throw Error('Unsafe rendering');}
}
const document={documentElement:{dataset:{}},getElementById(id){if(!elements.has(id))elements.set(id,new E());return elements.get(id);},querySelectorAll:()=>[],createElement:()=>new E()};
const genesis={height:0,header:{timestamp:'2026-01-01T00:00:00Z',nonce:0,previous_hash:'0'.repeat(64)},stored_hash:'genesis',transaction:null};
const response={chain:[genesis],blocks:[{height:0,computed_hash:'genesis',own_validation:{valid:true,checks:{}},link_valid:true,prefix_valid:true}],validation:{valid:true,reason:'Real backend result fixture'},max_blocks:12};
const location={hash:process.argv[1]};
const c=vm.createContext({document,location,Option:class extends E{},window:{addEventListener:(k,f)=>events[k]=f},localStorage:{getItem:()=> 'dark',setItem(){}},navigator:{sendBeacon(){}},console,
 fetch:async(url)=>{calls.push(url);return {ok:true,json:async()=>response};}});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),c);
(async()=>{
 await new Promise(r=>setImmediate(r));
 assert.equal(document.getElementById('lab-blocks').hidden,false);
 assert.deepEqual(calls,['/api/labs/blockchain/init']);
 assert.equal(vm.runInContext('chainLab.result.chain.length',c),1);
 const owner=vm.runInContext('chainLab',c);
 location.hash='#sha';events.hashchange();location.hash='#blockchain';events.hashchange();
 await new Promise(r=>setImmediate(r));
 assert.equal(vm.runInContext('chainLab',c),owner);assert.equal(calls.length,1);
})();
"""
    result = subprocess.run(['node', '-e', script, url], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
