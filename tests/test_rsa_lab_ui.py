"""Node VM frontend behavior; not browser evidence."""
import subprocess
from pathlib import Path
import pytest

@pytest.mark.parametrize('case',['replace_failure','replace_success','reset_create','empty_success','edit_encrypt','edit_decrypt','old_error','reset_crypto','transport','expired','non_utf8','pagehide','retained'])
def test_rsa_frontend_lifecycle(case):
    assert Path('ui/rsa_lab.js').is_file(), "RSA educational frontend is missing"
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,hidden:false,className:'',setAttribute(){}});return elements.get(id)};
let hold,fail=0,keyNumber=0,code='decrypted',plaintext='';
const calls=[],key=n=>({key_handle:'key-'+n,public_key_pem:'PEM-'+n,public_key_fingerprint:'f'.repeat(64),expires_in_seconds:900});
const context=vm.createContext({document:{getElementById:$},window:{},TextEncoder,AbortController,setTimeout:(fn,ms)=>ms===1000?0:setTimeout(fn,ms),clearTimeout,fetch:async(url,options={})=>{
 const method=options.method||'GET',body=options.body&&JSON.parse(options.body);calls.push({url,method,body});
 const responseFail=fail;fail=0;const n=++keyNumber;
 if(method==='DELETE')return{ok:true,json:async()=>({cleared:true})};
 if(hold){const h=hold;hold=null;await h;}
 if(responseFail===-1)throw Error('network');
 if(responseFail)return{ok:false,status:responseFail,json:async()=>({detail:{message:'capacity or expired'}})};
 const data=url.endsWith('/keys')?key(n):url.endsWith('/encrypt')?{outcome:{code:'encrypted',message:'encrypted'},ciphertext_b64:'cipher-'+n,message:body.message,message_utf8_bytes:body.message.length,public_key_fingerprint:'f'.repeat(64)}:
 {outcome:{code,message:'result'},decrypted:code!=='decryption_failed',plaintext:code==='decrypted'?plaintext:null,plaintext_utf8_bytes:code==='decrypted'?plaintext.length:null,public_key_fingerprint:'f'.repeat(64)};
 return{ok:true,json:async()=>data};
}});
let source=fs.readFileSync('ui/rsa_lab.js','utf8').split('// Bind RSA1.')[0];
vm.runInContext(source+'\nglobalThis.test={createKey,cryptoAction,changed,reset,leave,keep,loadSaved,state:()=>owner};})();',context);
const api=context.test,tick=()=>new Promise(r=>setImmediate(r));const which=process.argv[1];
(async()=>{
 $('rsa-decrypt-key').value='A';await api.createKey('A');const original=api.state().keys.A;
 if(which==='replace_failure'){
  for(const status of [429,503,-1]){fail=status;await api.createKey('A');assert.equal(api.state().keys.A,original);assert(!calls.some(c=>c.method==='DELETE'));assert(!api.state().creating.busy);}
 }else if(which==='replace_success'){
  let release;hold=new Promise(r=>release=r);const p=api.createKey('A');await tick();assert.equal(api.state().keys.A,original);
  release();await p;assert.notEqual(api.state().keys.A,original);assert(calls.some(c=>c.method==='DELETE'&&c.url.endsWith(original.key_handle)));
 }else if(which==='reset_create'){
  let release;hold=new Promise(r=>release=r);const p=api.createKey('A');await tick();await api.reset();release();await p;
  assert.equal(api.state().keys.A,null);assert(!api.state().creating.busy);assert.equal(calls.filter(c=>c.method==='DELETE').length,2);
 }else if(which==='empty_success'){
  await api.cryptoAction('decrypt');assert.equal(api.state().decrypt.result.outcome.code,'decrypted');
  assert($('rsa-decrypt-result').className.includes('valid'));assert($('rsa-decrypt-result').textContent.includes('0 byte'));assert(!$('rsa-decrypt-result').hidden);
 }else if(which.startsWith('edit_')||which==='old_error'){
  const channel=which==='edit_decrypt'?'decrypt':'encrypt';let release,releaseNew;
  if(which==='old_error')fail=500;hold=new Promise(r=>release=r);const old=api.cryptoAction(channel);await tick();api.changed(channel);
  assert(!api.state()[channel].busy);hold=new Promise(r=>releaseNew=r);const newer=api.cryptoAction(channel);await tick();release();await old;
  assert(api.state()[channel].busy,'old completion must not unlock retry');assert.equal(api.state()[channel].result,null);
  releaseNew();await newer;assert(!api.state()[channel].busy);
 }else if(which==='reset_crypto'){
  let release;hold=new Promise(r=>release=r);const p=api.cryptoAction('decrypt');await tick();await api.reset();release();await p;assert.equal(api.state().decrypt.result,null);assert(!api.state().decrypt.busy);
 }else if(which==='transport'){
  fail=-1;await api.cryptoAction('decrypt');assert.equal(api.state().decrypt.result,null);assert(!api.state().decrypt.busy);assert(!$('rsa-error').hidden);
 }else if(which==='expired'){
  fail=404;await api.cryptoAction('decrypt');assert.equal(api.state().keys.A,null);assert.equal(api.state().decrypt.result,null);assert($('rsa-public-key').value);
 }else if(which==='non_utf8'){
  code='plaintext_not_utf8';await api.cryptoAction('decrypt');assert(!$('rsa-decrypt-result').className.includes('valid'));assert($('rsa-decrypt-result').textContent.includes('UTF-8'));
 }else if(which==='pagehide'){
  $('rsa-message').value='abc';api.leave();assert.equal($('rsa-byte-count').textContent,'0 / 190 byte UTF-8');assert.equal(api.state().keys.A,null);assert(!api.state().creating.busy);assert(!api.state().encrypt.busy);
 }else if(which==='retained'){
  $('rsa-message').value='original';await api.cryptoAction('encrypt');api.keep();const saved=api.state().saved;
  $('rsa-message').value='edited';api.changed('encrypt');await api.cryptoAction('encrypt');assert.equal(api.state().saved,saved);api.loadSaved();assert.equal($('rsa-ciphertext').value,saved.ciphertext_b64);
 }
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    r=subprocess.run(['node','-e',script,case],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr

def test_rsa_practice_initial_and_keyboard():
    script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,attrs:{},setAttribute(k,v){this.attrs[k]=v},focus(){}});return elements.get(id)};
const s=fs.readFileSync('ui/labs.js','utf8');const piece=s.slice(s.indexOf('const labLearning'),s.indexOf('async function compareHashes'));
const c=vm.createContext({$,chainLab:{},document:{}});vm.runInContext(piece+'\nsetupLabLearning();',c);
assert.equal($('rsa-oaep-practice').hidden,false,'RSA must start in Practice');
assert.equal($('rsa-oaep-theory').hidden,true);
$('rsa-oaep-tab-practice').onkeydown({key:'ArrowLeft',preventDefault(){}});
assert.equal($('rsa-oaep-theory').hidden,false);
$('rsa-oaep-tab-theory').onkeydown({key:'End',preventDefault(){}});
assert.equal($('rsa-oaep-practice').hidden,false);
"""
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr

def test_rsa_bootstrap_deadline_and_retry():
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const els=new Map(),$=id=>{if(!els.has(id))els.set(id,{value:'',textContent:'',hidden:false,disabled:false,className:''});return els.get(id)};
let resolveBootstrap,resolveKey;const timers=[],calls=[];
const ctx=vm.createContext({document:{getElementById:$},window:{addEventListener(){}},TextEncoder,AbortController,
setTimeout(fn,ms){timers.push({fn,ms});return timers.length},clearTimeout(){},
fetch:async(url,opt)=>{
 calls.push(url);
 if(url==='/api/session/bootstrap')return await new Promise(r=>resolveBootstrap=()=>r({ok:true,json:async()=>({})}));
 if(opt?.signal?.aborted)throw Error('aborted');
 if(opt?.method==='DELETE')return{ok:true,json:async()=>({cleared:true})};
 return await new Promise(r=>resolveKey=()=>r({ok:true,json:async()=>({key_handle:'latest',public_key_pem:'PEM',public_key_fingerprint:'f'.repeat(64),expires_in_seconds:900})}));
}});
vm.runInContext(fs.readFileSync('ui/session.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('ui/rsa_lab.js','utf8').split('// Bind RSA1.')[0]+'\nglobalThis.api={createKey,state:()=>owner};})();',ctx);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const old=ctx.api.createKey('A');await tick();timers.find(t=>t.ms===15000).fn();await tick();
 assert.equal(ctx.api.state().creating.busy,false,'deadline must release bootstrap-held loading');
 assert(!$('rsa-error').hidden);
 const retry=ctx.api.createKey('A');await tick();assert(ctx.api.state().creating.busy);
 resolveBootstrap();await tick();await old;
 assert(ctx.api.state().creating.busy,'late old completion cannot unlock retry');
 assert.equal(ctx.api.state().keys.A,null);
 resolveKey();await retry;assert.equal(ctx.api.state().keys.A.key_handle,'latest');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr

def test_rsa_keyboard_fingerprint_and_remaining_ttl():
    html=Path('ui/labs.html').read_text(encoding='utf-8')
    assert 'id="rsa-fingerprint-a"' in html and 'id="rsa-fingerprint-b"' in html
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let now=100000,timer;const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,hidden:false,className:''});return elements.get(id)};
const ctx=vm.createContext({document:{getElementById:$},window:{},Date:{now:()=>now},TextEncoder,AbortController,
setTimeout(fn,ms){if(ms===1000)timer=fn;return 0},clearTimeout(){},
fetch:async()=>({ok:true,json:async()=>({key_handle:'k',public_key_pem:'PEM',public_key_fingerprint:'a'.repeat(64),expires_in_seconds:900})})});
vm.runInContext(fs.readFileSync('ui/rsa_lab.js','utf8').split('// Bind RSA1.')[0]+'\nglobalThis.api={createKey,reset};})();',ctx);
(async()=>{
 await ctx.api.createKey('A');assert.equal($('rsa-fingerprint-a').value,'a'.repeat(64));
 assert($('rsa-key-a').textContent.includes('900s'));
 now+=10000;timer();assert($('rsa-key-a').textContent.includes('890s'));
 await ctx.api.reset();assert.equal($('rsa-fingerprint-a').value,'');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr


@pytest.mark.parametrize('case',['pending_sign_edit','pending_verify_edit','old_error','reset_sign','reset_verify','reset_create','replace_failure','replace_success','retained','empty','transport','expired','pagehide','independent','cleanup_failed','delete_public','delete_404'])
def test_pss_frontend_lifecycle(case):
    source=Path('ui/rsa_lab.js').read_text(encoding='utf-8')
    assert '// RSA2 owner.' in source, 'Independent PSS frontend is missing'
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const els=new Map(),$=id=>{if(!els.has(id))els.set(id,{value:'',textContent:'',hidden:false,disabled:false,className:''});return els.get(id)};
let hold,fail=0,sequence=0;const calls=[],handlers=[];
const key=n=>({key_handle:'key-'+n,public_key_pem:'PEM-'+n,public_key_fingerprint:'f'.repeat(64),expires_in_seconds:900});
const ctx=vm.createContext({document:{getElementById:$},window:{addEventListener:(name,fn)=>handlers.push(fn),confirm:()=>true},TextEncoder,AbortController,
setTimeout:(fn,ms)=>ms===1000?0:setTimeout(fn,ms),clearTimeout,
fetch:async(url,opt={})=>{
 const body=opt.body&&JSON.parse(opt.body),method=opt.method||'GET',n=++sequence,responseFail=fail;fail=0;calls.push({url,method,body});
 if(hold){const gate=hold;hold=null;await gate}
 if(responseFail===-1)throw Error('transport');
 if(responseFail)return{ok:false,status:responseFail,json:async()=>({detail:{message:'operation failure'}})};
 if(method==='DELETE')return{ok:true,json:async()=>({cleared:true})};
 const d=url.endsWith('/keys')?key(n):url.endsWith('/sign')?{message:body.message,message_utf8_bytes:new TextEncoder().encode(body.message).length,message_sha256:'a'.repeat(64),signature_b64:'signature-'+n,public_key_pem:'SIGNED-PEM',public_key_fingerprint:'f'.repeat(64),outcome:{code:'signed'},salt_bytes:32}:
 {message:body.message,message_utf8_bytes:body.message.length,message_sha256:'b'.repeat(64),public_key_fingerprint:'f'.repeat(64),valid:true,outcome:{code:'signature_valid'},salt_bytes:32};
 return{ok:true,json:async()=>d};
}});
const all=fs.readFileSync('ui/rsa_lab.js','utf8'),marker=all.indexOf('// RSA2 owner.');
vm.runInContext(all.slice(0,marker).replace('// Bind RSA1.','globalThis.oaep={createKey,state:()=>owner};\n// Bind RSA1.'),ctx);
vm.runInContext(all.slice(marker).split('// Bind RSA2.')[0]+'\nglobalThis.pss={createKey,removeKey,action,changed,reset,leave,keep,loadSaved,loadCurrent,state:()=>owner};})();',ctx);
const api=ctx.pss,tick=()=>new Promise(r=>setImmediate(r)),which=process.argv[1];
(async()=>{
 $('pss-sign-key').value='A';await api.createKey('A');const oldKey=api.state().keys.A;
 $('pss-message').value='original';await api.action('sign');api.loadCurrent();
 if(which.startsWith('pending_')||which==='old_error'){
  const name=which==='pending_verify_edit'?'verify':'sign';let oldRelease,newRelease;
  if(which==='old_error')fail=500;
  hold=new Promise(r=>oldRelease=r);const old=api.action(name);await tick();api.changed(name);
  assert(!api.state()[name].busy);hold=new Promise(r=>newRelease=r);const newer=api.action(name);await tick();
  oldRelease();await old;assert(api.state()[name].busy);assert.equal(api.state()[name].result,null);
  newRelease();await newer;assert(!api.state()[name].busy);assert(api.state()[name].result);
 }else if(which==='reset_sign'||which==='reset_verify'){
  const name=which==='reset_sign'?'sign':'verify';let release;hold=new Promise(r=>release=r);const p=api.action(name);await tick();await api.reset();release();await p;
  assert.equal(api.state()[name].result,null);assert(!api.state()[name].busy);assert.equal(api.state().keys.A,null);
 }else if(which==='reset_create'){
  let release;hold=new Promise(r=>release=r);const p=api.createKey('B');await tick();await api.reset();release();await p;
  assert.equal(api.state().keys.B,null);assert(!api.state().creating.busy);assert.equal(calls.filter(c=>c.method==='DELETE').length,2);
 }else if(which==='replace_failure'){
  for(const status of [429,503,-1]){fail=status;await api.createKey('A');assert.equal(api.state().keys.A,oldKey);assert(!api.state().creating.busy)}
  assert(!calls.some(c=>c.method==='DELETE'));
 }else if(which==='replace_success'){
  let release;hold=new Promise(r=>release=r);const p=api.createKey('A');await tick();assert.equal(api.state().keys.A,oldKey);
  release();await p;assert.notEqual(api.state().keys.A,oldKey);assert.equal(api.state().sign.result,null);
  assert(calls.some(c=>c.method==='DELETE'&&c.url.endsWith(oldKey.key_handle)));
 }else if(which==='retained'){
  api.keep();const saved=api.state().saved;$('pss-message').value='new';api.changed('sign');await api.action('sign');
  assert.equal(api.state().saved,saved);api.loadSaved();assert.equal($('pss-verify-message').value,'original');
  assert.equal($('pss-signature').value,saved.signature_b64);
  await api.createKey('B');assert.equal($('pss-verify-public-key').value,saved.public_key_pem);
 }else if(which==='empty'){
  $('pss-message').value='';api.changed('sign');await api.action('sign');api.loadCurrent();await api.action('verify');
  assert($('pss-sign-result').textContent.includes('0 byte'));assert($('pss-verify-result').className.includes('valid'));
 }else if(which==='transport'){
  fail=-1;await api.action('verify');assert.equal(api.state().verify.result,null);assert(!$('pss-error').hidden);
 }else if(which==='expired'){
  fail=404;await api.action('sign');assert.equal(api.state().keys.A,null);assert($('pss-verify-public-key').value);
  await api.action('verify');assert(api.state().verify.result.valid);
 }else if(which==='pagehide'){
  api.keep();api.leave();assert.equal(api.state().keys.A,null);assert.equal(api.state().saved,null);assert(!api.state().sign.busy);assert.equal($('pss-byte-count').textContent,'0 / 4096 byte UTF-8');
 }else if(which==='independent'){
  await ctx.oaep.createKey('A');const oaep=ctx.oaep.state().keys.A;await api.reset();assert.equal(ctx.oaep.state().keys.A,oaep);
  assert.equal(calls.find(c=>c.body?.purpose==='pss').body.purpose,'pss');
  assert(!calls.some(c=>c.method==='DELETE'&&c.url.endsWith(oaep.key_handle)));
 }else if(which==='delete_public'||which==='delete_404'){
  api.keep();const saved=api.state().saved,publicDraft=$('pss-verify-public-key').value;
  if(which==='delete_404')fail=404;
  await api.removeKey('A');assert.equal(api.state().keys.A,null);
  assert.equal(api.state().saved,saved);assert.equal($('pss-verify-public-key').value,publicDraft);
  await api.action('verify');assert(api.state().verify.result.valid);
 }else if(which==='cleanup_failed'){
  fail=-1;await api.reset();assert.equal(api.state().keys.A,null);assert(!$('pss-error').hidden);
 }
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    r=subprocess.run(['node','-e',script,case],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr

def test_pss_practice_default_and_keyboard():
    s=Path('ui/labs.html').read_text(encoding='utf-8')
    assert 'id="lab-rsa-pss"' in s
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),e=new Map();
const $=id=>{if(!e.has(id))e.set(id,{hidden:false,disabled:false,setAttribute(){},focus(){}});return e.get(id)};
const s=fs.readFileSync('ui/labs.js','utf8'),c=vm.createContext({$,chainLab:{}});
vm.runInContext(s.slice(s.indexOf('const labLearning'),s.indexOf('async function compareHashes'))+'\nsetupLabLearning();',c);
assert(!$('rsa-pss-practice').hidden);assert($('rsa-pss-theory').hidden);
$('rsa-pss-tab-practice').onkeydown({key:'ArrowLeft',preventDefault(){}});assert(!$('rsa-pss-theory').hidden);
$('rsa-pss-tab-theory').onkeydown({key:'End',preventDefault(){}});assert(!$('rsa-pss-practice').hidden);
"""
    r=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stdout+r.stderr
