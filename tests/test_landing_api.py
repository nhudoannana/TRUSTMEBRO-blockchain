"""Phase 1 entry routes lead to the existing journey, with no repository mount."""
from html.parser import HTMLParser
import subprocess
import struct
from pathlib import Path

from tests.test_mempool_api import client


def test_reduced_motion_finishes_code_and_counts_without_animation():
    script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('landing.html','utf8');
const source=html.slice(html.indexOf('// ========== 4.'),html.indexOf('// ========== 6.'));
const code={children:[],replaceChildren(){this.children=[];},appendChild(e){this.children.push(e);},querySelector(){return this.children.at(-1);}};
const numbers=[6,256,3,12].map(n=>({dataset:{count:String(n)},textContent:'0'}));
const stats={querySelectorAll:()=>numbers};
const observers=[];
const context=vm.createContext({document:{getElementById:()=>code,querySelectorAll:()=>[stats],createElement:()=>({style:{},dataset:{},textContent:''})},
 matchMedia:()=>({matches:true}),IntersectionObserver:class{constructor(callback){this.callback=callback;observers.push(this);}observe(target){this.callback([{isIntersecting:true,target}]);}unobserve(){}},
 setTimeout(){throw Error('Reduced motion must not schedule typing');},requestAnimationFrame(){throw Error('Reduced motion must not schedule counting');},performance:{now:()=>0}});
vm.runInContext(source,context);
assert.deepEqual(numbers.map(e=>e.textContent),['6','256','3','12']);
assert.equal(code.children.map(e=>e.textContent).join(''),vm.runInContext('codeLines.map(e=>e.text).join("")',context));
assert.ok(code.children.length>1);
"""
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = {}
        self.urls = []
        self.start = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.urls.append(attrs.get('href'))
            self.hrefs[attrs.get('id', '')] = attrs.get('href')
            if 'start-button' in attrs.get('class', '').split() or 'btn-primary' in attrs.get('class', '').split():
                self.start.append(attrs.get('href'))


def test_entry_routes_follow_mode_choice_to_integrated_journey(client):
    root = client.get('/', follow_redirects=False)
    assert root.status_code == 307
    assert root.headers['location'] == '/landing.html'
    landing = client.get(root.headers['location'])
    assert landing.status_code == 200
    links = Links(landing.text)
    assert links.start and set(links.start) == {'/ui/modes.html'}
    modes = client.get(links.start[0])
    assert modes.status_code == 200
    choices = Links(modes.text)
    journey = client.get(choices.hrefs['guided-mode'])
    assert journey.status_code == 200
    assert choices.hrefs['guided-mode'] == '/ui/trustmebro.html'
    assert 'handlePowMining' in journey.text and '/mining/pow' in journey.text
    assert 'embedded-simulation' not in landing.text and 'srcdoc' not in landing.text
    assert client.get(choices.hrefs['labs-mode'].split('#')[0]).status_code == 200
    assert choices.hrefs['labs-mode'] == '/ui/modes.html#labs'
    assert '/landing.html' in Links(journey.text).urls


def test_entry_static_boundary_and_landing_assets(client):
    landing = client.get('/landing.html').text
    assert 'letter-glitch-canvas' in landing and 'ResizeObserver' in landing
    assert 'cdn.tailwindcss.com' not in landing
    for path in ['/requirements.txt', '/.git/config', '/api/wallet_api.py',
                 '/design-guidelines/TrustMeBro-Blockchain.html']:
        assert client.get(path).status_code == 404


def test_lab_home_links_use_existing_ui_mount(client):
    modes = client.get('/ui/modes.html')
    links = [url for url in Links(modes.text).urls if url and url.startswith('/ui/labs.html#')]
    assert set(links) == {'/ui/labs.html#sha', '/ui/labs.html#signatures', '/ui/labs.html#merkle', '/ui/labs.html#blocks', '/ui/labs.html#consensus', '/ui/labs.html#network', '/ui/labs.html#tamper'}
    for url in links:
        assert client.get(url.split('#')[0]).status_code == 200
    script = client.get('/ui/labs.js')
    assert script.status_code == 200
    assert 'javascript' in script.headers['content-type']


def test_attack_navigation_uses_existing_static_mount(client):
    assert '/ui/attacks.html' in Links(client.get('/ui/modes.html').text).urls
    labs = client.get('/ui/labs.html').text
    assert '/ui/attacks.html' in Links(labs).urls
    assert '/ui/labs.html#tamper' in Links(client.get('/ui/modes.html').text).urls
    page = client.get('/ui/attacks.html')
    assert page.status_code == 200 and '/ui/labs.html' in Links(page.text).urls
    assert client.get('/ui/attacks.js').status_code == 200


def test_explorer_entry_preserves_static_boundary_and_guided_state(client):
    modes = Links(client.get('/ui/modes.html').text)
    assert modes.hrefs['explorer-mode'] == '/ui/explorer.html'
    before = client.get('/api/session').json()
    page = client.get(modes.hrefs['explorer-mode'])
    assert page.status_code == 200
    links = Links(page.text)
    assert '/ui/modes.html#labs' in links.urls and '/ui/trustmebro.html' in links.urls
    assert client.get('/ui/explorer.js').status_code == 200
    assert client.get('/api/network_store.py').status_code == 404
    assert client.get('/api/session').json() == before


def test_about_roster_maps_assignments_by_name(client):
    class Members(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.rows = []
            self.headings = []
            self.in_heading = False
            self.in_body = False
            self.in_value = False
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'ol' and attrs.get('id') == 'team-members':
                self.in_body = True
            if tag == 'li' and self.in_body:
                self.rows.append([])
            if tag == 'h4' and self.in_body:
                self.in_heading = True
                self.headings.append('')
            if tag == 'span' and self.in_body and attrs.get('class') == 'member-value':
                self.in_value = True
                self.rows[-1].append('')

        def handle_endtag(self, tag):
            if tag == 'ol':
                self.in_body = False
            if tag == 'span':
                self.in_value = False
            if tag == 'h4':
                self.in_heading = False

        def handle_data(self, text):
            if self.in_value:
                self.rows[-1][-1] += text
            if self.in_heading:
                self.headings[-1] += text

    roster = [
        ('Đoàn Nguyễn Quỳnh Như', '031340240021', 'Trưởng nhóm'),
        ('Nguyễn Lê Phạm Lộc', '031340240015', 'Thành viên'),
        ('Huỳnh Thị Tuyết Mai', '031340240016', 'Thành viên'),
        ('Cai Thị Thảo Nguyên', '031340240019', 'Thành viên'),
        ('Kiều Thị Yến Nhi', '031340240020', 'Thành viên'),
        ('Trần Quỳnh Ngọc Thảo', '031340240026', 'Thành viên'),
        ('Phạm Thị Hồng Thắm', '031340240027', 'Thành viên'),
    ]
    assignments = {
        'Đoàn Nguyễn Quỳnh Như': 'Cấu trúc khối, block header, PoW; điều phối kho mã nguồn.',
        'Nguyễn Lê Phạm Lộc': 'Kiểm thử, kịch bản demo, chuẩn bị video và Attack Simulator.',
        'Huỳnh Thị Tuyết Mai': 'Báo cáo dự án và tài liệu kỹ thuật.',
        'Cai Thị Thảo Nguyên': 'Mạng P2P và mô phỏng nhiều node.',
        'Kiều Thị Yến Nhi': 'Xác thực giao dịch, mempool; khai thác và đồng thuận phân tán.',
        'Trần Quỳnh Ngọc Thảo': 'Rà soát tài liệu và hỗ trợ thuyết trình.',
        'Phạm Thị Hồng Thắm': 'SHA-256, chữ ký số ECDSA, cây Merkle và Merkle proof.',
    }
    html = client.get('/landing.html').text
    members = Members(html)
    rows = members.rows
    assert members.headings == ['Khối & Proof of Work', 'Kiểm thử & Demo',
                                'Báo cáo & Tài liệu', 'Mạng P2P & Đồng bộ',
                                'Giao dịch & Đồng thuận', 'Rà soát & Thuyết trình',
                                'Mã băm & Chữ ký số']
    assert len(rows) == len(roster)
    readme_rows = {}
    for line in Path('README.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('| ') and '03134024' in line:
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            readme_rows[cells[1]] = cells
    for index, (row, expected) in enumerate(zip(rows, roster), 1):
        name, student_id, role = expected
        assert row == [str(index), name, student_id, role, assignments[name]]
        assert readme_rows[name][2] == student_id
        assert readme_rows[name][4]  # All seven have documented assignments.
    assert 'Dự án nhóm 5' in html
    assert 'Trường Đại học Ngân hàng TP. Hồ Chí Minh' in html
    assert 'Giảng viên hướng dẫn: TS. Nguyễn Hoài Đức' in html
    assert 'https://github.com/nhudoannana/TRUSTMEBRO-blockchain' in Links(html).urls


def test_about_logo_is_public_static_png(client):
    class Images(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'img' and dict(attrs).get('class') == 'about-project-logo':
                self.logo = dict(attrs)

    parser = Images()
    parser.feed(client.get('/landing.html').text)
    image = parser.logo
    assert image['alt'] == 'Logo Trường Đại học Ngân hàng TP. Hồ Chí Minh (HUB)'
    assert int(image['width']) > 0 and int(image['height']) > 0
    response = client.get(image['src'])
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert 'set-cookie' not in response.headers
    assert response.content == Path('ui/assets/logo-hub-transparent.png').read_bytes()
    assert response.content[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II', response.content[16:24]) == (int(image['width']), int(image['height']))


def test_transparent_logo_preserves_original_colors_and_internal_white():
    import hashlib
    from PIL import Image

    source = Path('ui/assets/logo-hub.png')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '86c28a8960197a3528a68091925e946f8d45340870e6275ed3c21aef94931bfa'
    original = Image.open(source).convert('RGB')
    derivative = Image.open('ui/assets/logo-hub-transparent.png')
    assert derivative.mode == 'RGBA'
    assert derivative.size == (732, 814)
    assert derivative.getpixel((0, 0))[3] == 0
    assert derivative.getpixel((731, 0))[3] == 0
    # White lettering and circuitry, including an opening to the exterior,
    # stay opaque: removing every white pixel or a plain flood-fill fails here.
    for x, y in [(430, 340), (500, 565), (738, 505)]:
        assert original.getpixel((x, y)) == (255, 255, 255)
        assert derivative.getpixel((x - 234, y - 193)) == (255, 255, 255, 255)
    cropped = original.crop((234, 193, 966, 1007))
    assert derivative.convert('RGB').tobytes() == cropped.tobytes()
    colors = cropped.tobytes()
    for index, alpha in enumerate(derivative.getchannel('A').tobytes()):
        if colors[index * 3:index * 3 + 3] != b'\xff\xff\xff':
            assert alpha == 255
