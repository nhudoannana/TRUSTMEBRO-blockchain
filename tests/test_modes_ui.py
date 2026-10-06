"""Static mode navigation/theme behavior in Node VM, separate from browser checks."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('case', ['choose', 'labs', 'history'])
def test_mode_view_and_theme_preference(case):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('ui/modes.html','utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)];
const elements=new Map(),events={},store=new Map([['trustmebro-theme','light']]);
const document={title:'',documentElement:{dataset:{}},getElementById(id){
 if(!elements.has(id))elements.set(id,{hidden:false,focused:false,attributes:{},focus(){this.focused=true;},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,f){this[k]=f;}});
 return elements.get(id);
}};
const location={hash:process.argv[1]==='labs'?'#labs':''};
const context=vm.createContext({document,location,localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},window:{addEventListener:(k,f)=>events[k]=f},fetch(){throw Error('Entry must not mutate backend state');}});
for(const s of scripts)vm.runInContext(s[1],context);
assert.equal(document.documentElement.dataset.theme,'light');
assert.equal(document.getElementById('theme-toggle').attributes['aria-pressed'],'true');
document.getElementById('theme-toggle').click();
assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(store.get('trustmebro-theme'),'dark');
assert.equal(document.getElementById('mode-choice').hidden,location.hash==='#labs');
assert.equal(document.getElementById('labs-placeholder').hidden,location.hash!=='#labs');
if(process.argv[1]==='history'){
 location.hash='#labs';events.hashchange();
 assert.equal(document.getElementById('mode-choice').hidden,true);assert.equal(document.getElementById('labs-title').focused,true);
 location.hash='';events.hashchange();
 assert.equal(document.getElementById('labs-placeholder').hidden,true);assert.equal(document.getElementById('mode-title').focused,true);
 store.set('trustmebro-theme','light');events.pageshow(); // restore saved preference after browser Back
 assert.equal(document.documentElement.dataset.theme,'light');
}
"""
    result = subprocess.run(['node', '-e', script, case],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
