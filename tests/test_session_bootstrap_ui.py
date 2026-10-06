"""Execute page handlers with delayed real fetch boundaries in Node VM."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('page', ['trustmebro', 'explorer', 'labs', 'attacks'])
@pytest.mark.parametrize('case', ['queue', 'capacity_retry'])
def test_page_bootstrap_orders_requests_and_allows_retry(page, case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const [page,mode]=process.argv.slice(1),elements=new Map(),events={},calls=[];let release,bootstrapCount=0;
class E{
 constructor(){this.value='';this.textContent='';this.innerHTML='';this.children=[];this.dataset={};this.style={};this.hidden=true;}
 append(...v){this.children.push(...v)}prepend(...v){this.children.unshift(...v)}replaceChildren(...v){this.children=v}
 setAttribute(k,v){this[k]=v}removeAttribute(k){delete this[k]}querySelectorAll(){return []}focus(){}add(child){this.children.push(child)}
}
const body=new E(),document={body,documentElement:{dataset:{}},querySelector:()=>null,querySelectorAll:()=>[],
 getElementById(id){if(!elements.has(id))elements.set(id,new E());return elements.get(id)},createElement:()=>new E()};
const win={location:{hash:'#sha',search:''},addEventListener:(k,f)=>events[k]=f,dispatchEvent:e=>events[e.type]?.(e)};
const context=vm.createContext({document,window:win,location:win.location,console,AbortController,URLSearchParams,
 setTimeout,clearTimeout,TextEncoder,Option:class extends E{},Event:class{constructor(type){this.type=type}},
 localStorage:{getItem(){},setItem(){}},sessionStorage:{getItem(){},removeItem(){}},
 fetch:async(url,options)=>{
  calls.push(String(url));
  if(url==='/api/session/bootstrap'){
   bootstrapCount++;if(bootstrapCount===1)await new Promise(r=>release=r);
   return {ok:mode!=='capacity_retry'||bootstrapCount>1,status:503,json:async()=>mode==='capacity_retry'&&bootstrapCount===1
    ?{detail:{code:'session_capacity',message:'Capacity denied'}}:{context_generation:'context',reset_count:0}};
  }
  return {ok:true,json:async()=>({})};
 }});
const html=fs.readFileSync('ui/'+page+'.html','utf8');
for(const match of html.matchAll(/<script[^>]*src="([^"]+)"[^>]*>/g)){
 if(match[1]==='/ui/session.js')vm.runInContext(fs.readFileSync('ui/session.js','utf8'),context);
}
const source=page==='trustmebro'?[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1]:fs.readFileSync('ui/'+page+'.js','utf8');
vm.runInContext(page==='trustmebro'?source.slice(0,source.indexOf('(function initTheme()')):
 page==='explorer'?source.slice(0,source.indexOf('(function setupExplorer()')):source,context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 assert.equal(calls.length,0,'Reading page/theory must not bootstrap');
 let expression;
 if(page==='trustmebro')expression='journeyFetch("/api/wallets")';
 else if(page==='explorer'){document.getElementById('explorer-node').value='Node-1';expression='loadExplorerBlocks()';}
 else if(page==='labs')expression='labPost("/signatures/keys")';
 else {document.getElementById('attack-scenario').value='replay';run('attackControls()');expression='runAttack({preventDefault(){}})';}
 const job=run(expression),parallel=run('fetch("/api/network")').catch(e=>e);
 job.catch(()=>{});await new Promise(r=>setImmediate(r));
 assert.deepEqual(calls,['/api/session/bootstrap'],'No private API until cookie response finishes');
 release();await Promise.allSettled([job,parallel]);
 if(mode==='queue'){
  assert.equal(bootstrapCount,1);assert.ok(calls.includes('/api/network'));
  assert.equal(body.children.length,0);
 }else{
  assert.deepEqual(calls,['/api/session/bootstrap']);
  const notice=body.children[0];assert.ok(notice && !notice.hidden);
  const text=e=>e.textContent+' '+e.children.map(text).join(' ');
  assert.match(text(notice),/phiên|Phiên/);const button=notice.children.find(e=>e.type==='button');assert.ok(button);
  await button.onclick();assert.equal(bootstrapCount,2);assert.equal(notice.hidden,true);
  await run('fetch("/api/network")');assert.equal(bootstrapCount,2);assert.equal(calls.at(-1),'/api/network');
 }
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', script, page, case], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
