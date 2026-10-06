"""The numeric decoration must never change the accessible result or API state."""
import subprocess
from pathlib import Path


def test_result_counter_updates_and_accessibility():
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
let reduced=false,animations=[];
class Element{
 constructor(){this.children=[];this.style={};this.attributes={};this.textContent='';}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=children;this.textContent='';}
 setAttribute(k,v){this.attributes[k]=v;}
 animate(frames,options){const a={frames,options,cancelled:false,cancel(){this.cancelled=true;}};animations.push(a);return a;}
}
const context=vm.createContext({document:{createElement:()=>new Element()},matchMedia:()=>({matches:reduced})});
vm.runInContext(fs.readFileSync('ui/result-counters.js','utf8'),context);
const render=(value,options={})=>{const e=new Element();context.TrustCounter.render(e,value,{key:'test',...options});return e;};
let e=render(9);assert.equal(e.children[0].textContent,'9');assert.equal(animations.length,0);
e=render(10);assert.equal(e.children[0].textContent,'10');assert.equal(e.children[1].attributes['aria-hidden'],'true');
assert.ok(animations.length>0);assert.ok(animations.every(a=>a.options.duration>=250&&a.options.duration<=400));
const n=animations.length;render(10);assert.equal(animations.length,n);
render(99);const old=animations.slice();e=render(100);assert.equal(e.children[0].textContent,'100');assert.ok(old.every(a=>a.cancelled));
e=render(2);assert.equal(e.children[0].textContent,'2');
e=render(47.65625,{decimals:2});assert.equal(e.children[0].textContent,'47,66');
reduced=true;const before=animations.length;e=render(50);assert.equal(e.children[0].textContent,'50');assert.equal(animations.length,before);
reduced=false;context.TrustCounter.clear('test');e=render(0);assert.equal(e.children[0].textContent,'0');assert.equal(animations.length,before);
render(null);e=render(7);assert.equal(animations.length,before);assert.equal(e.children[0].textContent,'7');
context.TrustCounter.clear('test');assert.ok(animations.every(a=>a.cancelled));
"""
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
