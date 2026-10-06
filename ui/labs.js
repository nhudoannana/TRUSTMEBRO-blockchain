// These exercises never call journey wallet, credential, mining or reset APIs.
const $ = id => document.getElementById(id);
const LAB_API = '/api/labs';

async function labPost(path, body) {
  const response = await fetch(LAB_API + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return labResponse(response);
}

async function labResponse(response) {
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(e => e.msg).join('; ')
      : typeof detail === 'string' ? detail : detail?.message || `Lỗi HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

function labError(id, message = '') { $(id).textContent = message; $(id).hidden = !message; }
function formBusy(id, busy) { $(id).querySelectorAll('input,textarea,select,button').forEach(e => { e.disabled = busy; }); }
const shortHash = value => value.slice(0, 12) + '…' + value.slice(-8);

function resultMetric(parent, label, value, unit, decimals) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return;
  const metric = document.createElement('div'); metric.className = 'result-metric';
  chainText(metric, 'span', label).className = 'metric-label';
  chainText(metric, 'strong', decimals == null ? String(value) : value.toFixed(decimals)).className = 'metric-number';
  chainText(metric, 'span', unit).className = 'metric-unit'; parent.append(metric);
}
function powHash(parent, hash, difficulty) {
  if (!hash) return;
  const line = chainText(parent, 'p', 'Hash block: '), code = document.createElement('code');
  code.className = 'digest'; line.append(code);
  const zeros = Number.isInteger(difficulty) && difficulty > 0 && difficulty <= hash.length && hash.startsWith('0'.repeat(difficulty)) ? difficulty : 0;
  if (zeros) chainText(code, 'mark', hash.slice(0, zeros));
  chainText(code, 'span', hash.slice(zeros));
  if (zeros) chainText(parent, 'p', `${zeros} ký tự 0 đầu tiên đáp ứng độ khó; các ký tự 0 khác không được tô thêm.`).className = 'hint';
}

function fillLabExample(id, text) {
  const input = $(id);
  if (input.value === text) return;
  if (input.value && !window.confirm('Thay nội dung đang nhập bằng ví dụ? Chỉ điền dữ liệu, không chạy thí nghiệm.')) return;
  input.value = text;
  input.oninput?.();
}

async function hashText(text) {
  if (!globalThis.crypto?.subtle) throw new Error('Web Crypto cần HTTPS hoặc localhost. Hãy mở trang qua server.');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

function changedHashBits(a, b) {
  let bits = 0;
  for (let i = 0; i < a.length; i++) {
    let xor = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    while (xor) { bits += xor & 1; xor >>= 1; }
  }
  return bits;
}

let hashToken = 0, hashBusy = false;
let shaTab = 'theory', shaTopic = 0;

function showShaTab(tab, focusInput = false) {
  shaTab = tab === 'practice' ? 'practice' : 'theory';
  for (const name of ['theory', 'practice']) {
    const button = $('sha-tab-' + name), selected = name === shaTab;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $('sha-' + name).hidden = !selected;
  }
  if (focusInput && shaTab === 'practice') $('hash-a').focus();
}

function selectShaTopic(index) {
  shaTopic = Math.max(0, Math.min(4, index));
  for (let i = 0; i < 5; i++) {
    $('sha-topic-' + i).setAttribute('aria-pressed', String(i === shaTopic));
    $('sha-lesson-' + i).hidden = i !== shaTopic;
  }
  $('sha-previous').disabled = shaTopic === 0;
  $('sha-next').textContent = shaTopic === 4 ? 'Thử ngay' : 'Tiếp theo';
  $('sha-step-status').textContent = `Mục ${shaTopic + 1} / 5`;
}

// Presentation state only: practice owners and their lifecycle stay unchanged.
const labLearning = Object.fromEntries(['signatures', 'merkle', 'blocks', 'consensus', 'network']
  .map(name => [name, { tab: 'theory', topic: 0 }]));
const labPracticeFocus = { signatures: 'sig-message', merkle: 'merkle-leaves',
  blocks: 'chain-data', consensus: 'comparison-pow', network: 'network-init' };
function showLabLearning(name, tab, focusPractice = false) {
  const s = labLearning[name]; s.tab = tab === 'practice' ? 'practice' : 'theory';
  for (const value of ['theory', 'practice']) {
    const selected = s.tab === value, button = $(name + '-tab-' + value);
    button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
    $(name + '-' + value).hidden = !selected;
  }
  if (focusPractice && s.tab === 'practice') {
    const target = $(labPracticeFocus[name]);
    (target.disabled ? $(name + '-practice') : target).focus();
  }
}
function selectLabTopic(name, index) {
  const s = labLearning[name]; s.topic = Math.max(0, Math.min(3, index));
  for (let i = 0; i < 4; i++) {
    $(name + '-topic-' + i).setAttribute('aria-pressed', String(i === s.topic));
    $(name + '-lesson-' + i).hidden = i !== s.topic;
  }
  $(name + '-previous').disabled = s.topic === 0;
  $(name + '-next').textContent = s.topic === 3 ? 'Thử ngay' : 'Tiếp theo';
  $(name + '-step-status').textContent = `Mục ${s.topic + 1} / 4`;
}
function setupLabLearning() {
  for (const name of Object.keys(labLearning)) {
    for (const [index, tab] of ['theory', 'practice'].entries()) {
      const button = $(name + '-tab-' + tab);
      button.onclick = () => showLabLearning(name, tab);
      button.onkeydown = event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 'theory' : event.key === 'End' ? 'practice' : ['theory', 'practice'][1 - index];
        showLabLearning(name, next); $(name + '-tab-' + next).focus();
      };
    }
    for (let i = 0; i < 4; i++) $(name + '-topic-' + i).onclick = () => selectLabTopic(name, i);
    $(name + '-previous').onclick = () => selectLabTopic(name, labLearning[name].topic - 1);
    $(name + '-next').onclick = () => labLearning[name].topic === 3
      ? showLabLearning(name, 'practice', true) : selectLabTopic(name, labLearning[name].topic + 1);
    showLabLearning(name, 'theory'); selectLabTopic(name, 0);
  }
}

async function compareHashes(event) {
  event.preventDefault();
  if (hashBusy) return;
  const token = ++hashToken, original = $('hash-a').value, edited = $('hash-b').value;
  hashBusy = true; formBusy('hash-form', true); labError('hash-error');
  $('hash-status').textContent = 'Đang băm trong trình duyệt…';
  try {
    const [a, b] = await Promise.all([hashText(original), hashText(edited)]);
    if (token !== hashToken) return;
    $('hash-original').textContent = a; $('hash-edited').textContent = b;
    const bits = changedHashBits(a, b);
    const metrics = $('hash-metrics'); metrics.replaceChildren();
    resultMetric(metrics, 'Tỷ lệ bit thay đổi', bits / 256 * 100, '%', 2);
    resultMetric(metrics, 'Số bit thay đổi', bits, '/ 256 bit');
    $('hash-result-context').textContent = 'Kết quả cho hai văn bản tại thời điểm bấm tính.';
    $('hash-difference').textContent = `${bits}/256 bit khác nhau (${(bits / 256 * 100).toFixed(2)}%). ` +
      (original === edited ? 'Hai đầu vào giống nhau tạo cùng hash SHA-256, vì vậy chênh lệch là 0%.'
        : 'Với hai đầu vào khác nhau, hiệu ứng avalanche thường làm khoảng một nửa số bit hash thay đổi; tỷ lệ không cần đạt 100%.');
    $('hash-result').hidden = false;
    $('hash-status').textContent = 'Đã tính hai hash thật cho nội dung tại thời điểm bấm nút. Thử đổi một ký tự rồi tính lại; kết quả đo số bit khác nhau trên 256 bit.';
  } catch (error) { if (token === hashToken) labError('hash-error', error.message); }
  finally { if (token === hashToken) { hashBusy = false; formBusy('hash-form', false); } }
}
function resetHash() {
  hashToken++; hashBusy = false; formBusy('hash-form', false);
  $('hash-a').value = ''; $('hash-b').value = '';
  ['hash-original', 'hash-edited', 'hash-difference'].forEach(id => { $(id).textContent = ''; });
  $('hash-result').hidden = true; $('hash-status').textContent = 'Đã reset riêng lab SHA-256.';
  $('hash-metrics').replaceChildren(); $('hash-result-context').textContent = '';
  labError('hash-error');
}

function freshSignature() { return { key: null, other: null, signed: null, busy: false, result: null }; }
let signature = freshSignature();
async function disposeKey(handle) { if (handle) await labPost(`/signatures/keys/${encodeURIComponent(handle)}/reset`); }

function showSignature() {
  const s = signature;
  ['sig-create', 'sig-other', 'sig-message', 'sig-presented', 'sig-key-choice'].forEach(id => { $(id).disabled = s.busy; });
  $('sig-sign').disabled = s.busy || !s.key;
  $('sig-original').disabled = $('sig-verify').disabled = s.busy || !s.signed;
  $('sig-control-note').textContent = s.busy ? 'Đang chờ backend; các thao tác ký/kiểm tra tạm khóa.'
    : !s.key ? 'Bắt đầu bằng Tạo khóa tạm. Có khóa mới ký được thông điệp; có chữ ký mới xác minh được.'
    : !s.signed ? 'Khóa đã sẵn sàng. Nhập thông điệp rồi bấm Ký thông điệp để mở các nút xác minh.'
    : 'Có thể xác minh bản gốc hoặc sửa bản sao rồi kiểm tra. Chữ ký đã ghi được giữ nguyên.';
  $('sig-other-option').disabled = !s.other;
  $('sig-other-option').textContent = s.other ? `Khóa khác — ${shortHash(s.other.address)}` : 'Khóa khác — chưa tạo';
  $('sig-key-status').textContent = s.key
    ? `Khóa ký ${shortHash(s.key.address)} · ${s.key.curve} · hết hạn sau tối đa 15 phút.` : 'Chưa có khóa tạm.';
  $('sig-public').textContent = [s.key, s.other].filter(Boolean).map((k, i) =>
    `${i === 0 && s.key ? 'Khóa ký' : 'Khóa khác'}\nPublic key: ${k.public_key_hex}\nĐịa chỉ: ${k.address}`).join('\n\n');
  $('sig-signature').textContent = s.signed?.signature_hex || '';
  $('sig-signed-message').textContent = s.signed ? 'Thông điệp đã ký: ' + JSON.stringify(s.signed.message) : '';
  $('sig-result').hidden = !s.result;
  if (s.result) {
    $('sig-result').className = 'result ' + (s.result.valid ? 'valid' : 'invalid');
    $('sig-result').textContent = `${s.result.valid ? '✓ Chữ ký hợp lệ' : '✗ Chữ ký không hợp lệ'} — ${s.result.label}. Backend đã kiểm tra bằng khóa công khai đã chọn. ` +
      (s.result.valid ? 'Thử sửa bản sao hoặc dùng khóa khác rồi xác minh lại.' : 'Đối chiếu bản gốc bằng khóa đã ký để so sánh; kết quả này không sửa thông điệp hay chữ ký.');
  }
}

async function signatureAction(action, event) {
  event?.preventDefault();
  const s = signature;
  if (s.busy || (action === 'sign' && !s.key) || (['original', 'verify'].includes(action) && !s.signed)) return;
  const key = action === 'original' ? s.signed : $('sig-key-choice').value === 'other' ? s.other : s.signed;
  if (action === 'verify' && !key) { labError('sig-error', 'Hãy tạo khóa khác trước khi chọn nó.'); return; }
  const message = action === 'original' ? s.signed.message : $('sig-presented').value;
  s.busy = true; showSignature(); labError('sig-error'); $('sig-status').textContent = 'Đang chờ backend…';
  try {
    let data;
    if (action === 'create' || action === 'other') data = await labPost('/signatures/keys');
    else if (action === 'sign') data = await labPost('/signatures/sign', { key_handle: s.key.key_handle, message: $('sig-message').value });
    else data = await labPost('/signatures/verify', { message, signature_hex: s.signed.signature_hex, public_key_hex: key.public_key_hex });
    if (s !== signature) {
      if (data.key_handle && (action === 'create' || action === 'other')) await disposeKey(data.key_handle);
      return;
    }
    if (action === 'create' || action === 'other') {
      const property = action === 'create' ? 'key' : 'other', old = s[property];
      s[property] = data;
      if (action === 'create') { s.signed = null; s.result = null; $('sig-presented').value = ''; }
      $('sig-status').textContent = 'Đã tạo khóa tạm trên server; không tạo ví journey.';
      // Old handles are already inaccessible from this UI; TTL is the fallback if cleanup fails.
      if (old) await disposeKey(old.key_handle);
    } else if (action === 'sign') {
      s.signed = data; s.result = null; $('sig-presented').value = data.message;
      $('sig-key-choice').value = 'original'; $('sig-status').textContent = 'Đã ký thật. Hãy xác minh bản gốc, rồi thử sửa bản sao.';
    } else {
      s.result = { valid: data.valid, label: action === 'original' ? 'thông điệp gốc / khóa đã ký' : 'bản xuất trình / ' + ($('sig-key-choice').value === 'other' ? 'khóa khác' : 'khóa đã ký') };
      $('sig-status').textContent = 'Đã xác minh; chữ ký gốc không bị thay đổi.';
    }
  } catch (error) { if (s === signature) labError('sig-error', error.message); }
  finally { if (s === signature) { s.busy = false; showSignature(); } }
}

async function resetSignature() {
  const old = signature;
  signature = freshSignature();
  ['sig-message', 'sig-presented'].forEach(id => { $(id).value = ''; });
  $('sig-key-choice').value = 'original'; labError('sig-error'); showSignature();
  $('sig-status').textContent = 'Đã reset riêng lab chữ ký; đang dọn handle trên server…';
  const current = signature;
  try {
    await Promise.all([old.key, old.other].filter(Boolean).map(k => disposeKey(k.key_handle)));
    if (signature === current) $('sig-status').textContent = 'Đã xóa khóa tạm và trạng thái lab. Journey không bị reset.';
  } catch (error) { if (signature === current) labError('sig-error', `Trạng thái cục bộ đã xóa; chưa xác nhận dọn khóa: ${error.message}. Khóa sẽ hết hạn sau tối đa 15 phút.`); }
}

function readLeaves(text) { return text === '' ? [] : text.split('\n'); }
function updateProofChoices() {
  const select = $('merkle-proof'), previous = select.value, leaves = readLeaves($('merkle-leaves').value);
  select.replaceChildren(new Option('Không cần proof', ''));
  leaves.slice(0, 16).forEach((_, i) => select.add(new Option(`Lá ${i + 1}`, String(i))));
  select.value = Number(previous) < leaves.length ? previous : '';
}
let merkleToken = 0, merkleBusy = false, merklePrevious = null;
function merkleControls(busy) {
  formBusy('merkle-form', busy);
  ['merkle-one', 'merkle-odd', 'merkle-empty'].forEach(id => { $(id).disabled = busy; });
}

function merkleSvg(data, previous, count, inspections, inputs) {
  const svgElement = (tag, attributes, text) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const width = Math.max(360, data.levels[0].length * 184), height = data.levels.length * 156 + 24;
  const svg = svgElement('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'group',
    'aria-label': 'Cây Merkle: root ở trên, lá ở dưới. Chọn node để mở hash đầy đủ.' });
  svg.setAttribute('class', 'merkle-svg');
  const point = (l, i) => ({ x: (i + .5) * width / data.levels[l].length, y: 20 + (data.levels.length - 1 - l) * 156 });
  const path = new Set(), siblings = new Set();
  if (data.proof && count) {
    let index = data.proof.index;
    path.add(`0:${index}`);
    data.proof.siblings.forEach(([hash, side], l) => {
      const sibling = Math.min(side === 'left' ? index - 1 : index + 1, data.levels[l].length - 1);
      if (data.levels[l][sibling] === hash) siblings.add(`${l}:${sibling}`);
      index = Math.floor(index / 2); path.add(`${l + 1}:${index}`);
    });
  }
  data.levels.slice(0, -1).forEach((level, l) => {
    data.levels[l + 1].forEach((hash, parent) => {
      for (let side = 0; side < 2; side++) {
        const raw = parent * 2 + side, child = Math.min(raw, level.length - 1), duplicate = raw >= level.length;
        const a = point(l, child), b = point(l + 1, parent), from = `${l}:${child}`, to = `${l + 1}:${parent}`;
        const edge = svgElement('path', { d: `M ${a.x + (duplicate ? 18 : 0)} ${a.y} L ${b.x + (duplicate ? 18 : 0)} ${b.y + 76}`,
          class: 'merkle-edge' + (duplicate ? ' duplicate' : '') + (path.has(to) && (path.has(from) || siblings.has(from)) ? ' proof-edge' : ''),
          'aria-label': `Tầng ${l}, node ${child + 1} → tầng ${l + 1}, node ${parent + 1}${duplicate ? ' · nhân đôi hash cuối' : ''}` });
        edge.dataset.from = from; edge.dataset.to = to; edge.dataset.duplicate = String(duplicate); svg.append(edge);
        if (duplicate) {
          const x = Math.min(width - 100, Math.max(100, (a.x + b.x) / 2)), y = b.y + 102;
          const note = svgElement('g', { class: 'merkle-duplicate-note', 'aria-label': l === 0 ? 'Lặp hash lá cuối để ghép cặp' : 'Lặp hash node cuối để ghép cặp' });
          note.dataset.duplicateNote = 'true';
          note.append(svgElement('rect', { x: x - 98, y: y - 14, width: 196, height: 40, rx: 6 }),
            svgElement('text', { x, y, 'text-anchor': 'middle' }, l === 0 ? 'Lặp hash lá cuối' : 'Lặp hash node cuối'),
            svgElement('text', { x, y: y + 16, 'text-anchor': 'middle' }, 'để ghép cặp'));
          svg.append(note);
        }
      }
    });
  });
  data.levels.forEach((level, l) => level.forEach((hash, i) => {
    const key = `${l}:${i}`, p = point(l, i), changed = previous && previous.levels[l]?.[i] !== hash;
    const label = l === data.levels.length - 1 ? count === 1 ? 'Lá / Merkle root' : 'Merkle root' : l === 0 ? 'Lá' : 'Hash cha';
    const input = l === 0 && count ? inputs[i] : undefined;
    const markers = [changed ? 'Đổi / mới' : '', path.has(key) ? l === 0 ? 'Lá chọn' : 'Đường proof' : '', siblings.has(key) ? 'Anh em proof' : ''].filter(Boolean);
    const group = svgElement('g', { transform: `translate(${p.x - 82},${p.y})`, tabindex: 0, role: 'button',
      'aria-label': `${label} ${i + 1}, tầng ${l}. ${markers.join('. ')}. Mở hash đầy đủ`,
      class: 'merkle-visual-node' + (changed ? ' changed' : '') + (path.has(key) ? ' proof-path' : '') + (siblings.has(key) ? ' proof-sibling' : '') });
    group.dataset.node = key; group.dataset.y = String(p.y);
    group.append(svgElement('title', {}, `${label} ${i + 1}: ${hash}`), svgElement('rect', { width: 164, height: input === undefined ? 76 : 100, rx: 12 }),
      svgElement('text', { x: 82, y: 20, 'text-anchor': 'middle' }, `${label}${l === data.levels.length - 1 ? count === 1 ? ' · 1' : '' : ' ' + (i + 1)}`),
      svgElement('text', { x: 82, y: 41, 'text-anchor': 'middle' }, hash.length > 14 ? hash.slice(0, 6) + '…' + hash.slice(-6) : hash));
    if (input !== undefined) group.append(svgElement('text', { x: 82, y: 63, 'text-anchor': 'middle', class: 'merkle-preview' },
      input === '' ? '(Dòng rỗng)' : Array.from(input).slice(0, 18).join('') + (Array.from(input).length > 18 ? '…' : '')));
    group.append(svgElement('text', { x: 82, y: input === undefined ? 62 : 86, 'text-anchor': 'middle', class: 'merkle-marker' }, markers.join(' · ')));
    const inspect = () => { const entry = inspections.get(key); entry.levels.open = true; entry.details.open = true; entry.summary.focus(); };
    group.onclick = inspect;
    group.onkeydown = event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); inspect(); } };
    svg.append(group);
  }));
  return svg;
}

function showMerkle(data, previous, count, inputs = []) {
  $('merkle-result').hidden = false;
  $('merkle-root').textContent = data.root.length > 20 ? shortHash(data.root) : data.root;
  $('merkle-root').title = data.root; $('merkle-root-full').textContent = data.root;
  $('merkle-summary').textContent = `${count} lá · ${previous ? previous.root === data.root ? 'Root giữ nguyên' : 'Root đã thay đổi' : 'Đã tính root'}.`;
  const container = $('merkle-tree'); container.replaceChildren();
  const diagram = document.createElement('div'); diagram.className = 'merkle-diagram'; diagram.tabIndex = 0;
  diagram.setAttribute('role', 'region'); diagram.setAttribute('aria-label', 'Sơ đồ cây có thể cuộn ngang'); container.append(diagram);
  const legend = document.createElement('p'); legend.className = 'hint';
  legend.textContent = 'Root ở trên, lá ở dưới. Nét đứt: ghép hash cuối với chính nó. Nhãn Đổi / mới so sánh cùng vị trí; nhãn proof chỉ đường được cung cấp, không thay thế kết quả xác minh backend.';
  container.append(legend);
  const levels = document.createElement('details'), levelsSummary = document.createElement('summary');
  levelsSummary.textContent = 'Chi tiết các tầng'; levels.append(levelsSummary); container.append(levels);
  const inspections = new Map();
  if (!count) { const note = document.createElement('p'); note.textContent = 'Không có lá. Backend trả về một tầng chứa root của cây rỗng.'; container.append(note); }
  data.levels.forEach((level, l) => {
    const heading = document.createElement('p'); heading.className = 'level-title';
    heading.textContent = `Tầng ${l}${l === 0 && count ? ' / Lá' : l === data.levels.length - 1 ? ' / Root' : ''}`;
    levels.append(heading);
    const row = document.createElement('div'); row.className = 'tree-level';
    level.forEach((hash, i) => {
      const node = document.createElement('div'), changed = previous && previous.levels[l]?.[i] !== hash;
      node.className = 'tree-node' + (changed ? ' changed' : '');
      const details = document.createElement('details'), summary = document.createElement('summary'), code = document.createElement('code');
      details.dataset.fullNode = `${l}:${i}`; inspections.set(`${l}:${i}`, { details, summary, levels });
      summary.textContent = `${i + 1} · ${shortHash(hash)}`;
      code.textContent = hash; details.append(summary, code); node.append(details);
      if (l === 0 && count && inputs[i] !== undefined) {
        const value = document.createElement('pre'); value.textContent = inputs[i];
        const label = document.createElement('p'); label.textContent = `Dữ liệu đầy đủ của lá ${i + 1}:`;
        details.append(label, value);
      }
      if (changed) { const label = document.createElement('small'); label.textContent = 'Đổi / mới'; node.append(label); }
      if (count && i >= Math.ceil(count / (2 ** l))) { const label = document.createElement('small'); label.textContent = 'Bản sao ghép cặp từ backend'; node.append(label); }
      row.append(node);
    });
    levels.append(row);
  });
  diagram.append(merkleSvg(data, previous, count, inspections, inputs));
  $('merkle-proof-result').textContent = data.proof
    ? `Lá ${data.proof.index + 1} · Backend kiểm tra proof: ${data.proof.valid ? 'hợp lệ' : 'không hợp lệ'}\n` + JSON.stringify(data.proof.siblings, null, 2)
    : count ? 'Không yêu cầu proof cho lần tính này.' : 'Cây rỗng không có lá để chứng minh.';
}

async function computeMerkle(event) {
  event.preventDefault(); if (merkleBusy) return;
  const token = ++merkleToken, leaves = readLeaves($('merkle-leaves').value), selected = $('merkle-proof').value;
  merkleBusy = true; merkleControls(true); labError('merkle-error'); $('merkle-status').textContent = 'Đang tính trên backend…';
  try {
    const data = await labPost('/merkle', { leaves, proof_index: selected === '' ? null : Number(selected) });
    if (token !== merkleToken) return;
    showMerkle(data, merklePrevious, leaves.length, leaves); merklePrevious = data;
    $('merkle-status').textContent = 'Đã tính lại các tầng thật. Dấu “Đổi / mới” so sánh hash ở cùng vị trí với lần trước.';
  } catch (error) { if (token === merkleToken) labError('merkle-error', error.message); }
  finally { if (token === merkleToken) { merkleBusy = false; merkleControls(false); } }
}
function resetMerkle() {
  merkleToken++; merkleBusy = false; merklePrevious = null; merkleControls(false);
  $('merkle-leaves').value = ''; updateProofChoices(); $('merkle-root').textContent = '';
  $('merkle-tree').replaceChildren(); $('merkle-proof-result').textContent = ''; $('merkle-result').hidden = true;
  labError('merkle-error'); $('merkle-status').textContent = 'Đã reset riêng lab Merkle; không gọi reset phiên demo.';
}

function freshChainLab() { return { busy: false, result: null, selected: 0, draft: '', lastAdded: null, initialization: null }; }
let chainLab = freshChainLab();

function chainText(parent, tag, text) {
  const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
}

function chainButtonReason(id, reason) {
  const note = $(id);
  if (!note) return;
  note.textContent = reason; note.hidden = !reason; note.setAttribute('role', 'status');
}

function chainControls() {
  const s = chainLab, data = s.result;
  formBusy('chain-form', s.busy);
  $('chain-init').hidden = s.busy || !!data;
  $('chain-init').disabled = s.busy;
  $('chain-example').disabled = s.busy;
  $('chain-add').disabled = s.busy || !data || !data.validation.valid || data.chain.length > data.max_blocks;
  const busyReason = s.busy ? $('chain-status').textContent : '';
  chainButtonReason('chain-add-reason', busyReason || (!data
    ? 'Chưa có chuỗi. Bấm Thử khởi tạo genesis lại nếu khởi tạo thất bại.'
    : !data.validation.valid ? 'Chuỗi đang không hợp lệ nên không thêm khối. Xem khối bị đánh dấu đỏ/vàng, hoặc bấm Đặt lại.'
    : data.chain.length > data.max_blocks ? 'Đã đạt 12 khối (giới hạn của lab). Bấm Đặt lại để làm chuỗi mới.' : ''));
  $('chain-difficulty-hint').textContent = Number($('chain-difficulty').value) >= 4
    ? 'Độ khó 4–5 là thử thách: có thể chưa tìm được nonce trong giới hạn; khi đó khối chưa được thêm.'
    : 'Độ khó 2–3 phù hợp để bắt đầu; mỗi lượt đào vẫn có giới hạn.';
  $('chain-validate').disabled = s.busy || !data;
  $('chain-previous').value = data?.blocks.at(-1)?.computed_hash || '';
  const selected = data?.chain[s.selected], state = data?.blocks[s.selected];
  if ($('chain-edited-data')) $('chain-edited-data').disabled = s.busy;
  if ($('chain-edit')) $('chain-edit').disabled = s.busy || !s.selected || !selected
    || s.draft === selected.transaction?.payload.lab_data;
  if ($('chain-recompute')) $('chain-recompute').disabled = s.busy || !s.selected || !selected
    || selected.transaction.tx_id === state?.computed_transaction_hash;
  if (selected?.transaction) {
    chainButtonReason('chain-edit-reason', busyReason || (s.draft === selected.transaction.payload.lab_data
      ? 'Hãy đổi dữ liệu trước khi sửa.' : ''));
    chainButtonReason('chain-recompute-reason', busyReason || (selected.transaction.tx_id === state?.computed_transaction_hash
      ? 'Hash giao dịch đã khớp; không có dấu vân tay mới để tính lại.' : ''));
  }
}

function selectChainBlock(height) {
  const s = chainLab;
  if (s.busy || !height || !s.result?.chain[height]) return;
  s.selected = height;
  s.draft = s.result.chain[height].transaction.payload.lab_data;
  showChainLab();
  $('chain-edited-data').focus();
}

function showChainLab() {
  const s = chainLab, data = s.result, panel = $('chain-result'), track = $('chain-cards');
  const added = data?.chain.find(block => block.height === s.lastAdded && block.height > 0);
  $('chain-add-feedback').hidden = !added;
  $('chain-add-feedback').textContent = added ? `Đã thêm Block #${added.height}` : '';
  $('chain-show-added').hidden = !added; $('chain-show-added').disabled = s.busy;
  $('chain-show-added').textContent = added ? `Xem khối vừa thêm — #${added.height}` : '';
  $('chain-show-added').onclick = () => {
    if (s !== chainLab || s.busy || !added) return;
    const card = Array.from(track.children).find(element => element.dataset.height === String(added.height));
    card?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'auto' }); card?.focus({ preventScroll: true });
  };
  panel.hidden = !data; track.replaceChildren(); $('chain-summary').replaceChildren(); $('chain-evidence').replaceChildren();
  if (!data) { chainControls(); return; }
  const summary = $('chain-summary');
  summary.className = 'result ' + (data.validation.valid ? 'valid' : 'invalid');
  chainText(summary, 'h2', (data.validation.valid ? '✓ Chuỗi hợp lệ' : '✗ Chuỗi không hợp lệ') + ` · ${data.chain.length - 1} khối ngoài genesis`);
  chainText(summary, 'p', data.validation.reason);
  if (data.mining) {
    chainText(summary, 'h3', data.mining.completed ? '✓ Đã thêm khối' : 'Chưa thêm khối: đào chưa hoàn tất');
    if (data.mining.reason) chainText(summary, 'p', data.mining.reason);
    const metrics = document.createElement('div'); metrics.className = 'result-metrics'; summary.append(metrics);
    const candidate = data.mining.completed ? data.chain.at(-1) : data.candidate;
    resultMetric(metrics, data.mining.completed ? 'Nonce tìm được' : 'Nonce ứng viên — chưa đạt', candidate?.header.nonce, 'nonce');
    resultMetric(metrics, 'Số lần thử', data.mining.attempts, 'lần băm');
    resultMetric(metrics, 'Thời gian', data.mining.seconds, 'giây', 3);
    powHash(summary, candidate?.stored_hash, candidate?.header.difficulty);
  }
  for (const block of data.chain) {
    const state = data.blocks[block.height];
    if (block.height) {
      const preceding = data.chain[block.height - 1];
      const arrow = chainText(track, 'span', state.link_valid ? '→' : '✗ →');
      arrow.className = 'chain-arrow' + (state.link_valid ? ' link-valid' : ' link-broken');
      arrow.dataset.from = String(preceding.height); arrow.dataset.to = String(block.height);
      const relation = `Block #${block.height}.previous_hash → hash đã ghi của #${preceding.height}`;
      arrow.setAttribute('aria-label', `${relation}: ${state.link_valid ? 'đạt' : 'liên kết gãy'}`);
      const caption = chainText(arrow, 'small', `#${block.height} tham chiếu #${preceding.height}\n${state.link_valid ? '✓ Link đạt' : '✗ Link gãy'}`);
      caption.title = `${relation}\nPrevious hash: ${block.header.previous_hash}\nHash trước: ${preceding.stored_hash}`;
    }
    const card = document.createElement('article');
    card.className = 'chain-card ' + (!state.own_validation.valid ? 'own-invalid'
      : !state.prefix_valid ? 'prefix-broken' : 'own-valid');
    card.dataset.height = String(block.height); track.append(card);
    card.tabIndex = -1;
    chainText(card, 'h3', block.height === 0 ? 'Genesis · #0' : 'Block #' + block.height);
    const text = block.transaction?.payload.lab_data;
    const preview = chainText(card, 'p', block.height === 0 ? 'Khối khởi đầu cố định' : text ? text.slice(0, 160) + (text.length > 160 ? '…' : '') : '(Văn bản rỗng)');
    preview.className = 'chain-data-preview';
    chainText(card, 'p', `Timestamp: ${block.header.timestamp}`);
    chainText(card, 'p', `Nonce: ${block.header.nonce} · Độ khó: ${block.header.difficulty}`);
    chainText(card, 'p', `Hash đã ghi: ${shortHash(block.stored_hash)}`);
    chainText(card, 'p', `Hash tính lại: ${shortHash(state.computed_hash)}`);
    if (block.transaction && state.computed_transaction_hash !== block.transaction.tx_id) {
      chainText(card, 'p', `Hash giao dịch đã ghi: ${shortHash(block.transaction.tx_id)}`).title = block.transaction.tx_id;
      chainText(card, 'p', `Hash giao dịch tính lại: ${shortHash(state.computed_transaction_hash)}`).title = state.computed_transaction_hash;
      chainText(card, 'p', 'Nội dung đã đổi — hash giao dịch không khớp.');
    }
    chainText(card, 'p', `Previous hash${block.height ? ' → hash đã ghi của #' + (block.height - 1) : ' (genesis)'}: ${shortHash(block.header.previous_hash)}`).title = block.header.previous_hash;
    chainText(card, 'p', state.own_validation.valid ? '✓ Nội dung/header và bằng chứng riêng đạt' : '✗ Khối không hợp lệ: nội dung/header hoặc bằng chứng riêng không đạt');
    if (state.own_validation.valid && !state.prefix_valid) {
      chainText(card, 'p', 'Block này còn nguyên, nhưng lịch sử trước nó không hợp lệ.').className = 'chain-prefix-warning';
    }
    chainText(card, 'p', state.link_valid ? '✓ Liên kết với khối trước đạt' : '✗ Previous hash bị gãy');
    chainText(card, 'p', state.prefix_valid ? '✓ Tiền tố chuỗi hợp lệ' : '✗ Tiền tố chuỗi không hợp lệ; hash riêng của khối này có thể vẫn đúng.');
    const details = document.createElement('details'); card.append(details);
    chainText(details, 'summary', 'Chi tiết kỹ thuật — header, dữ liệu và kiểm tra đầy đủ');
    if (block.transaction) {
      chainText(details, 'p', 'Hash giao dịch đã ghi / tính lại:');
      chainText(details, 'pre', `${block.transaction.tx_id}\n${state.computed_transaction_hash}`);
    }
    chainText(details, 'pre', JSON.stringify({ block, validation: state }, null, 2));
    if (!block.height) continue;
    const edit = chainText(card, 'button', 'Sửa dữ liệu Block #' + block.height);
    edit.type = 'button'; edit.className = 'secondary'; edit.disabled = s.busy;
    edit.onclick = () => selectChainBlock(block.height);
    if (s.selected !== block.height) continue;
    const form = document.createElement('form'); form.className = 'chain-editor'; card.append(form);
    const label = chainText(form, 'label', 'Dữ liệu thay thế — giữ nguyên bằng chứng đã ghi');
    label.setAttribute('for', 'chain-edited-data');
    const input = document.createElement('textarea'); input.id = 'chain-edited-data'; input.maxLength = 4000; input.value = s.draft;
    form.append(input);
    const submit = chainText(form, 'button', 'Sửa và kiểm tra');
    submit.id = 'chain-edit'; submit.className = 'secondary';
    chainText(form, 'p', '').id = 'chain-edit-reason';
    form.onsubmit = event => chainLabAction('edit', event);
    input.oninput = () => {
      s.draft = input.value; chainControls();
      $('chain-status').textContent = 'Bản nháp đã đổi; bấm sửa và kiểm tra để backend kiểm tra ngay. Bằng chứng đã ghi giữ nguyên.';
    };
    const recompute = chainText(form, 'button', 'Tính lại dấu vân tay và Merkle');
    recompute.id = 'chain-recompute'; recompute.type = 'button'; recompute.className = 'secondary';
    chainText(form, 'p', '').id = 'chain-recompute-reason';
    recompute.onclick = () => chainLabAction('recompute');
    chainText(form, 'p', 'Tính lại là thao tác riêng: đổi tx_id, Merkle và hash của khối này; không ký lại, đào lại hay sửa liên kết phía sau.');
  }
  const evidence = $('chain-evidence');
  if (data.change) {
    const details = document.createElement('details'); details.open = true; evidence.append(details);
    chainText(details, 'summary', `Trước / sau — Block #${data.change.height}`);
    chainText(details, 'pre', `${data.change.before.transaction.payload.lab_data} → ${data.change.after.transaction.payload.lab_data}`);
    const technical = document.createElement('details'); details.append(technical);
    chainText(technical, 'summary', 'Hash, Merkle, nonce và chữ ký trước / sau');
    chainText(technical, 'pre', JSON.stringify(data.change, null, 2));
  }
  if (data.mining) {
    const details = document.createElement('details'); evidence.append(details);
    chainText(details, 'summary', 'Ứng viên và số liệu đào thực tế (kể cả chưa hoàn tất)');
    chainText(details, 'pre', JSON.stringify({ mining: data.mining, candidate: data.candidate }, null, 2));
    chainText(summary, 'p', 'Nonce là giá trị trong header; số lần băm là lượng công việc backend đã đo, không phải nonce. Thời gian không đo điện năng.');
  }
  chainControls();
}

async function chainLabAction(action, event) {
  event?.preventDefault();
  const s = chainLab;
  if (s.busy || (action !== 'init' && !s.result) || (action === 'init' && s.result)) return;
  if (['edit', 'recompute'].includes(action) && !s.selected) return;
  let body = action === 'init' ? {} : { chain: s.result.chain };
  const previousLength = s.result?.chain.length || 0;
  if (action === 'add') Object.assign(body, { data: $('chain-data').value,
    difficulty: Number($('chain-difficulty').value), version: Number($('chain-version').value),
    timestamp: $('chain-timestamp').value.trim() || null });
  if (['edit', 'recompute'].includes(action)) body.height = s.selected;
  if (action === 'edit') body.data = s.draft;
  s.busy = true; labError('chain-error');
  $('chain-status').textContent = action === 'add' ? '⏳ Backend đang tính hash và tìm nonce có giới hạn; chỉ thêm khối khi đạt PoW…'
    : action === 'init' ? 'Đang khởi tạo genesis của lab…' : 'Backend đang kiểm tra chuỗi riêng của lab…';
  showChainLab();
  try {
    const data = await labPost('/blockchain/' + action, body);
    if (s !== chainLab) return;
    s.result = data;
    if (action === 'add') {
      s.selected = 0;
      if (data.mining?.completed && data.chain.length > previousLength) s.lastAdded = data.chain.at(-1).height;
    }
    s.draft = data.chain[s.selected]?.transaction?.payload.lab_data || '';
    $('chain-status').textContent = data.mining && !data.mining.completed ? 'Đào chưa hoàn tất trong giới hạn; ứng viên chưa được thêm vào chuỗi.'
      : data.validation.valid ? 'Chuỗi đã được kiểm tra. Thêm khối hoặc chọn thẻ khối để thử sửa.'
      : 'Phát hiện lỗi thật. Không tự ký lại, đào lại hay sửa các liên kết phía sau.';
  } catch (error) {
    if (s === chainLab) {
      labError('chain-error', error.message);
      $('chain-status').textContent = 'Thao tác không thành công; chuỗi trước đó được giữ nguyên.';
    }
  } finally { if (s === chainLab) { s.busy = false; showChainLab(); } }
}

function resetChainLab(initialize = true) {
  chainLab = freshChainLab(); $('chain-data').value = ''; $('chain-difficulty').value = '2';
  $('chain-version').value = '1'; $('chain-timestamp').value = '';
  labError('chain-error'); showChainLab();
  $('chain-status').textContent = 'Đã đặt lại riêng lab Khối & Chuỗi khối. Các lab khác và mạng có hướng dẫn giữ nguyên.';
  if (initialize) chainLab.initialization = chainLabAction('init');
}

function freshComparison() { return { mode: 'pow', busy: false, results: { pow: null, pos: null } }; }
let comparison = freshComparison();

function showComparison() {
  const c = comparison;
  formBusy('comparison-form', c.busy);
  $('comparison-pow').checked = c.mode === 'pow'; $('comparison-pos').checked = c.mode === 'pos';
  $('comparison-submit').textContent = c.busy ? 'Đang tạo block thật trên backend…' : `Chạy ${c.mode === 'pow' ? 'PoW' : 'PoS'} trên mạng lab riêng`;
  $('comparison-method').textContent = c.mode === 'pow' ? 'PoW: tìm hash đạt mục tiêu' : 'PoS: chọn validator để ký block';
  $('comparison-method-note').textContent = c.mode === 'pow'
    ? 'Backend tăng nonce cho đến khi hash đạt độ khó. Không có mining giả trong trình duyệt.'
    : 'Backend chọn validator đủ điều kiện theo trọng số stake. Người dùng không chọn validator thủ công.';
  for (const mode of ['pow', 'pos']) {
    const data = c.results[mode], panel = $('comparison-result-' + mode);
    panel.hidden = !data; panel.replaceChildren();
    if (!data) continue;
    panel.className = 'result ' + (data.created ? 'valid' : 'invalid');
    const heading = document.createElement('h2');
    heading.textContent = `${mode === 'pow' ? 'PoW' : 'PoS'} · ${data.created ? 'Đã tạo block #' + data.block.height : 'Chưa tạo block'}`;
    panel.append(heading);
    function line(text) { const p = document.createElement('p'); p.textContent = text; panel.append(p); }
    line(`${data.node_id} · ${data.node_status} · ${data.transaction_ids.length} giao dịch trong block · ${data.pending_count} giao dịch còn chờ trước khi dọn mạng lab.`);
    if (!data.created) line(`Backend từ chối ở ${data.stage === 'submission' ? 'bước gửi giao dịch' : 'bước tạo block'}: ${data.reason}`);
    const metrics = document.createElement('div'); metrics.className = 'result-metrics'; panel.append(metrics);
    resultMetric(metrics, mode === 'pos' ? 'Thời gian tạo block' : 'Thời gian', data.seconds, 'giây', 4);
    if (data.created && mode === 'pow') {
      resultMetric(metrics, 'Nonce tìm được', data.block.nonce, 'nonce');
      resultMetric(metrics, 'Số lần thử', data.attempts, 'lần băm');
      line(`Độ khó: ${data.block.difficulty}`);
      powHash(panel, data.block.hash, data.block.difficulty);
    }
    line(`Ví phát hành — ký hồ sơ: ${data.issuer.name} · ${shortHash(data.issuer.address)}`);
    if (data.created && mode === 'pos' && data.signer) {
      line(`Validator tạo block — ký block: ${data.signer.name} · ${shortHash(data.signer.address)}`);
      line(`Stake: ${data.signer.stake} · Trọng số lựa chọn: ${(data.signer.selection_weight * 100).toFixed(1)}%.`);
    }
    line(`Chuỗi lab: ${data.chain_valid ? 'hợp lệ' : 'không hợp lệ'} — ${data.validity_reason}`);
    const details = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
    details.className = 'technical';
    summary.textContent = 'Chi tiết kỹ thuật — hash, khóa, chữ ký, seed và thời gian chính xác';
    pre.textContent = JSON.stringify(data, null, 2); details.append(summary, pre); panel.append(details);
  }
}

async function runComparison(event) {
  event.preventDefault(); const c = comparison;
  if (c.busy) return;
  const mode = c.mode;
  const body = { mode, holder_name: $('comparison-holder').value, title: $('comparison-title').value,
    issue_date: $('comparison-date').value, node_online: $('comparison-online').checked,
    include_sample: $('comparison-sample').checked };
  c.busy = true; c.results[mode] = null; labError('comparison-error'); showComparison();
  $('comparison-status').textContent = 'Đang tạo mạng tạm, ký/gửi mẫu và gọi backend. Không thay đổi phiên journey.';
  try {
    const data = await labPost('/consensus/run', body);
    if (comparison !== c) return;
    c.results[mode] = data;
    $('comparison-status').textContent = data.created ? 'Đã tạo block và dọn worker lab. Giữ nguyên mẫu rồi thử chế độ còn lại.'
      : 'Chưa tạo block; đọc lý do backend bên dưới. Lượt mới dùng một mạng lab mới.';
  } catch (error) {
    if (comparison === c) { labError('comparison-error', error.message); $('comparison-status').textContent = 'Không nhận được kết quả. Có thể thử lại trên một mạng lab mới.'; }
  } finally { if (comparison === c) { c.busy = false; showComparison(); } }
}

function resetComparison() {
  comparison = freshComparison();
  $('comparison-holder').value = 'Người học DEMO-001'; $('comparison-title').value = 'Chứng chỉ Phân tích dữ liệu';
  $('comparison-date').value = '2026-01-01'; $('comparison-online').checked = $('comparison-sample').checked = true;
  labError('comparison-error'); showComparison();
  $('comparison-status').textContent = 'Đã reset riêng lab PoW–PoS. Kết quả muộn bị bỏ qua; server tự dọn mạng tạm.';
}

// A handle belongs only to this lab. Reset/page exit invalidates late responses.
function freshNetworkLab() {
  return { handle: null, snapshot: null, busy: false, mutating: false, abort: null, pollFailed: false };
}
let networkLab = freshNetworkLab();
const networkPath = s => `/network/${encodeURIComponent(s.handle)}`;

function showNetworkLab() {
  const s = networkLab, data = s.snapshot;
  $('network-init').disabled = s.busy || !!s.handle;
  $('network-reset').disabled = s.mutating || !s.handle;
  ['refresh', 'sync'].forEach(action => { $('network-' + action).disabled = s.busy || !s.handle; });
  const node3 = data?.nodes.find(n => n.node_id === 'Node-3');
  $('network-offline').disabled = s.busy || !node3 || node3.status === 'OFFLINE';
  $('network-online').disabled = s.busy || !node3 || node3.status === 'ONLINE';
  $('network-mine').disabled = s.busy || !s.handle || !!data?.mining;
  $('network-control-note').textContent = s.busy ? 'Đang chờ kết quả thực; các thao tác mạng tạm khóa.'
    : !s.handle ? 'Khởi tạo mạng trước để mở các nút điều khiển Node-3 và tạo block.'
    : data?.mining ? 'Mẫu này đã có một block. Thử bật/tắt Node-3, làm mới hoặc đồng bộ; đặt lại lab để tạo mẫu mới.'
    : 'Thử tắt Node-3 trước khi tạo block. Nút Bật/Tắt chỉ khả dụng khi node đang ở trạng thái ngược lại.';
  const summary = $('network-summary');
  summary.className = 'result';
  summary.textContent = !data ? 'Chưa có mạng lab. Khởi tạo để xem ba node ở block genesis.'
    : s.pollFailed ? 'Chưa xác nhận hoàn tất trong thời hạn. Các thẻ bên dưới là trạng thái cuối đã đọc; hãy làm mới.'
    : data.all_nodes_synchronized ? '✓ Cả ba node ONLINE: cùng chiều cao và tip hash, các chuỗi hợp lệ.'
    : data.online_nodes_synchronized ? 'Các node ONLINE đồng thuận về chiều cao và tip hash, chuỗi hợp lệ. Chưa đồng bộ cả ba node.'
    : !data.online_nodes_valid ? 'Có chuỗi ONLINE không hợp lệ. Xem lý do backend trong chi tiết.'
    : 'Các node ONLINE chưa có cùng chiều cao và tip hash; đang quan sát trạng thái thực.';
  if (data?.all_nodes_synchronized && !s.pollFailed) summary.className += ' valid';
  showLabNodes('network-nodes', data?.nodes || []);
  $('network-technical').textContent = data ? JSON.stringify(data, null, 2) : '';
  $('network-credential').textContent = data?.mining
    ? `Đã tạo block #${data.mining.block.height} bằng PoW trên Node-1. Độ khó ${data.mining.block.difficulty}; hồ sơ ${data.credential_id}.`
    : data?.transaction ? 'Hồ sơ mẫu đã ký; chưa tạo được block. Giao dịch được giữ để thử lại.'
    : 'Thử: tắt Node-3 → tạo block → quan sát NOT_FOUND trên node offline → bật lại Node-3.';
}

function showLabNodes(id, nodes) {
  const container = $(id); container.replaceChildren();
  for (const node of nodes) {
    const card = document.createElement('article'); card.className = 'panel';
    const heading = document.createElement('h2'); heading.textContent = `${node.node_id} · ${node.status === 'ONLINE' ? 'Đang bật' : 'Offline'}`;
    card.append(heading);
    function line(text) { const p = document.createElement('p'); p.textContent = text; card.append(p); }
    line(`Chiều cao: ${node.height} · ${node.block_count} block (gồm genesis)`);
    line(`Tip: ${shortHash(node.tip_hash)} · Giao dịch chờ: ${node.pending_count}`);
    line(`Chuỗi: ${node.chain_valid ? '✓ Hợp lệ' : '✗ Không hợp lệ'}`);
    line(node.verification ? `Hồ sơ: ${node.verification.status}` : 'Chưa có hồ sơ mẫu để xác minh.');
    if (node.local_title != null) line(`Tiêu đề trong bản sao cục bộ: ${node.local_title}`);
    if (node.local_chain_warning) line(node.local_chain_warning);
    const details = document.createElement('details'), label = document.createElement('summary'), pre = document.createElement('pre');
    label.textContent = 'Chi tiết kỹ thuật — tip đầy đủ, lý do và các bước xác minh';
    pre.textContent = JSON.stringify(node, null, 2); details.append(label, pre); card.append(details); container.append(card);
  }
}

async function readNetworkLab(s, timeout = 2000, path = networkPath(s)) {
  const controller = new AbortController(); s.abort = controller;
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await labResponse(await fetch(LAB_API + path, { signal: controller.signal }));
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Hết thời gian đọc trạng thái mạng. Hãy làm mới.');
    throw error;
  } finally { clearTimeout(timer); if (s.abort === controller) s.abort = null; }
}

async function pollNetworkLab(s, complete, {
  isCurrent = () => s === networkLab, render = showNetworkLab, path = networkPath(s)
} = {}) {
  const deadline = Date.now() + 5000;
  while (isCurrent() && Date.now() < deadline) {
    let data;
    try { data = await readNetworkLab(s, Math.min(2000, deadline - Date.now()), path); }
    catch (error) { if (isCurrent()) s.pollFailed = true; throw error; }
    if (!isCurrent()) return false;
    s.snapshot = data; render();
    if (complete(data)) return true;
    const remaining = deadline - Date.now();
    if (remaining > 0) await new Promise(resolve => setTimeout(resolve, Math.min(250, remaining)));
  }
  if (!isCurrent()) return false;
  s.pollFailed = true;
  throw new Error('Hết thời gian chờ truyền/đồng bộ block (tối đa 5 giây). Chưa xác nhận hoàn tất; hãy làm mới.');
}

async function networkLabAction(action) {
  const s = networkLab;
  if (s.busy || (action === 'init' ? s.handle : !s.handle)) return;
  s.busy = true; s.mutating = action !== 'refresh'; s.pollFailed = false;
  showNetworkLab(); labError('network-error');
  $('network-status').textContent = action === 'mine' ? 'Đang ký/gửi hồ sơ mẫu và mining PoW thật trên Node-1…' : 'Đang chờ backend…';
  try {
    let data;
    if (action === 'init') data = await labPost('/network');
    else if (action === 'refresh') data = await readNetworkLab(s);
    else if (action === 'offline' || action === 'online') data = await labPost(networkPath(s) + '/nodes/Node-3/status', { online: action === 'online' });
    else data = await labPost(networkPath(s) + '/' + action);
    if (s !== networkLab) {
      if (action === 'init') await labPost(`/network/${encodeURIComponent(data.lab_handle)}/reset`);
      return;
    }
    s.handle = action === 'init' ? data.lab_handle : s.handle;
    s.snapshot = data.snapshot || data; s.mutating = false;
    if (action === 'mine') {
      if (!data.mined) throw new Error(data.reason);
      const block = data.block;
      $('network-status').textContent = `Đã tạo block #${block.height}; đang đọc trạng thái truyền tới Node-2…`;
      await pollNetworkLab(s, snapshot => ['Node-1', 'Node-2'].every(id => snapshot.nodes.some(n =>
        n.node_id === id && n.status === 'ONLINE' && n.height === block.height && n.tip_hash === block.hash
        && n.chain_valid && n.verification?.status === 'VERIFIED')));
    } else if (action === 'online' || action === 'sync') {
      if (action === 'sync' && !data.completed && !s.snapshot.online_nodes_valid) {
        s.pollFailed = true;
        throw new Error(data.reason);
      }
      $('network-status').textContent = action === 'online'
        ? 'go_online() đã yêu cầu catch-up qua hàng đợi. Đang quan sát, không gửi thêm yêu cầu sync…'
        : 'Backend đã sync các node ONLINE; node offline giữ nguyên. Đang kiểm tra trạng thái…';
      const expectAll = action === 'online' || s.snapshot.nodes.every(n => n.status === 'ONLINE');
      await pollNetworkLab(s, snapshot => (expectAll ? snapshot.all_nodes_synchronized : snapshot.online_nodes_synchronized)
        && snapshot.nodes.filter(n => n.status === 'ONLINE').every(n => !snapshot.credential_id || n.verification?.status === 'VERIFIED'));
    }
    if (s !== networkLab) return;
    $('network-status').textContent = action === 'init' ? 'Đã khởi tạo ba node lab ở genesis. Hãy tắt Node-3 trước khi tạo block.'
      : action === 'offline' ? 'Node-3 đã offline. Chain của node vẫn giữ nguyên; node không nhận block mới.'
      : action === 'mine' ? 'Node-1/2 đã nhận và xác minh block mới. Xem trạng thái thực của Node-3 bên dưới.'
      : action === 'refresh' ? 'Đã đọc snapshot thực; mỗi node được khóa riêng, đây không phải snapshot nguyên tử toàn mạng.'
      : s.snapshot.all_nodes_synchronized ? 'Đã quan sát cả ba node ONLINE cùng chiều cao/tip và các chuỗi hợp lệ.'
      : 'Chỉ các node ONLINE đã đồng bộ. Node-3 vẫn offline; hãy bật node để catch-up.';
  } catch (error) {
    if (s === networkLab) {
      labError('network-error', error.message);
      $('network-status').textContent = 'Thao tác chưa hoàn tất. Đọc lỗi và làm mới trạng thái trước khi thử lại.';
      if (error.status === 404) { s.handle = null; s.snapshot = null; }
    }
  } finally { if (s === networkLab) { s.busy = s.mutating = false; showNetworkLab(); } }
}

async function resetNetworkLab() {
  const old = networkLab;
  if (old.mutating || !old.handle) return;
  old.abort?.abort(); networkLab = freshNetworkLab();
  const s = networkLab; s.busy = s.mutating = true;
  showNetworkLab(); labError('network-error'); $('network-status').textContent = 'Đang dừng worker và reset riêng mạng lab…';
  try {
    await labPost(networkPath(old) + '/reset');
    if (s === networkLab) $('network-status').textContent = 'Đã dọn mạng lab. Khởi tạo để thử lại; journey và các lab khác giữ nguyên.';
  } catch (error) {
    if (s === networkLab) labError('network-error', `Đã xóa trạng thái cục bộ; chưa xác nhận dọn worker: ${error.message}. Mạng sẽ tự hết hạn sau tối đa 15 phút.`);
  } finally { if (s === networkLab) { s.busy = s.mutating = false; showNetworkLab(); } }
}

let tamperLab = freshNetworkLab();
const tamperPath = s => `/tamper/${encodeURIComponent(s.handle)}`;
async function closeTamperLab(s) {
  return labResponse(await fetch(LAB_API + tamperPath(s), { method: 'DELETE', keepalive: true }));
}

function showTamperLab() {
  const s = tamperLab, data = s.snapshot;
  $('tamper-create').disabled = s.busy || !!s.handle;
  $('tamper-reset').disabled = s.mutating || !s.handle;
  $('tamper-refresh').disabled = s.busy || !s.handle;
  $('tamper-sync').disabled = s.busy || !s.handle || data?.edited_title == null;
  $('tamper-input').disabled = s.busy || !data?.ready;
  const title = $('tamper-input').value.trim();
  $('tamper-edit').disabled = s.busy || !data?.ready || !title || title === data.original_title;
  $('tamper-control-note').textContent = s.busy ? 'Đang chờ backend; chưa thể sửa hoặc phục hồi lần nữa.'
    : !s.handle ? 'Tạo chuỗi mẫu trước để mở phần sửa dữ liệu.'
    : !data?.ready ? 'Đọc kết quả các node. Nếu đã sửa, bấm Đồng bộ để phục hồi; nếu chưa sẵn sàng, bấm Kiểm tra các node.'
    : !title || title === data.original_title ? 'Nhập tiêu đề không trống, khác bản gốc để mở nút Sửa. Phục hồi chỉ mở sau khi đã sửa.'
    : 'Có thể sửa riêng Node-2 rồi đọc kết quả. Đồng bộ để phục hồi chỉ mở sau khi đã sửa.';
  const summary = $('tamper-summary'); summary.className = 'result';
  summary.textContent = !data ? 'Chưa có chuỗi mẫu. Tạo chuỗi để xác minh hồ sơ trên cả ba node.'
    : s.pollFailed ? 'Chưa xác nhận hoàn tất trong thời hạn. Đây là trạng thái cuối đã đọc; hãy kiểm tra lại.'
    : data.restored && data.ready ? '✓ Đã phục hồi từ peer: cả ba chuỗi hợp lệ, cùng tip và hồ sơ VERIFIED với tiêu đề gốc.'
    : data.ready ? '✓ Chuỗi mẫu sẵn sàng: cả ba chuỗi hợp lệ, cùng tip và hồ sơ VERIFIED.'
    : data.tampered ? '✗ Bản sao Node-2 đã bị sửa. Đọc kết quả kiểm tra thật bên dưới; chưa yêu cầu phục hồi.'
    : 'Chưa xác nhận chuỗi mẫu sẵn sàng. Kiểm tra các node và lý do backend.';
  if (data?.ready && !s.pollFailed) summary.className += ' valid';
  else if (data?.tampered) summary.className += ' invalid';
  $('tamper-original').textContent = data?.original_title || 'Chưa có tiêu đề gốc.';
  $('tamper-local').textContent = data?.nodes.find(n => n.node_id === 'Node-2')?.local_title || 'Chưa đọc được bản sao Node-2.';
  $('tamper-credential').textContent = data?.credential_id ? `Hồ sơ mẫu: ${data.credential_id}` : '';
  $('tamper-reason').textContent = data?.reason || '';
  showLabNodes('tamper-nodes', data?.nodes || []);
  $('tamper-technical').textContent = data ? JSON.stringify(data, null, 2) : '';
}

async function tamperLabAction(action) {
  const s = tamperLab;
  if (s.busy || (action === 'create' ? s.handle : !s.handle)) return;
  if (action === 'edit' && (!s.snapshot?.ready || !$('tamper-input').value.trim()
      || $('tamper-input').value.trim() === s.snapshot.original_title)) return;
  if (action === 'sync' && s.snapshot?.edited_title == null) return;
  s.busy = true; s.mutating = action !== 'refresh'; s.pollFailed = false;
  showTamperLab(); labError('tamper-error');
  $('tamper-status').textContent = action === 'create' ? 'Đang ký/gửi mẫu và mining PoW thật trên Node-1…'
    : action === 'sync' ? 'Đang yêu cầu backend phục hồi qua peer hợp lệ…' : 'Đang chờ backend…';
  try {
    const data = action === 'create' ? await labPost('/tamper')
      : action === 'refresh' ? await readNetworkLab(s, 2000, tamperPath(s))
      : await labPost(tamperPath(s) + '/' + action, action === 'edit' ? { title: $('tamper-input').value } : undefined);
    if (s !== tamperLab) {
      if (action === 'create') await closeTamperLab({ handle: data.lab_id });
      return;
    }
    if (action === 'create') s.handle = data.lab_id;
    s.snapshot = data; s.mutating = false;
    if (action === 'create') {
      if (!data.prepared) throw new Error(data.reason);
      $('tamper-input').value = `${data.original_title} (đã sửa)`;
    }
    if (action === 'create' || action === 'sync') {
      $('tamper-status').textContent = 'Đang đọc trạng thái thực, tối đa 5 giây. Không giữ khóa backend khi chờ peer.';
      await pollNetworkLab(s, snapshot => snapshot.ready && (action !== 'sync' || snapshot.restored), {
        isCurrent: () => s === tamperLab, render: showTamperLab, path: tamperPath(s)
      });
    }
    if (s !== tamperLab) return;
    $('tamper-status').textContent = action === 'create' ? 'Chuỗi mẫu đã sẵn sàng. Thử đổi tiêu đề trên bản sao Node-2.'
      : action === 'edit' ? 'Đã sửa riêng payload Node-2 và chạy kiểm tra backend. Không re-sign, re-hash hay tự đồng bộ.'
      : action === 'sync' ? 'Đã xác nhận phục hồi tiêu đề gốc từ peer hợp lệ, VERIFIED trên cả ba node.'
      : 'Đã đọc các validator và verifier thật. Kiểm tra không tự phục hồi dữ liệu.';
  } catch (error) {
    if (s === tamperLab) {
      labError('tamper-error', error.message);
      $('tamper-status').textContent = 'Chưa hoàn tất. Đọc lỗi và kiểm tra lại; không báo thành công khi chưa xác nhận.';
      if (error.status === 404) { s.handle = null; s.snapshot = null; $('tamper-status').textContent = 'Lab không còn tồn tại hoặc đã hết hạn. Hãy tạo chuỗi mẫu mới.'; }
    }
  } finally { if (s === tamperLab) { s.busy = s.mutating = false; showTamperLab(); } }
}

async function resetTamperLab() {
  const old = tamperLab;
  if (old.mutating || !old.handle) return;
  old.abort?.abort(); tamperLab = freshNetworkLab();
  const s = tamperLab; s.busy = s.mutating = true;
  $('tamper-input').value = ''; labError('tamper-error'); showTamperLab();
  $('tamper-status').textContent = 'Đang dừng worker và reset riêng lab sửa dữ liệu…';
  try {
    await closeTamperLab(old);
    if (s === tamperLab) $('tamper-status').textContent = 'Đã reset riêng lab này. Journey và các lab khác giữ nguyên.';
  } catch (error) {
    if (s === tamperLab) labError('tamper-error', `Đã xóa trạng thái cục bộ; chưa xác nhận dọn worker: ${error.message}. Mạng tự hết hạn sau tối đa 15 phút.`);
  } finally { if (s === tamperLab) { s.busy = s.mutating = false; showTamperLab(); } }
}

(function setupLabs() {
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    $('theme-toggle').textContent = theme === 'light' ? 'Chế độ tối' : 'Chế độ sáng';
    $('theme-toggle').setAttribute('aria-pressed', String(theme === 'light'));
    try { localStorage.setItem('trustmebro-theme', theme); } catch {}
  }
  function restoreTheme() {
    try { applyTheme(localStorage.getItem('trustmebro-theme') === 'light' ? 'light' : 'dark'); }
    catch { applyTheme(document.documentElement.dataset.theme || 'dark'); }
  }
  $('theme-toggle').onclick = () => applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  window.addEventListener('pageshow', restoreTheme); restoreTheme();
  function route(focus) {
    const labs = ['sha', 'signatures', 'merkle', 'blocks', 'consensus', 'network', 'tamper'];
    const requested = ['block', 'blockchain'].includes(location.hash.slice(1)) ? 'blocks' : location.hash.slice(1);
    const name = labs.includes(requested) ? requested : 'sha';
    labs.forEach(id => { $('lab-' + id).hidden = id !== name; });
    document.querySelectorAll('[data-lab]').forEach(a => {
      if (a.dataset.lab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.title = `${name === 'sha' ? 'SHA-256' : name === 'merkle' ? 'Cây Merkle' : name === 'blocks' ? 'Khối & Chuỗi khối' : name === 'consensus' ? 'PoW–PoS' : name === 'network' ? 'Đồng bộ mạng' : name === 'tamper' ? 'Sửa dữ liệu' : 'Chữ ký số'} — TrustMeBro`;
    if (focus) $(name + '-title').focus();
    if (name === 'blocks' && !chainLab.result && !chainLab.busy) chainLab.initialization = chainLabAction('init');
  }
  window.addEventListener('hashchange', () => route(true));
  for (const [index, name] of ['theory', 'practice'].entries()) {
    const button = $('sha-tab-' + name);
    button.onclick = () => showShaTab(name);
    button.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 'theory' : event.key === 'End' ? 'practice'
        : ['theory', 'practice'][1 - index];
      showShaTab(next); $('sha-tab-' + next).focus();
    };
  }
  for (let i = 0; i < 5; i++) $('sha-topic-' + i).onclick = () => selectShaTopic(i);
  $('sha-previous').onclick = () => selectShaTopic(shaTopic - 1);
  $('sha-next').onclick = () => shaTopic === 4 ? showShaTab('practice', true) : selectShaTopic(shaTopic + 1);
  showShaTab('theory'); selectShaTopic(0);
  setupLabLearning();
  $('hash-form').onsubmit = compareHashes; $('hash-reset').onclick = resetHash;
  ['hash-a', 'hash-b'].forEach(id => { $(id).oninput = () => {
    $('hash-status').textContent = 'Nội dung đã đổi. Bấm tính lại để cập nhật kết quả.';
    if (!$('hash-result').hidden) $('hash-result-context').textContent = 'Đầu vào đã đổi — số liệu bên dưới thuộc lần tính trước. Bấm tính lại để cập nhật.';
  }; });
  $('sig-create').onclick = () => signatureAction('create'); $('sig-other').onclick = () => signatureAction('other');
  $('signature-form').onsubmit = event => signatureAction('sign', event);
  $('sig-original').onclick = () => signatureAction('original'); $('sig-verify').onclick = () => signatureAction('verify');
  $('sig-reset').onclick = resetSignature;
  ['sig-presented', 'sig-key-choice'].forEach(id => { $(id).oninput = () => { signature.result = null; showSignature(); $('sig-status').textContent = 'Bản xuất trình hoặc khóa kiểm tra đã đổi. Chữ ký gốc vẫn giữ nguyên.'; }; });
  $('merkle-form').onsubmit = computeMerkle; $('merkle-reset').onclick = resetMerkle;
  $('merkle-leaves').oninput = () => { updateProofChoices(); $('merkle-status').textContent = 'Lá đã đổi — cây và root đang hiển thị thuộc lần tính trước. Bấm tính lại để cập nhật và so sánh các node.'; };
  for (const [id, text] of [['merkle-one', 'Hồ sơ An'], ['merkle-odd', 'Hồ sơ An\nHồ sơ Bình\nHồ sơ Chi'], ['merkle-empty', '']]) {
    $(id).onclick = () => { if (merkleBusy) return; fillLabExample('merkle-leaves', text); };
  }
  $('comparison-form').onsubmit = runComparison; $('comparison-reset').onclick = resetComparison;
  $('chain-init').onclick = () => chainLabAction('init');
  $('chain-form').onsubmit = event => chainLabAction('add', event);
  $('chain-difficulty').onchange = chainControls;
  $('chain-validate').onclick = () => chainLabAction('validate');
  $('chain-reset').onclick = () => resetChainLab();
  $('chain-example').onclick = () => { if (!chainLab.busy) fillLabExample('chain-data', 'Ghi chú của tôi: mỗi block nối với block trước.'); };
  resetChainLab(false);
  for (const mode of ['pow', 'pos']) {
    $('comparison-' + mode).onchange = () => {
      if (comparison.busy) return;
      comparison.mode = mode; labError('comparison-error'); showComparison();
    };
  }
  ['holder', 'title', 'date', 'online', 'sample'].forEach(field => {
    $('comparison-' + field).oninput = () => {
      if (comparison.busy) return;
      comparison.results = { pow: null, pos: null }; labError('comparison-error'); showComparison();
      $('comparison-status').textContent = 'Mẫu hoặc điều kiện đã đổi; kết quả cũ được xóa. Chạy lại cả hai chế độ để đối chiếu.';
    };
  });
  showComparison();
  ['init', 'offline', 'online', 'mine', 'refresh', 'sync'].forEach(action => {
    $('network-' + action).onclick = () => networkLabAction(action);
  });
  $('network-reset').onclick = resetNetworkLab; showNetworkLab();
  ['create', 'refresh', 'sync'].forEach(action => {
    $('tamper-' + action).onclick = () => tamperLabAction(action);
  });
  $('tamper-form').onsubmit = event => { event.preventDefault(); return tamperLabAction('edit'); };
  $('tamper-input').oninput = showTamperLab;
  $('tamper-reset').onclick = resetTamperLab; showTamperLab();
  window.addEventListener('pagehide', () => {
    resetChainLab(false);
    const oldTamper = tamperLab; oldTamper.abort?.abort(); tamperLab = freshNetworkLab(); showTamperLab();
    $('tamper-status').textContent = 'Đã rời trang; tạo chuỗi mẫu mới để tiếp tục.';
    if (oldTamper.handle) closeTamperLab(oldTamper).catch(() => {});
    const oldNetwork = networkLab; oldNetwork.abort?.abort(); networkLab = freshNetworkLab(); showNetworkLab();
    $('network-status').textContent = 'Đã rời trang; khởi tạo mạng lab mới để tiếp tục.';
    if (oldNetwork.handle) navigator.sendBeacon(LAB_API + networkPath(oldNetwork) + '/reset');
    comparison = freshComparison(); showComparison();
    const old = signature; signature = freshSignature(); showSignature();
    $('sig-status').textContent = 'Đã rời trang; tạo khóa tạm mới để ký tiếp.';
    [old.key, old.other].filter(Boolean).forEach(k => navigator.sendBeacon(`${LAB_API}/signatures/keys/${encodeURIComponent(k.key_handle)}/reset`));
  });
  showSignature(); updateProofChoices(); route(false);
})();
