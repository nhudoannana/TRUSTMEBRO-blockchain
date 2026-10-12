"""Quiz state tests run the production owner in Node VM, not a browser."""
import subprocess
from pathlib import Path
import pytest

HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let now=1000,seq=0,timers=new Map(),notices=[],ls=new Map(),ss=new Map();
const storage=map=>({getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)});
const localStorage=storage(ls),sessionStorage=storage(ss);
const nodes=new Map();
const document={documentElement:{dataset:{}},getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,focus(){},setAttribute(){},replaceChildren(){},append(){}});return nodes.get(id);}};
const context=vm.createContext({console,Blob,document,localStorage,sessionStorage,window:{addEventListener(){}},
 Date:class extends Date {static now(){return now;}},crypto:{randomUUID:()=>String(++seq)},
 setInterval:f=>{const id=++seq;timers.set(id,f);return id;},clearInterval:id=>timers.delete(id),
 confirm:()=>true,fetch:()=>{throw Error('No simulation API allowed');},setTimeout,clearTimeout});
let source=fs.readFileSync('ui/quiz.js','utf8');
source=source.replace('// Browser wiring',`render=()=>{};refreshSummary=()=>{};updateNavigation=()=>{};fillTopics=()=>{};notice=(m)=>notices.push(m);
globalThis.q={validateBank,selectQuestions,scoreAttempt,validateProgress,validateAttempt,
 startAttempt,selectOption,checkPracticeAnswer,finishAttempt,resetQuiz,restoreAttempt,loadBank,
 expire, tick, leaveAttempt, resumeAttempt, updateFilter,
 configure(b){bank=validateBank(b);byId=new Map(bank.questions.map(q=>[q.id,q]));progress=freshProgress();},
 get attempt(){return attempt;},get progress(){return progress;},get revision(){return revision;},
 setFetch(f){fetch=f;},setRenderer(f){render=f;},get loading(){return loading;},
 keys:{PROGRESS_KEY,ATTEMPT_KEY}};
return;
// Browser wiring`);
context.notices=notices;vm.runInContext(source,context);
const q=context.q,bank=vm.runInContext('JSON.parse(raw)',Object.assign(context,{raw:fs.readFileSync('ui/quiz_questions.json','utf8')}));
q.configure(bank);
const copy=o=>vm.runInContext('JSON.parse(raw)',Object.assign(context,{raw:JSON.stringify(o)}));
const bad=f=>assert.throws(f);
"""

def run_node(script):
    r=subprocess.run(['node','-e',HARNESS+script],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert r.returncode==0,r.stdout+r.stderr

def test_bank_quota_and_scoring_boundaries():
    run_node(r"""
const ids=q.selectQuestions('exam',null,null);assert.equal(ids.length,20);assert.equal(new Set(ids).size,20);
const counts={};for(const id of ids){const t=bank.questions.find(r=>r.id===id).topicId;counts[t]=(counts[t]??0)+1;}
assert.deepEqual(counts,{...Object.fromEntries(Object.keys(counts).map(k=>[k,{sha:4,ecdsa:2,blocks:2,merkle:4,fork:3,oaep:2,pss:3}[k]]))});
bad(()=>q.selectQuestions('practice','pss','Khó'));
for(const field of ['prompt','explanation']){const b=copy(bank);b.questions[0][field]='';bad(()=>q.validateBank(b));}
const b=copy(bank);b.questions.push(copy(b.questions[0]));bad(()=>q.validateBank(b));
const unreviewed=copy(bank);unreviewed.questions[0].reviewStatus='pending';bad(()=>q.validateBank(unreviewed));
const unsafe=copy(bank);unsafe.questions[0].labLinks[0].href='javascript:alert(1)';bad(()=>q.validateBank(unsafe));
const score=(n,correct)=>{const ids=bank.questions.slice(0,n).map(r=>r.id),answers={};
for(const r of bank.questions.slice(0,correct))answers[r.id]=r.correctOptionId;
return q.scoreAttempt({questionIds:ids,answers});};
assert.equal(score(20,14).passed,true);assert.equal(score(20,13).passed,false);
assert.equal(score(23,16).percent,70);assert.equal(score(23,16).passed,false);
assert.equal(score(20,0).unanswered,20);
""")

def test_explicit_practice_and_exam_no_early_credit():
    run_node(r"""
q.startAttempt('practice','pss',null,false);const id=q.attempt.questionIds[0];
q.selectOption('a');assert.equal(Object.keys(q.progress.outcomes).length,0);
q.checkPracticeAnswer();assert.equal(q.attempt.confirmedIds.length,1);const chosen=q.attempt.answers[id];
q.selectOption(chosen==='a'?'b':'a');assert.equal(q.attempt.answers[id],chosen);
q.startAttempt('exam',null,null,false);q.selectOption('b');assert.equal(q.attempt.confirmedIds.length,0);
const previous=ls.get(q.keys.PROGRESS_KEY);q.selectOption(null);assert.equal(Object.keys(q.attempt.answers).length,0);
assert.equal(ls.get(q.keys.PROGRESS_KEY),previous);q.selectOption('a');q.finishAttempt('submitted');
const snapshot=ls.get(q.keys.PROGRESS_KEY);q.finishAttempt('timeout');q.tick();assert.equal(ls.get(q.keys.PROGRESS_KEY),snapshot);
assert.equal(q.attempt.status,'finished');assert.equal(timers.size,0);
""")

def test_storage_validation_reset_and_absolute_reload():
    run_node(r"""
ls.set('trustmebro-theme','light');ls.set('qzp','legacy');ss.set('lab-state','keep');
q.startAttempt('exam',null,null,true);q.selectOption('c');const before=copy(q.attempt);
now+=8000;q.restoreAttempt();assert.deepEqual(copy(q.attempt),before);assert.equal(q.attempt.deadlineMs,1201000);
for(const value of [null,[],{schemaVersion:1,bankVersion:bank.bankVersion,outcomes:{evil:{}}}]){
bad(()=>q.validateProgress(value));}
let malformed=copy(q.attempt);malformed.questionIds.push(malformed.questionIds[0]);bad(()=>q.validateAttempt(malformed));
malformed=copy(q.attempt);malformed.answers[malformed.questionIds[0]]='evil';bad(()=>q.validateAttempt(malformed));
malformed=copy(q.attempt);malformed.index=999;bad(()=>q.validateAttempt(malformed));
malformed=copy(q.attempt);malformed.deadlineMs=0;bad(()=>q.validateAttempt(malformed));
ss.set(q.keys.ATTEMPT_KEY,'{');q.restoreAttempt();assert.equal(q.attempt,null);assert(notices.length);
q.startAttempt('exam',null,null,true);const callback=[...timers.values()][0];q.resetQuiz();
assert.equal(q.attempt,null);assert.equal(timers.size,0);callback();assert.equal(q.attempt,null);
assert.equal(ls.get('trustmebro-theme'),'light');assert.equal(ls.get('qzp'),'legacy');assert.equal(ss.get('lab-state'),'keep');
assert.equal(ls.has(q.keys.PROGRESS_KEY),false);assert.equal(ss.has(q.keys.ATTEMPT_KEY),false);
""")

def test_timeout_home_and_finished_restore_idempotent():
    run_node(r"""
q.startAttempt('exam',null,null,true);q.selectOption('a');q.leaveAttempt();
const deadline=q.attempt.deadlineMs;now=deadline;q.resumeAttempt();
assert.equal(q.attempt.status,'finished');assert.equal(q.attempt.finishReason,'timeout');
const progress=ls.get(q.keys.PROGRESS_KEY);q.restoreAttempt();assert.equal(q.attempt.status,'finished');
assert.equal(ls.get(q.keys.PROGRESS_KEY),progress);assert.equal(timers.size,0);
""")

def test_storage_denial_keeps_learning_and_other_tab_progress():
    run_node(r"""
q.startAttempt('practice','oaep',null,false);const id=q.attempt.questionIds[0];
const other=bank.questions.find(r=>r.id!==id);ls.set(q.keys.PROGRESS_KEY,JSON.stringify({
 schemaVersion:1,bankVersion:bank.bankVersion,outcomes:{[other.id]:{selectedOptionId:other.correctOptionId,correct:true,answeredAtMs:1000}}}));
q.selectOption('a');q.checkPracticeAnswer();assert(q.progress.outcomes[other.id]);
localStorage.setItem=()=>{throw Error('quota');};sessionStorage.setItem=()=>{throw Error('quota');};
q.startAttempt('exam',null,null,false);q.selectOption('a');q.finishAttempt('submitted');
assert.equal(q.attempt.status,'finished');assert(notices.some(m=>m.includes('lưu')));
""")

def test_pending_bank_reset_retry_and_late_response():
    run_node(r"""
(async()=>{
let pending=[];q.setFetch(()=>new Promise(resolve=>pending.push(resolve)));
const first=q.loadBank();assert.equal(q.loading,true);q.resetQuiz();assert.equal(q.loading,false);
const second=q.loadBank();pending[0]({ok:true,json:async()=>bank});await first;
assert.equal(q.loading,true);pending[1]({ok:true,json:async()=>bank});await second;
assert.equal(q.loading,false);assert.equal(q.attempt,null);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

def test_quiz_semantics_and_navigation_contract():
    from html.parser import HTMLParser
    class Page(HTMLParser):
        def __init__(self): super().__init__(); self.ids={}; self.links=[]
        def handle_starttag(self,t,a):
            a=dict(a)
            if 'id' in a: assert a['id'] not in self.ids; self.ids[a['id']]=(t,a)
            if t=='a': self.links.append(a)
    html=Path('ui/quiz.html').read_text(encoding='utf-8');p=Page();p.feed(html)
    for id in ['objectives','knowledge','prediction','practice','results','limits','theme-toggle','question','quiz-notice']:
        assert id in p.ids
    assert p.ids['theme-toggle'][1]['type']=='button'
    assert 'aria-live="polite"' in html and '<fieldset' in html and '<legend' in html
    for name in ['modes','labs']:
        parser=Page();parser.feed(Path(f'ui/{name}.html').read_text(encoding='utf-8'))
        links=[a for a in parser.links if a.get('href')=='/ui/quiz.html']
        assert len(links)>=1 and 'data-lab' not in links[0]
    js=Path('ui/quiz.js').read_text(encoding='utf-8')
    assert 'localStorage.clear' not in js and '/api/' not in js

def test_reset_releases_pending_load_controls_and_retry():
    run_node(r"""
(async()=>{
let pending=[];q.setFetch(()=>new Promise(resolve=>pending.push(resolve)));
const first=q.loadBank();assert.equal(nodes.get('retry-bank').disabled,true);
q.resetQuiz();assert.equal(nodes.get('retry-bank').disabled,false);
assert.equal(nodes.get('start-exam').disabled,false);
const second=q.loadBank();pending[0]({ok:true,json:async()=>bank});await first;
assert.equal(nodes.get('retry-bank').disabled,true);
pending[1]({ok:true,json:async()=>bank});await second;
assert.equal(nodes.get('retry-bank').disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

def test_failed_filter_does_not_destroy_or_stop_existing_attempt():
    run_node(r"""
q.startAttempt('exam',null,null,true);const before=copy(q.attempt),rev=q.revision;
bad(()=>q.startAttempt('practice','pss','Khó',false));
assert.deepEqual(copy(q.attempt),before);assert.equal(q.revision,rev);assert.equal(timers.size,1);
""")

def test_failed_bank_retry_keeps_deadline_running():
    run_node(r"""
(async()=>{
q.startAttempt('exam',null,null,true);
q.setFetch(async()=>{throw Error('offline');});await q.loadBank();
now=q.attempt.deadlineMs;for(const callback of [...timers.values()])callback();
assert.equal(q.attempt.status,'finished');assert.equal(q.attempt.finishReason,'timeout');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")

def test_storage_property_access_denial_is_memory_only():
    run_node(r"""
q.startAttempt('practice','oaep',null,false);
Object.defineProperty(context,'sessionStorage',{get(){throw Error('SecurityError');}});
Object.defineProperty(context,'localStorage',{get(){throw Error('SecurityError');}});
q.selectOption('a');q.checkPracticeAnswer();q.finishAttempt('submitted');
assert.equal(q.attempt.status,'finished');assert(notices.some(m=>m.includes('lưu')));
q.restoreAttempt();q.resetQuiz();assert.equal(q.attempt,null);
""")

def test_empty_filter_and_feedback_recovery():
    run_node(r"""
document.getElementById('topic').value='pss';document.getElementById('level').value='Khó';q.updateFilter();
assert.equal(nodes.get('start-practice').disabled,true);
document.getElementById('level').value='';q.updateFilter();assert.equal(nodes.get('start-practice').disabled,false);
""")
    html=Path('ui/quiz.html').read_text(encoding='utf-8')
    assert 'id="question-feedback" class="feedback" tabindex="-1"' in html
    assert 'id="filter-notice"' in html
