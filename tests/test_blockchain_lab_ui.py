"""Combined chain handlers in Node VM; not browser verification."""
from pathlib import Path
import subprocess

import pytest


def run_chain_case(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const testCase=process.argv[1],elements=new Map(),events={},calls=[];
class Element{
 constructor(tag='div'){this.tag=tag;this.value='';this.children=[];this.hidden=false;this.disabled=false;this.textContent='';this.dataset={};}
 set id(value){this._id=value;elements.set(value,this);}get id(){return this._id;}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}focus(){this.focused=true;}scrollIntoView(options){this.scrolled=options;}setAttribute(k,v){this[k]=v;}removeAttribute(k){delete this[k];}
 querySelectorAll(){return this.id==='chain-form'?['chain-data','chain-difficulty','chain-add','chain-version','chain-timestamp'].map(id=>document.getElementById(id)):[];}
 set innerHTML(v){throw Error('Unsafe HTML rendering');}
}
const document={documentElement:{dataset:{}},getElementById(id){if(!elements.has(id)){const e=new Element();e.id=id;}return elements.get(id);},createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
const record=(height,data,header={})=>({height,header:{version:1,timestamp:'2026-10-04T12:00:00Z',difficulty:height?2:1,merkle_root:'root-'+height,previous_hash:height?'hash-'+(height-1):'0'.repeat(64),nonce:27,...header},stored_hash:'hash-'+height,transaction:height?{payload:{lab_data:data},tx_id:'signed-'+height,signature:'original-signature'}:null});
const snapshot=chain=>({chain,blocks:chain.map(b=>({height:b.height,computed_hash:b.stored_hash,computed_transaction_hash:b.transaction?.tx_id||null,own_validation:{valid:true,checks:b.height?{transaction:{valid:true,reason:'Backend signature OK'}}:{}},link_valid:true,prefix_valid:true,prefix_reason:'Backend chain OK'})),validation:{valid:true,reason:'Backend chain OK'},max_blocks:12,mining:null,change:null});
let context,held,hold=['reset','pagehide'].includes(testCase),errorOnce=testCase==='error';
context=vm.createContext({document,Option:class extends Element{constructor(label,value){super();this.textContent=label;this.value=value;}},location:{hash:'#blocks'},window:{addEventListener:(k,f)=>events[k]=f},localStorage:{getItem:()=> 'dark',setItem(){}},navigator:{sendBeacon(){}},console,
 fetch:async(url,options)=>{
  assert.ok(url.startsWith('/api/labs/blockchain/'));const body=JSON.parse(options.body);calls.push({url,body});
  assert.equal(document.getElementById('chain-add').disabled,true);
  await vm.runInContext('chainLabAction("validate")',context); // Busy guard.
  if(hold){hold=false;await new Promise(r=>held=r);}
  if(errorOnce){errorOnce=false;return {ok:false,status:422,json:async()=>({detail:'Exact backend reason <safe>'})};}
  if(testCase==='rejection'&&url.endsWith('/add'))return {ok:false,status:409,json:async()=>({detail:'Actual mining rejection <safe>'})};
  let data=snapshot(structuredClone(body.chain||[record(0)]));
  if(url.endsWith('/add')){
   const block=record(data.chain.length,body.data,{version:body.version,timestamp:body.timestamp||'2026-10-04T12:00:00Z',difficulty:body.difficulty});
   if(testCase!=='incomplete')data=snapshot([...data.chain,block]);
   data.mining={completed:testCase!=='incomplete',attempts:28,seconds:.002345,reason:testCase==='incomplete'?'Actual limit <safe>':null};data.candidate=block;
  }
  if(url.endsWith('/edit')){
   const before=structuredClone(data.chain[body.height]);data.chain[body.height].transaction.payload.lab_data=body.data;
   data.validation={valid:false,reason:'Actual signed payload mismatch <safe>'};
   data.blocks[body.height].computed_transaction_hash='changed-tx';
   data.blocks[body.height].own_validation={valid:false,checks:{transaction:{valid:false,reason:data.validation.reason}}};
   data.blocks.slice(body.height).forEach(b=>b.prefix_valid=false);
   data.change={height:body.height,before,after:data.chain[body.height]};
  }
  if(url.endsWith('/recompute')){
   data.chain[body.height].stored_hash='recomputed-hash';data.chain[body.height].transaction.tx_id='changed-tx';
   data.blocks[body.height].computed_transaction_hash='changed-tx';data.blocks[body.height].own_validation.valid=false;
   data.validation={valid:false,reason:'Signature remains invalid'};data.blocks.slice(body.height).forEach(b=>b.prefix_valid=false);
   if(data.blocks[body.height+1])data.blocks[body.height+1].link_valid=false;
  }
  return {ok:true,json:async()=>data};
 }});
vm.runInContext(fs.readFileSync('ui/labs.js','utf8'),context);
const $=id=>document.getElementById(id),run=s=>vm.runInContext(s,context),text=e=>e.textContent+' '+e.children.map(text).join(' ');
const find=(e,p)=>p(e)?e:e.children.map(child=>find(child,p)).find(Boolean);
const card=height=>$('chain-cards').children.find(e=>e.dataset.height===String(height));
(async()=>{
 assert.equal($('lab-blocks').hidden,false);
 const pending=run('chainLab.initialization');
 if(['reset','pagehide'].includes(testCase)){
  await new Promise(r=>setImmediate(r));
  const old=run('chainLab'),other=run('signature'),comparison=run('comparison'),network=run('networkLab');
  if(testCase==='reset')await $('chain-reset').onclick();else events.pagehide();
  if(testCase==='reset')await run('chainLab.initialization');
  held();await pending;assert.notEqual(run('chainLab'),old);
  if(testCase==='reset'){
   assert.equal(run('chainLab.result.chain.length'),1);assert.equal(calls.length,2);
   assert.equal(run('signature'),other);assert.equal(run('comparison'),comparison);assert.equal(run('networkLab'),network);
  }else{assert.equal(run('chainLab.result'),null);assert.equal($('chain-result').hidden,true);assert.equal(calls.length,1);}
  return;
 }
 await pending;
 if(testCase==='error'){
  assert.equal($('chain-error').textContent,'Exact backend reason <safe>');assert.equal($('chain-init').hidden,false);
  await $('chain-init').onclick();assert.equal(run('chainLab.result.chain.length'),1);return;
 }
 assert.equal(calls.length,1);assert.ok(card(0));assert.equal($('chain-add').disabled,false);
 if(testCase==='add_reasons'){
  assert.equal($('chain-add-reason').hidden,true);assert.equal($('chain-add-reason').textContent,'');
  run('chainLab.result.validation.valid=false;showChainLab()');
  assert.equal($('chain-add').disabled,true);assert.equal($('chain-add-reason').hidden,false);
  assert.equal($('chain-add-reason').role,'status');
  assert.ok($('chain-add-reason').textContent.includes('Chuỗi đang không hợp lệ'));
  assert.ok($('chain-add-reason').textContent.includes('Đặt lại'));
  run('chainLab.result.validation.valid=true;showChainLab()');
  assert.equal($('chain-add').disabled,false);assert.equal($('chain-add-reason').hidden,true);
  assert.equal($('chain-add-reason').textContent,'');
  for(let n=0;n<12;n++)await run('chainLabAction("add")');
  assert.equal($('chain-add').disabled,true);assert.equal($('chain-add-reason').hidden,false);
  assert.ok($('chain-add-reason').textContent.includes('Đã đạt 12 khối'));
  assert.ok($('chain-add-reason').textContent.includes('Đặt lại'));
  $('chain-reset').onclick();await run('chainLab.initialization');
  assert.equal($('chain-add').disabled,false);assert.equal($('chain-add-reason').hidden,true);
  assert.equal($('chain-add-reason').textContent,'');return;
 }
 if(testCase==='difficulty_hint'){
  const normal=$('chain-difficulty-hint').textContent;
  assert.ok(normal.length);assert.ok(!normal.includes('thử thách'));
  for(const value of ['4','5','3','2']){
   $('chain-difficulty').value=value;$('chain-difficulty').onchange();
   const hint=$('chain-difficulty-hint').textContent;
   if(Number(value)>=4){assert.ok(hint.includes('thử thách'));assert.ok(hint.includes('khối chưa được thêm'));}
   else assert.equal(hint,normal);
  }
  assert.equal(calls.length,1);return;
 }
 assert.equal($('chain-previous').value,'hash-0');
 $('chain-data').value='  Free text <img src=x>  ';
 if(['inputs','headers'].includes(testCase)){
  $('chain-difficulty').value='5';$('chain-version').value='2';$('chain-timestamp').value='2026-10-04T12:00:00+07:00';
 }
 if(testCase==='reset_mining'){
  hold=true;const owner=run('chainLab'),pendingAdd=run('chainLabAction("add")');
  await new Promise(r=>setImmediate(r));$('chain-reset').onclick();await run('chainLab.initialization');held();await pendingAdd;
  assert.notEqual(run('chainLab'),owner);assert.equal(run('chainLab.result.chain.length'),1);assert.equal($('chain-add').disabled,false);return;
 }
 await run('chainLabAction("add")');
 if(testCase==='rejection'){
  assert.equal($('chain-error').textContent,'Actual mining rejection <safe>');assert.equal(run('chainLab.result.chain.length'),1);
  assert.ok(card(0));assert.equal($('chain-add').disabled,false);return;
 }
 if(testCase==='incomplete'){
  assert.equal(run('chainLab.result.chain.length'),1);assert.ok(text($('chain-summary')).includes('Actual limit <safe>'));
  assert.ok(text($('chain-summary')).includes('Nonce ứng viên'));
  assert.ok(!text($('chain-summary')).includes('Nonce tìm được'));
  const metrics=find($('chain-summary'),e=>e.className==='result-metrics');
  assert.equal(metrics.children[0].children[1].textContent,'27');
  assert.equal(metrics.children[1].children[1].textContent,'28');
  assert.equal(metrics.children[2].children[1].textContent,'0.002');
  assert.ok(text($('chain-evidence')).includes('"completed": false'));assert.equal($('chain-add').disabled,false);return;
 }
 assert.equal($('chain-previous').value,'hash-1');
 const metrics=find($('chain-summary'),e=>e.className==='result-metrics');
 assert.equal(metrics.children[0].children[1].textContent,'27');
 assert.equal(metrics.children[1].children[1].textContent,'28');
 if(testCase==='added_target'){
  assert.equal($('chain-show-added').hidden,false);assert.equal(run('chainLab.lastAdded'),1);
  assert.equal(card(1).scrolled,undefined);assert.equal(card(1).focused,undefined);
  $('chain-show-added').onclick();assert.ok(card(1).scrolled);assert.equal(card(1).focused,true);
  $('chain-data').value='Keep my draft';await run('chainLabAction("add")');
  assert.equal(run('chainLab.lastAdded'),2);assert.equal($('chain-data').value,'Keep my draft');
  $('chain-show-added').onclick();assert.ok(card(2).scrolled);assert.equal(calls.length,3);
  $('chain-reset').onclick();await run('chainLab.initialization');assert.equal($('chain-show-added').hidden,true);return;
 }
 const detail=find(card(1),e=>e.tag==='details');
 const serialized=find(detail,e=>e.tag==='pre'&&e.textContent.startsWith('{'));
 assert.deepEqual(JSON.parse(serialized.textContent).block,JSON.parse(run('JSON.stringify(chainLab.result.chain[1])')));
 assert.ok(text(card(1)).includes('Free text <img src=x>'));
 if(['inputs','headers'].includes(testCase)){
  assert.equal(calls[1].body.data,'  Free text <img src=x>  ');assert.equal(calls[1].body.version,2);
  assert.equal(calls[1].body.timestamp,'2026-10-04T12:00:00+07:00');assert.equal(calls[1].body.difficulty,5);
  assert.ok(!('previous_hash' in calls[1].body));return;
 }
 if(testCase==='cards'){
  assert.equal($('chain-cards').children.filter(e=>e.tag==='article').length,2);
  assert.equal($('chain-cards').children.filter(e=>e.className?.startsWith('chain-arrow')).length,1);
  assert.ok(text(card(1)).includes('Timestamp:'));assert.ok(text(card(1)).includes('Nonce:'));
  assert.equal(find(card(0),e=>e.tag==='button'),undefined);return;
 }
 if(testCase==='max_blocks'){
  for(let n=1;n<12;n++)await run('chainLabAction("add")');
  assert.equal($('chain-add').disabled,true);assert.equal($('chain-cards').children.filter(e=>e.tag==='article').length,13);return;
 }
 for(let n=0;n<2;n++)await run('chainLabAction("add")');
 const height=testCase==='edit_first'?1:2;
 find(card(height),e=>e.tag==='button').onclick();assert.equal(run('chainLab.selected'),height);
 assert.equal($('chain-edit').disabled,true);
 if(testCase==='edit_reasons'){
  assert.equal($('chain-edit-reason').hidden,false);
  assert.ok($('chain-edit-reason').textContent.includes('Hãy đổi dữ liệu'));
  assert.equal($('chain-recompute-reason').hidden,false);
  assert.ok($('chain-recompute-reason').textContent.includes('khớp'));
 }
 const input=$('chain-edited-data');input.value='<script>changed middle</script>';input.oninput();
 assert.equal($('chain-edited-data'),input); // Typing must not replace/focus-reset the editor.
 assert.equal($('chain-edit').disabled,false);
 if(testCase==='edit_reasons'){
  assert.equal($('chain-edit-reason').hidden,true);assert.equal($('chain-edit-reason').textContent,'');
  hold=true;const pendingEdit=run('chainLabAction("edit")');await new Promise(r=>setImmediate(r));
  assert.equal($('chain-add-reason').textContent,$('chain-status').textContent);
  assert.equal($('chain-edit-reason').textContent,$('chain-status').textContent);
  assert.equal($('chain-recompute-reason').textContent,$('chain-status').textContent);
  held();await pendingEdit;
  assert.equal($('chain-recompute').disabled,false);assert.equal($('chain-recompute-reason').hidden,true);return;
 }
 if(testCase==='draft'){assert.equal(run('chainLab.result.validation.valid'),true);assert.equal(calls.length,4);return;}
 await run('chainLabAction("edit")');assert.equal(calls.at(-1).body.height,height);
 assert.equal(run('chainLab.result.chain['+height+'].transaction.signature'),'original-signature');
 assert.ok(text(card(height)).includes('<script>changed middle</script>'));
 assert.ok(text($('chain-summary')).includes('Actual signed payload mismatch <safe>'));
 assert.equal($('chain-add').disabled,true);assert.equal($('chain-recompute').disabled,false);
 assert.equal(run('chainLab.result.blocks[3].own_validation.valid'),true);
 if(testCase==='transaction_hashes'){
  const visible=card(height).children.filter(e=>e.tag!=='details'&&e.tag!=='form');
  const recorded=visible.find(e=>e.textContent.startsWith('Hash giao dịch đã ghi:'));
  const computed=visible.find(e=>e.textContent.startsWith('Hash giao dịch tính lại:'));
  assert.ok(recorded);assert.ok(computed);
  assert.equal(recorded.title,'signed-'+height);assert.equal(computed.title,'changed-tx');
  assert.ok(visible.some(e=>e.textContent==='Nội dung đã đổi — hash giao dịch không khớp.'));
  assert.equal(run('chainLab.result.chain['+height+'].stored_hash'),run('chainLab.result.blocks['+height+'].computed_hash'));
  assert.ok(text(card(height)).includes('Hash đã ghi:'));assert.ok(text(card(height)).includes('Hash tính lại:'));
  assert.ok(!text(card(1)).includes('Nội dung đã đổi — hash giao dịch không khớp.'));return;
 }
 if(testCase==='prefix_warning'){
  assert.ok(card(height).className.includes('own-invalid'));assert.ok(!card(height).className.includes('prefix-broken'));
  assert.ok(card(3).className.includes('prefix-broken'));assert.ok(!card(3).className.includes('own-valid'));
  assert.ok(!card(1).className.includes('prefix-broken'));
  assert.ok(card(3).children.some(e=>e.textContent==='Block này còn nguyên, nhưng lịch sử trước nó không hợp lệ.'));
  assert.ok(text(card(3)).includes('✓ Liên kết với khối trước đạt'));
  assert.ok(text(card(3)).includes('Tiền tố chuỗi không hợp lệ'));return;
 }
 await run('chainLabAction("recompute")');assert.equal(run('chainLab.result.blocks['+(height+1)+'].link_valid'),false);
 if(testCase==='link_visualization'){
  const arrows=$('chain-cards').children.filter(e=>e.className?.startsWith('chain-arrow'));
  assert.equal(arrows.length,3);
  const broken=arrows.find(e=>e.dataset.to===String(height+1));
  assert.equal(broken.dataset.from,String(height));assert.ok(broken.className.includes('link-broken'));
  assert.ok(broken['aria-label'].includes('previous_hash'));assert.ok(broken['aria-label'].includes('liên kết gãy'));
  assert.ok(text(broken).includes('Link gãy'));assert.ok(broken.children[0].title.includes('recomputed-hash'));
  assert.ok(arrows[0].className.includes('link-valid'));
  assert.ok(card(height).className.includes('own-invalid'));assert.ok(card(height+1).className.includes('prefix-broken'));
  assert.ok(text(card(height+1)).includes('hash đã ghi của #'+height));return;
 }
 assert.equal($('chain-recompute').disabled,true);assert.equal($('chain-add').disabled,true);
 const other=run('signature');$('chain-reset').onclick();await run('chainLab.initialization');
 assert.equal(run('signature'),other);assert.equal(run('chainLab.result.chain.length'),1);
 assert.equal($('chain-cards').children.filter(e=>e.tag==='article').length,1);
 assert.ok(calls.every(c=>c.url.startsWith('/api/labs/blockchain/')));
})();
"""
    result = subprocess.run(['node', '-e', script, case], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_add_form_precedes_chain_without_duplicate_controls():
    from collections import Counter
    from html.parser import HTMLParser

    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self, tag, attrs):
            identifier = dict(attrs).get('id')
            if identifier:
                self.ids.append(identifier)

    parser = Controls()
    parser.feed(Path('ui/labs.html').read_text(encoding='utf-8'))
    counts = Counter(parser.ids)
    controls = ['chain-form', 'chain-data', 'chain-difficulty', 'chain-add',
                'chain-add-reason', 'chain-status', 'chain-show-added', 'chain-result']
    assert all(counts[name] == 1 for name in controls)
    assert [parser.ids.index(name) for name in controls] == sorted(parser.ids.index(name) for name in controls)


@pytest.mark.parametrize('case', ['flow', 'selection', 'inputs', 'error', 'incomplete',
                                  'reset', 'pagehide', 'rejection', 'reset_mining',
                                  'transaction_hashes', 'prefix_warning', 'add_reasons',
                                  'difficulty_hint', 'edit_reasons', 'link_visualization', 'added_target'])
def test_combined_chain_controls(case):
    run_chain_case(case)
