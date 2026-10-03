// These exercises never call journey wallet, credential, mining or reset APIs.
const $ = id => document.getElementById(id);
const LAB_API = '/api/labs';

async function labPost(path, body) {
  const response = await fetch(LAB_API + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.map(e => e.msg).join('; ')
      : typeof detail === 'string' ? detail : detail?.message || `Lỗi HTTP ${response.status}`);
  }
  return data;
}

function labError(id, message = '') { $(id).textContent = message; $(id).hidden = !message; }
function formBusy(id, busy) { $(id).querySelectorAll('input,textarea,select,button').forEach(e => { e.disabled = busy; }); }
const shortHash = value => value.slice(0, 12) + '…' + value.slice(-8);

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
    $('hash-difference').textContent = `${bits}/256 bit khác nhau (${(bits / 256 * 100).toFixed(2)}%).`;
    $('hash-result').hidden = false;
    $('hash-status').textContent = 'Đã tính hai hash thật cho nội dung tại thời điểm bấm nút.';
  } catch (error) { if (token === hashToken) labError('hash-error', error.message); }
  finally { if (token === hashToken) { hashBusy = false; formBusy('hash-form', false); } }
}
function resetHash() {
  hashToken++; hashBusy = false; formBusy('hash-form', false);
  $('hash-a').value = ''; $('hash-b').value = '';
  ['hash-original', 'hash-edited', 'hash-difference'].forEach(id => { $(id).textContent = ''; });
  $('hash-result').hidden = true; $('hash-status').textContent = 'Đã reset riêng lab SHA-256.';
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
    $('sig-result').textContent = `${s.result.valid ? '✓ Chữ ký hợp lệ' : '✗ Chữ ký không hợp lệ'} — ${s.result.label}. Backend đã kiểm tra bằng khóa công khai đã chọn.`;
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

function showMerkle(data, previous, count) {
  $('merkle-result').hidden = false; $('merkle-root').textContent = data.root;
  $('merkle-summary').textContent = `${count} lá · ${previous ? previous.root === data.root ? 'Root giữ nguyên' : 'Root đã thay đổi' : 'Đã tính root'}.`;
  const container = $('merkle-tree'); container.replaceChildren();
  if (!count) { const note = document.createElement('p'); note.textContent = 'Không có lá. Backend trả về một tầng chứa root của cây rỗng.'; container.append(note); }
  data.levels.forEach((level, l) => {
    const heading = document.createElement('p'); heading.className = 'level-title';
    heading.textContent = `Tầng ${l}${l === 0 && count ? ' / Lá' : l === data.levels.length - 1 ? ' / Root' : ''}`;
    container.append(heading);
    const row = document.createElement('div'); row.className = 'tree-level';
    level.forEach((hash, i) => {
      const node = document.createElement('div'), changed = previous && previous.levels[l]?.[i] !== hash;
      node.className = 'tree-node' + (changed ? ' changed' : '');
      const details = document.createElement('details'), summary = document.createElement('summary'), code = document.createElement('code');
      summary.textContent = `${i + 1} · ${shortHash(hash)}`;
      code.textContent = hash; details.append(summary, code); node.append(details);
      if (changed) { const label = document.createElement('small'); label.textContent = 'Đổi / mới'; node.append(label); }
      if (count && i >= Math.ceil(count / (2 ** l))) { const label = document.createElement('small'); label.textContent = 'Bản sao ghép cặp từ backend'; node.append(label); }
      row.append(node);
    });
    container.append(row);
  });
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
    showMerkle(data, merklePrevious, leaves.length); merklePrevious = data;
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
    const name = ['sha', 'signatures', 'merkle'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'sha';
    ['sha', 'signatures', 'merkle'].forEach(id => { $('lab-' + id).hidden = id !== name; });
    document.querySelectorAll('[data-lab]').forEach(a => {
      if (a.dataset.lab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.title = `${name === 'sha' ? 'SHA-256' : name === 'merkle' ? 'Cây Merkle' : 'Chữ ký số'} — TrustMeBro`;
    if (focus) $(name + '-title').focus();
  }
  window.addEventListener('hashchange', () => route(true)); route(false);
  $('hash-form').onsubmit = compareHashes; $('hash-reset').onclick = resetHash;
  ['hash-a', 'hash-b'].forEach(id => { $(id).oninput = () => { $('hash-status').textContent = 'Nội dung đã đổi. Bấm tính lại để cập nhật kết quả.'; }; });
  $('sig-create').onclick = () => signatureAction('create'); $('sig-other').onclick = () => signatureAction('other');
  $('signature-form').onsubmit = event => signatureAction('sign', event);
  $('sig-original').onclick = () => signatureAction('original'); $('sig-verify').onclick = () => signatureAction('verify');
  $('sig-reset').onclick = resetSignature;
  ['sig-presented', 'sig-key-choice'].forEach(id => { $(id).oninput = () => { signature.result = null; showSignature(); $('sig-status').textContent = 'Bản xuất trình hoặc khóa kiểm tra đã đổi. Chữ ký gốc vẫn giữ nguyên.'; }; });
  $('merkle-form').onsubmit = computeMerkle; $('merkle-reset').onclick = resetMerkle;
  $('merkle-leaves').oninput = () => { updateProofChoices(); $('merkle-status').textContent = 'Lá đã đổi. Bấm tính lại để so sánh các node.'; };
  for (const [id, text] of [['merkle-one', 'Hồ sơ An'], ['merkle-odd', 'Hồ sơ An\nHồ sơ Bình\nHồ sơ Chi'], ['merkle-empty', '']]) {
    $(id).onclick = () => { if (merkleBusy) return; $('merkle-leaves').value = text; $('merkle-leaves').oninput(); };
  }
  window.addEventListener('pagehide', () => {
    const old = signature; signature = freshSignature(); showSignature();
    $('sig-status').textContent = 'Đã rời trang; tạo khóa tạm mới để ký tiếp.';
    [old.key, old.other].filter(Boolean).forEach(k => navigator.sendBeacon(`${LAB_API}/signatures/keys/${encodeURIComponent(k.key_handle)}/reset`));
  });
  showSignature(); updateProofChoices();
})();
