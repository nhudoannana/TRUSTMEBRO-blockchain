"""Browser-independent Node VM behavior checks; no mock fallback in UI."""
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('case', ['results', 'error', 'reset_pending', 'selection', 'accepted', 'changed_input'])
def test_attack_handlers(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),calls=[],events={},testCase=process.argv[1];let release;
class Element{
 constructor(){this.value='';this.children=[];this.hidden=false;this.disabled=false;this.textContent='';}
 append(...nodes){this.children.push(...nodes)}replaceChildren(...nodes){this.children=nodes}
 setAttribute(k,v){this[k]=v}set innerHTML(v){throw Error('Unsafe rendering')}
}
const document={documentElement:{dataset:{theme:'dark'}},getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id)},createElement(){return new Element()}};
const $=id=>document.getElementById(id);$('attack-scenario').value='tamper';$('attack-title').value='Edited';
const tx={sender_public_key:'issuer-key'.repeat(10),tx_id:'a'.repeat(64),signature:'signed',payload:{title:'Original',issuer_name:'Trusted issuer'}};
const result=scenario=>({scenario,context_generation:'opaque',authorized_issuer:{address:'issuer-address',public_key_hex:tx.sender_public_key},attacker:scenario==='impersonation'?{address:'attacker-address',public_key_hex:'attacker-key'}:null,
 baseline:{transaction:tx,verification:{valid:true,reason:'Actual baseline OK',computed_hash:tx.tx_id,signature_checked:true},submission:{accepted:true,reason:'Actual accepted'}},
 attack:{transaction:{...tx,payload:{...tx.payload,title:'<img src=x onerror=alert(1)>'}},verification:{valid:scenario!=='tamper',reason:'Actual verifier reason',computed_hash:'b'.repeat(64),signature_checked:scenario!=='tamper'},submission:{accepted:testCase==='accepted',reason:'Exact backend rejection <unsafe>'}},failure_layer:scenario==='tamper'?'transaction_hash':scenario==='impersonation'?'issuer_authorization':'duplicate_submission'});
const context=vm.createContext({document,window:{addEventListener:(k,f)=>events[k]=f},localStorage:{getItem:()=> 'dark',setItem(){}},console,
fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});assert.equal($('attack-run').disabled,true);
 if(testCase==='reset_pending')await new Promise(r=>release=r);
 if(testCase==='error')return {ok:false,status:503,json:async()=>({detail:{message:'Actual capacity error'}})};
 return {ok:true,json:async()=>result(JSON.parse(options.body).scenario)};}});
const run=s=>vm.runInContext(s,context),text=e=>e.textContent+' '+e.children.map(text).join(' ');
vm.runInContext(fs.readFileSync('ui/attacks.js','utf8'),context);
context.event={preventDefault(){}};
(async()=>{
 if(testCase==='selection'){
  $('attack-title').value=' ';$('attack-title').oninput();assert.equal($('attack-run').disabled,true);
  assert.ok($('attack-control-note').textContent.length);
  $('attack-scenario').value='replay';$('attack-scenario').onchange();assert.equal($('attack-run').disabled,false);
  assert.equal($('attack-title-field').hidden,true);assert.equal($('attack-title').required,false);assert.equal(calls.length,0);return;
 }
 const pending=run('runAttack(event)');await Promise.resolve();
 if(testCase==='reset_pending'){
  await run('runAttack(event)');assert.equal(calls.length,1);
  $('attack-reset').onclick();assert.equal($('attack-run').disabled,false);
  release();await pending;assert.equal($('attack-results').hidden,true);assert.equal(run('attackState.result'),null);return;
 }
 await pending;
 assert.equal($('attack-run').disabled,false);
 if(testCase==='error'){
  assert.equal($('attack-error').textContent,'Actual capacity error');assert.equal($('attack-results').hidden,true);
  assert.equal(run('attackState.result'),null);return;
 }
 assert.equal($('attack-results').hidden,false);
 assert.ok(text($('attack-data')).includes('<img src=x onerror=alert(1)>'));
 assert.ok(text($('attack-outcome')).includes('Exact backend rejection <unsafe>'));
 if(testCase==='accepted'){
  assert.ok($('attack-outcome').className.includes('unexpected'));
  assert.ok(!$('attack-outcome').className.split(' ').includes('valid'));
  return;
 }
 assert.ok($('attack-outcome').className.includes('invalid'));
 const first=text($('attack-outcome'));
 assert.ok(first.includes('Đối chiếu hash giao dịch'));
 assert.ok(!first.includes('Chữ ký số ECDSA'));
 if(testCase==='changed_input'){
  $('attack-title').value='A newer draft';$('attack-title').oninput();
  assert.ok($('attack-result-context').textContent.includes('lượt thử trước'));
  assert.equal(text($('attack-outcome')),first);assert.equal(calls.length,1);
  $('attack-reset').onclick();assert.equal($('attack-result-context').textContent,'');return;
 }
 assert.ok(text($('attack-data')).includes('ECDSA')); // hash gate is explained visibly.
 for(const scenario of ['impersonation','replay']){
  $('attack-scenario').value=scenario;$('attack-scenario').onchange();assert.equal($('attack-results').hidden,true);
  await run('runAttack(event)');assert.notEqual(text($('attack-outcome')),first);
  assert.ok(!('edited_title' in calls.at(-1).body));
 }
 assert.ok(calls.every(c=>c.url==='/api/labs/attacks/run'));
 $('attack-reset').onclick();assert.equal($('attack-results').hidden,true);assert.equal(calls.length,3);
})();
"""
    response = subprocess.run(['node', '-e', script, case], cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert response.returncode == 0, response.stdout + response.stderr
