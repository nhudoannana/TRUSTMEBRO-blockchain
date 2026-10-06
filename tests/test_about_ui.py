"""Native carousel behavior; Node-VM checks are not browser verification."""
import json
import re
import subprocess
from pathlib import Path


def test_member_carousel_navigation_resize_and_reduced_motion():
    html = Path('landing.html').read_text(encoding='utf-8')
    script = re.search(r'<script id="member-carousel-script">(.*?)</script>', html, re.S)
    assert script, 'About carousel must enhance the static member list'
    result = subprocess.run(['node', '-e', r'''
const vm = require('vm'), assert = require('assert');
const events = {};
const track = {scrollLeft: 0, clientWidth: 880, scrollWidth: 2080,
  children: Array.from({length: 7}, (_, i) => ({offsetLeft: i * 300, offsetWidth: 280})),
  addEventListener: (name, handler) => events[name] = handler,
  scrollTo(options) {this.last = options; this.scrollLeft = Math.max(0, Math.min(options.left, this.scrollWidth - this.clientWidth)); events.scroll();}};
const previous = {}, next = {}, position = {}, controls = {hidden: true};
const elements = {'team-members': track, 'members-previous': previous,
  'members-next': next, 'members-position': position, 'members-controls': controls};
let resize, reduced = false;
vm.runInNewContext(SCRIPT, {
  document: {getElementById: id => elements[id]},
  matchMedia: () => ({matches: reduced}),
  ResizeObserver: class {constructor(fn) {resize = fn;} observe() {}},
});
assert.equal(controls.hidden, false);
assert.equal(previous.disabled, true); assert.equal(next.disabled, false);
assert.equal(position.textContent, '1–3 / 7');
next.onclick(); assert.equal(track.scrollLeft, 300); assert.equal(previous.disabled, false);
for (let i = 0; i < 10; i++) next.onclick();
assert.equal(next.disabled, true); assert.equal(position.textContent, '5–7 / 7');
track.clientWidth = 280; resize();
next.onclick(); next.onclick();
assert.equal(position.textContent, '7 / 7'); assert.equal(next.disabled, true);
reduced = true;
let prevented = false;
events.keydown({target: track, key: 'ArrowLeft', preventDefault() {prevented = true;}});
assert(prevented); assert.equal(track.last.behavior, 'auto');
assert.equal(position.textContent, '6 / 7');
events.keydown({target: {}, key: 'ArrowLeft', preventDefault() {throw Error('Nested control intercepted');}});
assert.equal(position.textContent, '6 / 7');
previous.onclick(); assert.equal(position.textContent, '5 / 7');
track.scrollLeft = 0; events.scroll(); assert.equal(previous.disabled, true);
track.clientWidth = 2080; resize(); assert.equal(next.disabled, true);
assert.equal(position.textContent, '1–7 / 7');
'''.replace('SCRIPT', json.dumps(script.group(1)))], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
