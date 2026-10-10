"""Node VM lifecycle checks; not browser evidence."""
import subprocess
from pathlib import Path
import pytest

@pytest.mark.parametrize("case", ["duplicate", "reset", "late_create", "stale", "domain", "transport", "expired", "scenario_draft", "mining_draft", "page_restore"])
def test_fork_frontend_lifecycle(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const calls=[],elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,{textContent:'',disabled:false});return elements.get(id)};
let hold,fail=0,nextOutcome='updated',revision=0;
function elem(tag){return {tag,value:'',checked:false,children:[],append(...c){this.children.push(...c)},replaceChildren(...c){this.children=c},querySelectorAll(selector){const all=this.children.flatMap(c=>[c,...(c.children||[])]);return all.filter(c=>c.tag==='input'&&(!selector.includes(':checked')||c.checked))}};}

const snap=handle=>({lab_handle:handle,revision,nodes:[],links:[],pending_messages:[],events:[]});
const context=vm.createContext({document:{getElementById:$,createElement:elem},window:{},console,AbortController,setTimeout,clearTimeout,
fetch:async(url,options={})=>{
 calls.push({url,method:options.method||'GET'});
 if(options.method==='DELETE')return {ok:true,json:async()=>({cleared:true})};
 if(hold){const h=hold;hold=null;await h;}
 if(fail===-1){fail=0;throw Error('network lost');}
 if(fail){const status=fail;fail=0;return {ok:false,status,json:async()=>({detail:{code:'stale_revision',message:'old revision'}})};}
 return {ok:true,json:async()=>options.method==='POST'&&url==='/api/labs/fork'?snap('new'):
 options.method==='POST'?{snapshot:snap('old'),outcome:{code:nextOutcome,message:'domain detail'}}:snap('old')};
}});
let source=fs.readFileSync('ui/fork_lab.js','utf8').split('// Bind the independent lab.')[0];
vm.runInContext(source+'\nlet renders=0;render=()=>{renders++};globalThis.test={action,reset,refresh,mineChoices,leave,state:()=>owner,renders:()=>renders};})();',context);
const api=context.test,tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await api.action('create');assert.equal(api.state().snapshot.lab_handle,'new');
 if(process.argv[1]==='duplicate'){
  let release;hold=new Promise(r=>release=r);const p=api.action('sync',{node_id:'Node-1'});await tick();
  const n=calls.length;await api.action('sync',{});assert.equal(calls.length,n);release();await p;assert.equal(api.state().busy,false);
 }else if(process.argv[1]==='reset'){
  let release;hold=new Promise(r=>release=r);const p=api.action('sync',{});await tick();await api.reset();
  await api.action('create');const current=api.state();release();await p;assert.equal(api.state(),current);assert.equal(current.snapshot.lab_handle,'new');assert.equal(current.busy,false);
 }else if(process.argv[1]==='late_create'){
  await api.reset();let release;hold=new Promise(r=>release=r);const p=api.action('create');await tick();await api.reset();
  release();await p;assert.equal(api.state().snapshot,null);assert.ok(calls.filter(c=>c.method==='DELETE').length>=2);
 }else if(process.argv[1]==='stale'){
  fail=409;const n=calls.length;await api.action('sync',{});assert.equal(calls.length,n+2);assert.equal(calls.at(-1).method,'GET');
  assert.match(api.state().notice,/không tự/);assert.equal(api.state().busy,false);
 }else if(process.argv[1]==='domain'){
  for(const code of ['blocked','mining_incomplete','scenario_incomplete']){nextOutcome=code;await api.action('sync',{});assert.ok(api.state().notice.includes(code));}
 }else if(process.argv[1]==='transport'){
  fail=-1;const n=calls.length;await api.action('sync',{});assert.equal(calls.length,n+2);assert.equal(calls.at(-1).method,'GET');assert.equal(api.state().busy,false);
 }else if(process.argv[1]==='scenario_draft'){
  let release;hold=new Promise(r=>release=r);const p=api.action('scenario',{scenario:'E1'});await tick();
  $('fork-scenario').value='E2';release();await p;assert.equal(api.state().scenario,'E1');
 }else if(process.argv[1]==='mining_draft'){
  api.state().snapshot.nodes=[{node_id:'Node-1',tip_hash:'tip',blocks:[{hash:'tip',height:2,classification:'active'},{hash:'side',height:1,classification:'stale'}],mempool:[{tx_id:'tx',payload:{label:'TX'}}]}];
  $('fork-node').value='Node-1';
  Object.assign($('fork-parent'),elem('select'));Object.assign($('fork-txs'),elem('div'));
  api.mineChoices();$('fork-parent').value='side';$('fork-txs').querySelectorAll('input')[0].checked=true;
  api.mineChoices();assert.equal($('fork-parent').value,'side');assert.equal($('fork-txs').querySelectorAll('input')[0].checked,true);
 }else if(process.argv[1]==='page_restore'){
  const before=api.renders();api.leave();assert.equal(api.state().snapshot,null);assert.ok(api.renders()>before,'cached DOM must be reset with owner');
 }else {fail=404;await api.refresh();assert.equal(api.state().snapshot,null);assert.match(api.state().notice,/hết hạn/);}
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", script, case], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr

def test_fork_lab_learning_contract():
    html = Path("ui/labs.html").read_text(encoding="utf-8")
    for label in ["fork-objectives", "fork-basics", "fork-prediction", "fork-practice", "fork-results", "fork-limits"]:
        assert f'id="{label}"' in html
    source = Path("ui/fork_lab.js").read_text(encoding="utf-8")
    assert "/api/labs/fork" in source
    assert "innerHTML" not in source
