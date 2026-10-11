"""Meaningful checks for the newly integrated pedagogical UI behavior and navigation."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import pytest


class LabNavParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.groups = []
        self.current_group = None
        self.current_num = ''
        self.current_title = ''
        self.current_items = []
        self.in_num = False
        self.in_title = False
        self.in_items = False
        self.links = []
        self.labs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and attrs.get('class') == 'lab-nav-group':
            self.current_group = {}
            self.current_num = ''
            self.current_title = ''
            self.current_items = []
        elif tag == 'span' and attrs.get('class') == 'lab-nav-group-num':
            self.in_num = True
        elif tag == 'span' and attrs.get('class') == 'lab-nav-group-title':
            self.in_title = True
        elif tag == 'div' and attrs.get('class') == 'lab-nav-group-items':
            self.in_items = True
        elif tag == 'a':
            self.links.append(attrs.get('href', ''))
            if 'data-lab' in attrs:
                self.labs.append(attrs['href'])
                if self.in_items:
                    self.current_items.append(attrs['href'])
            elif attrs.get('href') == '/ui/attacks.html':
                self.labs.append(attrs['href'])
                if self.in_items:
                    self.current_items.append(attrs['href'])

    def handle_data(self, data):
        if self.in_num:
            self.current_num += data.strip()
        elif self.in_title:
            self.current_title += data.strip()

    def handle_endtag(self, tag):
        if tag == 'span':
            self.in_num = False
            self.in_title = False
        elif tag == 'div':
            if self.in_items:
                self.in_items = False
            elif self.current_group is not None:
                self.groups.append({
                    'num': self.current_num,
                    'title': self.current_title,
                    'items': self.current_items,
                })
                self.current_group = None


def test_pedagogical_lab_navigation_groups_and_order():
    html_content = Path('ui/labs.html').read_text(encoding='utf-8')
    parser = LabNavParser()
    parser.feed(html_content)

    # 1. Exactly 4 groups
    assert len(parser.groups) == 4, f"Expected 4 groups, got {len(parser.groups)}"
    assert parser.groups[0]['num'] == '01'
    assert 'Mật mã' in parser.groups[0]['title']
    assert parser.groups[0]['items'] == ['#sha', '#rsa-oaep', '#rsa-pss', '#signatures', '#merkle']

    assert parser.groups[1]['num'] == '02'
    assert 'Giao dịch' in parser.groups[1]['title']
    assert parser.groups[1]['items'] == ['#blocks']

    assert parser.groups[2]['num'] == '03'
    assert 'Đồng thuận' in parser.groups[2]['title']
    assert parser.groups[2]['items'] == ['#consensus', '#network', '#fork']

    assert parser.groups[3]['num'] == '04'
    assert 'Tấn công' in parser.groups[3]['title']
    assert parser.groups[3]['items'] == ['#tamper', '/ui/attacks.html']

    # 2. Sequential 11 lab entries in exact required DOM order
    expected_order = ['sha', 'rsa-oaep', 'rsa-pss', 'signatures', 'merkle', 'blocks', 'consensus', 'network', 'fork', 'tamper', 'attacks']
    actual_order = [link.split('#')[-1] if '#' in link else 'attacks' for link in parser.labs]
    assert actual_order == expected_order

    # 3. Header utilities includes Quiz link
    assert '/ui/quiz.html' in parser.links


def test_pedagogical_blocks_markup_and_preservation():
    html = Path('ui/labs.html').read_text(encoding='utf-8')
    
    # 3Blue1Brown educational lessons
    assert '3Blue1Brown' in html
    assert 'Proof of Work' in html
    assert 'Con số Nonce bí ẩn' in html
    assert 'Liên kết Previous Hash' in html
    assert 'Hiệu ứng sụp đổ dây chuyền khi sửa dữ liệu' in html
    assert 'Kịch bản Alice' in html

    # Pedagogy card & hypothesis test box in blocks lab
    assert 'class="pedagogy-card"' in html
    assert 'id="blocks-hypothesis-box"' in html
    assert 'name="blocks-hypo"' in html
    assert 'value="broken"' in html
    assert 'id="blocks-hypo-feedback"' in html

    # Presets in blocks lab
    assert 'id="chain-preset-alice"' in html
    assert 'id="chain-preset-smart"' in html
    assert 'id="chain-preset-hash"' in html

    # Preservation of all required chain form controls
    required_ids = [
        'chain-form', 'chain-data', 'chain-difficulty', 'chain-previous',
        'chain-version', 'chain-timestamp', 'chain-add', 'chain-add-reason',
        'chain-status', 'chain-error', 'chain-add-feedback', 'chain-show-added',
        'chain-example', 'chain-result', 'chain-summary', 'chain-cards', 'chain-evidence'
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html, f"Missing required element: {element_id}"


def test_pedagogical_merkle_flow_tracker_and_lifecycle_preservation():
    html = Path('ui/labs.html').read_text(encoding='utf-8')

    # Merkle Flow Tracker
    assert 'class="merkle-flow-tracker"' in html
    assert '1. Dữ liệu đầu vào' in html
    assert '2. Dựng cây Merkle' in html
    assert '3. Merkle Proof' in html
    assert '4. Xác minh độc lập' in html

    # Accepted Merkle verification lifecycle preserved
    merkle_lifecycle_ids = [
        'merkle-keep-a', 'merkle-saved', 'merkle-verification',
        'merkle-verify-form', 'merkle-verify-text', 'merkle-expected-root',
        'merkle-proof-rows', 'merkle-proof-add', 'merkle-verify-submit',
        'merkle-verify-result', 'merkle-verify-trace'
    ]
    for element_id in merkle_lifecycle_ids:
        assert f'id="{element_id}"' in html, f"Missing Merkle lifecycle element: {element_id}"


def test_pedagogical_blocks_hypothesis_and_presets_behavior_in_node():
    script = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const elements = new Map();
class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.value = ''; this.textContent = ''; this.hidden = false;
    this.disabled = false; this.children = []; this.className = ''; this.checked = false;
    this.dataset = {};
  }
  set id(v) { this._id = v; elements.set(v, this); } get id() { return this._id; }
  append(...c) { this.children.push(...c); }
  replaceChildren(...c) { this.children = c; }
  setAttribute(k, v) { this[k] = v; }
  focus() {}
  querySelectorAll(sel) {
    if (sel === 'input[name="blocks-hypo"]') {
      return ['blocks-hypo-1', 'blocks-hypo-2', 'blocks-hypo-3'].map(id => document.getElementById(id));
    }
    return [];
  }
}
const document = {
  documentElement: { dataset: {} },
  getElementById(id) { if (!elements.has(id)) { const e = new Element(); e.id = id; } return elements.get(id); },
  createElement: tag => new Element(tag),
  querySelectorAll: sel => {
    if (sel === 'input[name="blocks-hypo"]') {
      return ['blocks-hypo-1', 'blocks-hypo-2', 'blocks-hypo-3'].map(id => document.getElementById(id));
    }
    return [];
  }
};
const context = vm.createContext({
  document, Option: class extends Element {},
  location: { hash: '#blocks' }, window: { addEventListener: () => {}, confirm: () => true },
  localStorage: { getItem: () => 'dark', setItem() {} }, console,
  fetch: async () => ({ ok: true, json: async () => ({ chain: [], blocks: [], validation: { valid: true } }) })
});
vm.runInContext(fs.readFileSync('ui/labs.js', 'utf8'), context);

// 1. Test Hypothesis feedback
const hypoRadioBroken = document.getElementById('blocks-hypo-broken');
hypoRadioBroken.value = 'broken';
hypoRadioBroken.checked = true;
// Trigger hypothesis change
const radios = document.querySelectorAll('input[name="blocks-hypo"]');
assert.equal(radios.length, 3);
radios[0].value = 'broken';
radios[0].onchange();
const feedback = document.getElementById('blocks-hypo-feedback');
assert.ok(feedback.className.includes('correct'), 'Feedback must be correct for broken link');
assert.ok(feedback.textContent.includes('Chính xác'), 'Feedback text must validate broken link explanation');

radios[1].value = 'valid';
radios[1].onchange();
assert.ok(feedback.className.includes('incorrect'), 'Feedback must be incorrect for valid option');

// 2. Test Presets fillLabExample
const presetAlice = document.getElementById('chain-preset-alice');
presetAlice.onclick();
const chainData = document.getElementById('chain-data');
assert.ok(chainData.value.includes('Alice trả Bob'), 'chain-data must be populated by preset');

// 3. Test Reset resets hypothesis
vm.runInContext('resetChainLab(false)', context);
assert.equal(feedback.textContent, '');
assert.equal(feedback.className, 'hypothesis-feedback');
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, f"Node test failed:\n{result.stderr}"
