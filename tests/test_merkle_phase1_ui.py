"""Node VM checks exercise the real Merkle handlers; fetch is deferred to test races.
Real-browser layout/accessibility observations are recorded separately.
"""
import subprocess
import pytest


@pytest.mark.parametrize("case", ["current_success", "current_error", "verify_success", "verify_error",
                                  "reset_success", "reset_error", "experiment", "inputs", "unavailable",
                                  "verify_sibling_success", "verify_sibling_error", "verify_direction_success",
                                  "verify_direction_error", "verify_root_success", "verify_root_error",
                                  "reset_retry_success", "reset_retry_error", "independent"])
def test_merkle_experiment_and_lifecycle(case):
    script = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), crypto = require('node:crypto');
const testCase = process.argv[1], elements = new Map(), events = {}, pending = [], calls = [];
class Element {
 constructor(tag='div') {this.tag=tag;this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};this.className='';this.checked=false;}
 set id(value){this._id=value;elements.set(value,this);} get id(){return this._id;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;}
 add(child){this.children.push(child);}
 querySelectorAll(){return this.children.flatMap(c=>[c,...c.querySelectorAll()]);}
 setAttribute(key,value){this[key]=value;}
 removeAttribute(key){delete this[key];}
 focus(){document.activeElement=this;}
 set innerHTML(value){throw Error('Unsafe HTML');}
}
const document={documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id)){const e=new Element();e.id=id;}return elements.get(id);},querySelectorAll(){return [];},createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>new Element(tag)};
const $=id=>document.getElementById(id);
const h=text=>crypto.createHash('sha256').update(text,'utf8').digest('hex');
function tree(body){
 let level=body.leaves.map(h),levels=[level.slice()];
 if(!level.length)levels=[[h('')]];
 while(level.length>1){const next=[];for(let i=0;i<level.length;i+=2)next.push(h(level[i]+(level[i+1]??level[i])));levels.push(next);level=next;}
 let proof=null;
 if(body.proof_index!=null){let i=body.proof_index;const siblings=[];for(const row of levels.slice(0,-1)){siblings.push([row[i%2?i-1:Math.min(i+1,row.length-1)],i%2?'left':'right']);i=Math.floor(i/2);}proof={index:body.proof_index,siblings,valid:true};}
 return {leaf_hashes:body.leaves.map(h),levels,root:levels.at(-1)[0],proof};
}
function verification(body){
 let current=h(body.leaf_text);const trace=[];
 for(const [sibling,direction] of body.proof){const before=current,normalized=sibling.toLowerCase();current=h(direction==='left'?normalized+current:current+normalized);trace.push({step:trace.length+1,current_hash:before,sibling_hash:normalized,direction,parent_hash:current});}
 return {leaf_hash:h(body.leaf_text),computed_root:current,expected_root:body.expected_root.toLowerCase(),valid:current===body.expected_root.toLowerCase(),trace};
}
let hold=false, accepted=true;
const context=vm.createContext({document,TextEncoder,Uint8Array,crypto:crypto.webcrypto,structuredClone,console,Option:class extends Element{constructor(label,value){super('option');this.textContent=label;this.value=value;}},location:{hash:'#merkle'},window:{confirm:()=>accepted,addEventListener:(k,f)=>events[k]=f},navigator:{sendBeacon(){}},localStorage:{getItem:()=>null,setItem(){}},
 fetch:async(url,options)=>{
  const body=JSON.parse(options.body);calls.push({url,body});
  if(hold){return await new Promise((resolve,reject)=>pending.push({url,body,resolve,reject}));}
  return {ok:true,json:async()=>url.endsWith('/merkle/verify')?verification(body):tree(body)};
 }});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),context);
const run=s=>vm.runInContext(s,context);context.event={preventDefault(){}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fill(text,index='2'){$('merkle-leaves').value=text;$('merkle-leaves').oninput();$('merkle-proof').value=index;$('merkle-proof').onchange();}
async function ready(){fill(Array.from({length:8},(_,i)=>'Leaf '+(i+1)).join('\n'));await run('computeMerkle(event)');run('keepMerkleA()');run('loadMerkleProof("A")');}
function resolveRequest(request,error=false){
 if(error)request.reject(new Error('delayed transport failure'));
 else request.resolve({ok:true,json:async()=>request.url.endsWith('/merkle/verify')?verification(request.body):tree(request.body)});
}
(async()=>{
 if(testCase.startsWith('current_')){
  hold=true;fill('A\nB\nC');
  const first=run('computeMerkle(event)');await tick();assert.equal(pending.length,1);
  fill('changed\nB\nC');
  assert.equal(run('merkleBusy'),false);assert.equal($('merkle-submit').disabled,false);
  const second=run('computeMerkle(event)');await tick();assert.equal(pending.length,2);
  resolveRequest(pending[0],testCase.endsWith('error'));await first;
  assert.equal(run('merkleBusy'),true);assert.equal($('merkle-submit').disabled,true);
  assert.equal(run('merklePrevious'),null);assert.equal($('merkle-error').textContent,'');
  resolveRequest(pending[1]);await second;
  assert.equal(run('merkleBusy'),false);assert.equal($('merkle-root-full').textContent,tree(pending[1].body).root);
 }else if(testCase.startsWith('verify_')){
  await ready();hold=true;
  const first=run('verifyMerkle(event)');await tick();
  if(testCase.includes('sibling')){$('merkle-sibling-0').value=h('changed sibling');$('merkle-sibling-0').oninput();}
  else if(testCase.includes('direction')){$('merkle-direction-0').value='left';$('merkle-direction-0').onchange();}
  else if(testCase.includes('root')){$('merkle-expected-root').value=h('changed root');$('merkle-expected-root').oninput();}
  else {$('merkle-verify-text').value+=' changed';$('merkle-verify-text').oninput();}
  assert.equal($('merkle-verify-submit').disabled,false);
  const second=run('verifyMerkle(event)');await tick();assert.equal(pending.length,2);
  resolveRequest(pending[0],testCase.endsWith('error'));await first;
  assert.equal($('merkle-verify-submit').disabled,true);
  assert.equal($('merkle-verify-result').hidden,true);assert.equal($('merkle-verify-error').textContent,'');
  resolveRequest(pending[1]);await second;
  assert.equal($('merkle-verify-submit').disabled,false);
  assert.match($('merkle-verify-result').textContent,/Không khớp/);
 }else if(testCase.startsWith('reset_retry_')){
  await ready();hold=true;
  const oldCurrent=run('computeMerkle(event)'),oldCheck=run('verifyMerkle(event)');await tick();
  run('resetMerkle()');fill('fresh leaf','0');
  $('merkle-verify-text').value='fresh leaf';$('merkle-verify-text').oninput();
  $('merkle-expected-root').value=h('fresh leaf');$('merkle-expected-root').oninput();
  const newCurrent=run('computeMerkle(event)'),newCheck=run('verifyMerkle(event)');await tick();
  assert.equal(pending.length,4);
  resolveRequest(pending[0],testCase.endsWith('error'));resolveRequest(pending[1],testCase.endsWith('error'));
  await Promise.all([oldCurrent,oldCheck]);
  assert.equal(run('merkleBusy'),true);assert.equal($('merkle-verify-submit').disabled,true);
  assert.equal(run('merklePrevious'),null);assert.equal($('merkle-verify-result').hidden,true);
  assert.equal($('merkle-error').textContent,'');assert.equal($('merkle-verify-error').textContent,'');
  resolveRequest(pending[2]);resolveRequest(pending[3]);await Promise.all([newCurrent,newCheck]);
  assert.equal($('merkle-root-full').textContent,h('fresh leaf'));
  assert.match($('merkle-verify-result').textContent,/Khớp root/);
 }else if(testCase.startsWith('reset_')){
  await ready();hold=true;
  const current=run('computeMerkle(event)'),check=run('verifyMerkle(event)');await tick();
  run('resetMerkle()');assert.equal($('merkle-verify-submit').disabled,false);
  for(const request of pending)resolveRequest(request,testCase.endsWith('error'));
  await Promise.all([current,check]);
  assert.equal(run('merklePrevious'),null);assert.equal(run('merkleExperiment.savedA'),null);
  assert.equal($('merkle-result').hidden,true);assert.equal($('merkle-verify-result').hidden,true);
  for(const id of ['merkle-root-full','merkle-verify-trace','merkle-saved-data','merkle-verify-error','merkle-error'])assert.equal($(id).textContent,'');
 }else if(testCase==='independent'){
  await ready();const expected=$('merkle-expected-root').value;hold=true;
  const check=run('verifyMerkle(event)');await tick();
  fill('different tree draft','0');run('resetHash()');
  assert.equal($('merkle-verify-submit').disabled,true);assert.equal($('merkle-expected-root').value,expected);
  resolveRequest(pending[0]);await check;assert.match($('merkle-verify-result').textContent,/Khớp root/);
  assert.equal($('merkle-expected-root').value,expected);
 }else if(testCase==='experiment'){
  assert.equal($('merkle-practice').hidden,false);assert.equal($('signatures-theory').hidden,false);
  await ready();const a=$('merkle-expected-root').value,reference=run('JSON.stringify(merkleExperiment.savedA)');
  await run('verifyMerkle(event)');assert.match($('merkle-verify-result').textContent,/Khớp root/);
  fill('Leaf 1\nLeaf 2\nLeaf 3 changed\nLeaf 4\nLeaf 5\nLeaf 6\nLeaf 7\nLeaf 8');
  await run('computeMerkle(event)');assert.equal($('merkle-expected-root').value,a);assert.equal(run('JSON.stringify(merkleExperiment.savedA)'),reference);
  const all=e=>[e,...e.children.flatMap(all)];
  assert.equal(all($('merkle-tree')).filter(e=>e.tag==='g'&&e.dataset.node&&e.class.includes('changed')).length,4);
  assert.equal(all($('merkle-a-tree')).filter(e=>e.tag==='g'&&e.dataset.node).length,15);
  assert.equal($('merkle-a-root-full').textContent,a);
  assert.match($('merkle-cause').textContent,/4/);
  run('copyMerkleLeaf()');await run('verifyMerkle(event)');assert.match($('merkle-verify-result').textContent,/Không khớp/);
  assert.equal($('merkle-expected-root').value,a);
  run('loadMerkleProof("current")');await run('verifyMerkle(event)');assert.match($('merkle-verify-result').textContent,/Khớp root/);
  assert.notEqual($('merkle-expected-root').value,a);assert.equal(run('JSON.stringify(merkleExperiment.savedA)'),reference);
  assert.ok($('merkle-verify-trace').textContent.includes($('merkle-expected-root').value));
  const preserved=run('JSON.stringify([signature,chainLab,networkLab,comparison])');run('resetMerkle()');
  assert.equal(run('JSON.stringify([signature,chainLab,networkLab,comparison])'),preserved);
 }else if(testCase==='inputs'){
  assert.deepEqual(Array.from(run('readLeaves(" a \\n\\n")')),[' a ','','']);
  fill(' A \n\nB\n','0');run('removeMerkleLeaf()');assert.equal($('merkle-leaves').value,'\nB\n');
  fill('x\n','0');run('removeMerkleLeaf()');assert.equal($('merkle-leaves').value,'x\n');assert.match($('merkle-status').textContent,/rỗng/);
  fill(Array.from({length:16},()=> 'x').join('\n'),'0');run('addMerkleLeaf()');assert.equal(run('readLeaves($("merkle-leaves").value).length'),16);
  for(let i=0;i<5;i++)run('addMerkleProofRow()');assert.equal(run('merkleExperiment.verification.proof.length'),4);
  $('merkle-prediction-answer').value='4';run('revealMerklePrediction()');assert.match($('merkle-prediction-feedback').textContent,/ba tổ tiên/);
 }else if(testCase==='unavailable'){
  await ready();context.fetch=async()=>({ok:true,json:async()=>({valid:true})});
  await run('verifyMerkle(event)');assert.equal($('merkle-verify-result').hidden,true);assert.match($('merkle-verify-error').textContent,/khả dụng/);
  context.fetch=async()=>({ok:false,status:422,json:async()=>({detail:[{loc:['body','proof',0,0],msg:'bad format'}]})});
  await run('verifyMerkle(event)');assert.match($('merkle-verify-error').textContent,/định dạng/);
  assert.equal($('merkle-expected-root').value.length,64);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(["node", "-e", script, case], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
