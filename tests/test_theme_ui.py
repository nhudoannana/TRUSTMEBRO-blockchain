"""Native theme controls retain their icons and never invoke simulation APIs."""
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


@pytest.mark.parametrize('page', ['landing', 'modes', 'labs', 'journey', 'explorer', 'attacks'])
def test_theme_control_preserves_icons_and_simulation_state(page):
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const page=process.argv[1],events={},store=new Map([['trustmebro-theme','light']]);
const button={children:['sun','moon'],attributes:{},setAttribute(k,v){this.attributes[k]=v;},
 set textContent(v){this.children=[];},addEventListener(k,f){this['on'+k]=f;}};
const owner={chain:['keep'],draft:'keep'},before=JSON.stringify(owner);
let source;
if(['landing','modes'].includes(page)){
 const html=fs.readFileSync(page==='landing'?'landing.html':'ui/modes.html','utf8');
 source=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>s.includes('const toggle=document.getElementById'));
}else{
 source=fs.readFileSync({labs:'ui/labs.js',journey:'ui/trustmebro.html',explorer:'ui/explorer.js',attacks:'ui/attacks.js'}[page],'utf8');
 if(page==='journey')source=source.slice(source.indexOf('(function initTheme()'),source.indexOf('})();',source.indexOf('(function initTheme()'))+5);
 else if(page==='attacks')source=source.slice(source.indexOf('function theme(value)'),source.indexOf("attackElement('attack-form').onsubmit"));
 else{
  const start=source.indexOf('function applyTheme(theme)'),end=source.indexOf("$('theme-toggle').onclick",start);
  source=source.slice(start,end)+source.slice(end,source.indexOf(';',end)+1)+'restoreTheme();';
 }
}
const element={hidden:false,focus(){}},document={title:'',documentElement:{dataset:{theme:'light'}},getElementById:id=>id.includes('theme')?button:element};
const context=vm.createContext({document,$:()=>button,attackElement:()=>button,owner,location:{hash:''},
 localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},window:{addEventListener:(k,f)=>events[k]=f},fetch(){throw Error('Theme must not call APIs');}});
vm.runInContext(source,context);
assert.equal(document.documentElement.dataset.theme,'light');assert.equal(button.attributes['aria-pressed'],'true');
assert.equal(button.children.length,2);button.onclick();
assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(button.attributes['aria-pressed'],'false');
assert.equal(store.get('trustmebro-theme'),'dark');assert.equal(button.children.length,2);
button.onclick();assert.equal(store.get('trustmebro-theme'),'light');assert.equal(button.children.length,2);
assert.equal(JSON.stringify(owner),before);
"""
    result = subprocess.run(['node', '-e', script, page], capture_output=True,
                            text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_theme_controls_and_lab_order():
    class Navigation(HTMLParser):
        def __init__(self):
            super().__init__()
            self.labs = []
            self.toggle = None
            self.links = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'button' and attrs.get('id') in {'theme-toggle', 'attack-theme'}:
                self.toggle = attrs
            if tag == 'a':
                self.links.append(attrs.get('href', ''))
                if 'data-lab' in attrs:
                    self.labs.append(attrs['href'])
                elif (attrs.get('class') == 'mode-card' and attrs.get('href', '').startswith('/ui/labs.html#')) or attrs.get('href') == '/ui/attacks.html':
                    self.labs.append(attrs['href'])

    for filename in ['landing.html', 'ui/modes.html', 'ui/labs.html', 'ui/trustmebro.html',
                     'ui/explorer.html', 'ui/attacks.html']:
        parser = Navigation()
        parser.feed(Path(filename).read_text(encoding='utf-8'))
        assert parser.toggle['type'] == 'button'
        assert parser.toggle['aria-label'] == 'Chế độ sáng'
        assert 'aria-pressed' in parser.toggle
        assert not any(re.search(r'/(?:api/)?(?:docs|redoc|openapi\.json)(?:$|[?#])', link) for link in parser.links)
        if filename in {'ui/modes.html', 'ui/labs.html'}:
            expected = ['sha', 'signatures', 'merkle', 'blocks', 'consensus', 'network', 'tamper', 'attacks']
            actual = [link.split('#')[-1] if '#' in link else 'attacks' for link in parser.labs]
            assert actual == expected
