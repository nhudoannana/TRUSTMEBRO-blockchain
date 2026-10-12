"""P3-A3 Node VM interaction tests; browser acceptance is recorded separately."""
import subprocess
import pytest

@pytest.mark.parametrize("case", [
    "issue", "revoke", "legacy", "C1", "C2", "C3", "remine",
    "pending_active", "pending_unknown", "placements", "incomplete", "transition",
    "edit", "reset", "stale", "expired", "late_failure", "no_remine",
])
def test_credential_fork_ui(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function elem(tag='div'){
 return {tag,value:'',checked:false,disabled:false,hidden:false,dataset:{},children:[],events:{},
 textContent:'',append(...c){this.children.push(...c)},replaceChildren(...c){this.children=c},
 setAttribute(k,v){this[k]=v},addEventListener(k,f){this.events[k]=f},focus(){},
 querySelectorAll(selector){
  const all=this.children.flatMap(c=>[c,...c.querySelectorAll('*')]);
  if(selector==='*')return all;
  if(selector==='button')return all.filter(c=>c.tag==='button');
  return all.filter(c=>c.tag==='input'&&(!selector.includes(':checked')||c.checked));
 }};
}
const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,elem());return elements.get(id)};
const text=e=>e.textContent+e.children.map(text).join(' ');
const calls=[];let response,hold,fail=0,rev=7;
const tx=(id,type)=>({tx_id:id,tx_type:type,payload:{credential_id:'cert-real',reason:'withdraw',label:'lab'}});
const placement=(id,type,hash)=>({transaction:tx(id,type),block_hash:hash,height:2,transaction_index:0});
const node=()=>({node_id:'Node-1',status:'ONLINE',height:2,chain_work:32,chain_valid:true,
 tip_hash:'tip-current',blocks:[{hash:'tip-current',parent_hash:'ancestor',height:2,difficulty:1,work:16,classification:'active'}],
 branches:[],orphans:[],mempool:[tx('revoke-real','REVOKE')],
 credential_states:{'cert-real':{confirmed_status:'ACTIVE',status:'ACTIVE',confirmed_transactions:[placement('issue-real','ISSUE','ancestor')],
 pending_transactions:[tx('revoke-real','REVOKE')],stale_transactions:[placement('revoke-real','REVOKE','stale-block')]}},
 transaction_states:{'revoke-real':{active_blocks:[],stale_blocks:[{block_hash:'stale-block',height:2,transaction_index:0}],pending:true}}});
const snap=()=>({lab_handle:'owned',revision:rev,expires_in_seconds:900,nodes:[node()],links:[],
 pending_messages:[{id:'message-returned',sequence:19,kind:'BLOCK',from:'Node-3',to:'Node-1',reference:'winning-real',blocked_reason:null}],events:[]});
const continuation=()=>({message_id:'message-returned',node_id:'Node-1',peer_node_id:'Node-3',credential_id:'cert-real',
 issue_tx_id:'issue-real',revoke_tx_id:'revoke-real',remine_tx_ids:['revoke-real'],
 learning_goal:'Backend learner goal',next_steps:['Backend next action']});
const context=vm.createContext({document:{getElementById:$,createElement:elem},window:{addEventListener(){}},
 console,AbortController,setTimeout,clearTimeout,fetch:async(url,options={})=>{
 calls.push({url,method:options.method||'GET',body:options.body&&JSON.parse(options.body)});
 const captured=response,err=fail;fail=0;
 if(hold){const h=hold;hold=null;await h;}
 if(err)return {ok:false,status:err,json:async()=>({detail:{code:'stale_revision',message:'old'}})};
 return {ok:true,json:async()=>options.method==='DELETE'?{cleared:true}:
 url==='/api/labs/fork'?snap():options.method==='POST'?
 (captured||{snapshot:snap(),outcome:{code:'accepted_tx',message:'actual acceptance'}}):snap()};
}});
$('fork-node').value='Node-1';$('fork-scenario').value='C1';$('fork-credential-action').value='ISSUE';
$('fork-credential-id').value='cert-real';$('fork-credential-text').value='content';
let source=fs.readFileSync('ui/fork_lab.js','utf8');
source=source.replace(/\}\)\(\);\s*$/, 'globalThis.test={action,edit,reset,refresh,render,state:()=>owner};})();');
vm.runInContext(source,context);
const api=context.test,tick=()=>new Promise(r=>setImmediate(r));
const submit=async id=>{ $(id).onsubmit({preventDefault(){}}); await tick(); };
const findButton=(id,label)=>$(id).querySelectorAll('button').find(b=>b.textContent===label);
(async()=>{
 await api.action('create');
 const mode=process.argv[1];
 if(['issue','revoke'].includes(mode)){
  $('fork-credential-action').value=mode==='issue'?'ISSUE':'REVOKE';
  await submit('fork-credential-form');
  const c=calls.at(-1);assert.ok(c.url.endsWith('/credential-transactions'));
  assert.equal(c.body.credential_id,'cert-real');assert.equal(c.body.expected_revision,7);
  assert.equal(c.body.action,mode==='issue'?'ISSUE':'REVOKE');
  assert.equal(c.body[mode==='issue'?'label':'reason'],'content');
  assert.equal(Object.hasOwn(c.body,mode==='issue'?'reason':'label'),false);
 }else if(mode==='legacy'){
  $('fork-label').value='old';await submit('fork-issue-form');assert.ok(calls.at(-1).url.endsWith('/transactions'));
 }else if(['C1','C2','C3','remine','incomplete','no_remine'].includes(mode)){
  response={snapshot:snap(),outcome:{code:mode==='incomplete'?'scenario_incomplete':'scenario_ready',message:'domain result'},
   continuation:continuation(),setup_completed_steps:[{operation:'mine',block_hash:'actual-partial-block'}],
   setup_failure:{code:'mining_incomplete',message:'budget exhausted'}};
  if(mode==='C2'||mode==='C3')delete response.continuation.remine_tx_ids;
  const scenario=mode.startsWith('C')?mode:'C1';
  await api.action('scenario',{scenario});
  const content=text($('fork-continuation'));
  if(mode==='incomplete'){
   assert.equal(api.state().continuation,null,'HTTP200 incomplete must not retain actionable continuation');
   assert.match(text($('fork-report')),/mining_incomplete/);assert.match(text($('fork-report')),/Reset/);
   assert.match(text($('fork-report')),/actual-partial-block/);
  }else if(mode==='remine'){
   api.state().snapshot.pending_messages=[];api.state().snapshot.revision=21;api.render();
   const b=findButton('fork-continuation','Đào lại REVOKE đang chờ');assert.ok(b&&!b.disabled);
   response=null;await b.onclick();const c=calls.at(-1);
   assert.ok(c.url.endsWith('/mine'));assert.equal(c.body.parent_hash,'tip-current');
   assert.equal(c.body.expected_revision,21);assert.equal(c.body.node_id,'Node-1');
   assert.deepEqual(c.body.tx_ids,['revoke-real']);assert.equal(c.body.difficulty,1);
  }else if(mode==='no_remine'){
   api.state().snapshot.nodes[0].mempool=[];api.render();
   const b=findButton('fork-continuation','Đào lại REVOKE đang chờ');assert.ok(!b||b.disabled);
  }else{
   assert.match(content,/Backend learner goal/);assert.match(content,/Backend next action/);
   const b=findButton('fork-continuation','Giao tin quyết định');assert.ok(b&&!b.disabled);
   response=null;rev=12;api.state().snapshot.revision=12;await b.onclick();
   assert.equal(calls.at(-1).body.message_id,'message-returned');assert.equal(calls.at(-1).body.expected_revision,12);
  }
 }else if(mode==='pending_active'||mode==='pending_unknown'){
  if(mode==='pending_unknown'){const c=api.state().snapshot.nodes[0].credential_states['cert-real'];c.confirmed_status=null;c.status=null;c.confirmed_transactions=[];}
  api.render();const content=text($('fork-nodes'));
  assert.match(content,mode==='pending_active'?/Đã xác nhận: ACTIVE/:/Chưa có trên active chain/);
  assert.match(content,/Pending.*chưa xác nhận/);assert.match(content,/REVOKE/);
 }else if(mode==='placements'){
  const c=api.state().snapshot.nodes[0].credential_states['cert-real'];
  c.confirmed_transactions.push(placement('revoke-real','REVOKE','winner-block'));c.pending_transactions=[];
  api.render();const content=text($('fork-nodes'));
  assert.match(content,/Active.*đã xác nhận/);assert.match(content,/Stale.*không quyết định/);
  assert.match(content,/winner-block/);assert.match(content,/stale-block/);
 }else if(mode==='transition'){
  response={snapshot:snap(),outcome:{code:'accepted_block',message:'adopted'},transition:{
   old_work:32,new_work:272,selection_reason:'higher_work',common_ancestor:{hash:'ancestor',height:1},
   detached_hashes:['detached-real'],attached_hashes:['attached-real'],counts:{restored:0,rejected:1},
   transactions:[{tx_id:'revoke-real',disposition:'rejected',reason_code:'not_active_on_chain',message:'not confirmed'}]}};
  await api.action('deliver',{message_id:'message-returned'});
  const content=text($('fork-report'));assert.match(content,/Restored thực: 0/);assert.match(content,/Tách 1.*gắn 1/);
  assert.match(content,/not_active_on_chain/);assert.match(content,/detached-real/);
 }else if(mode==='stale'||mode==='expired'){
  fail=mode==='stale'?409:404;const before=calls.length;await submit('fork-credential-form');
  assert.equal(calls.length,before+(mode==='stale'?2:1));
  if(mode==='stale')assert.equal(calls.at(-1).method,'GET');else assert.equal(api.state().snapshot,null);
 }else{
  let release,newRelease;
  response={snapshot:snap(),outcome:{code:'scenario_ready',message:'old'},continuation:continuation()};
  if(mode==='late_failure')fail=500;
  hold=new Promise(r=>release=r);const old=api.action('scenario',{scenario:'C1'});await tick();
  if(mode==='reset'){await api.reset();await api.action('create');release();await old;assert.equal(api.state().continuation,null);}
  else{
   api.edit();assert.equal(api.state().busy,false);assert.equal(api.state().uncertain,true);
   response=null;await api.refresh();hold=new Promise(r=>newRelease=r);
   const newer=api.action('credential-transactions',{node_id:'Node-1',action:'ISSUE',credential_id:'new',label:'new'});await tick();
   release();await old;assert.equal(api.state().busy,true,'old response must not unlock newer request');
   assert.equal(api.state().continuation,null,'invalidated scenario continuation must not revive');
   newRelease();await newer;assert.equal(api.state().busy,false);
  }
 }
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    # The VM executes actual handlers and rendering; its backend fixtures are not browser evidence.
    result = subprocess.run(["node", "-e", script, case], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
