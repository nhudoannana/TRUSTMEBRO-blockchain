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
    $('hash-difference').textContent = `${bits}/256 bit khác nhau (${(bits / 256 * 100).toFixed(2)}%). ` +
      (original === edited ? 'Hai đầu vào giống nhau tạo cùng hash SHA-256, vì vậy chênh lệch là 0%.'
        : 'Với hai đầu vào khác nhau, hiệu ứng avalanche thường làm khoảng một nửa số bit hash thay đổi; tỷ lệ không cần đạt 100%.');
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
    if (data.seconds !== null) line(`Thời gian lời gọi Node: ${data.seconds.toFixed(4)} giây.`);
    if (data.created && mode === 'pow') {
      line(`Độ khó: ${data.block.difficulty} · Nonce: ${data.block.nonce}${data.attempts == null ? '' : ' · ' + data.attempts + ' lần thử (backend đo).'}`);
    }
    line(`Ví phát hành — ký hồ sơ: ${data.issuer.name} · ${shortHash(data.issuer.address)}`);
    if (data.created && mode === 'pos' && data.signer) {
      line(`Validator tạo block — ký block: ${data.signer.name} · ${shortHash(data.signer.address)}`);
      line(`Stake: ${data.signer.stake} · Trọng số lựa chọn: ${(data.signer.selection_weight * 100).toFixed(1)}%.`);
    }
    line(`Chuỗi lab: ${data.chain_valid ? 'hợp lệ' : 'không hợp lệ'} — ${data.validity_reason}`);
    const details = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
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
  const summary = $('network-summary');
  summary.className = 'result';
  summary.textContent = !data ? 'Chưa có mạng lab. Khởi tạo để xem ba node ở block genesis.'
    : s.pollFailed ? 'Chưa xác nhận hoàn tất trong thời hạn. Các thẻ bên dưới là trạng thái cuối đã đọc; hãy làm mới.'
    : data.all_nodes_synchronized ? '✓ Cả ba node ONLINE: cùng chiều cao và tip hash, các chuỗi hợp lệ.'
    : data.online_nodes_synchronized ? 'Các node ONLINE đồng thuận về chiều cao và tip hash, chuỗi hợp lệ. Chưa đồng bộ cả ba node.'
    : !data.online_nodes_valid ? 'Có chuỗi ONLINE không hợp lệ. Xem lý do backend trong chi tiết.'
    : 'Các node ONLINE chưa có cùng chiều cao và tip hash; đang quan sát trạng thái thực.';
  if (data?.all_nodes_synchronized && !s.pollFailed) summary.className += ' valid';
  const container = $('network-nodes'); container.replaceChildren();
  for (const node of data?.nodes || []) {
    const card = document.createElement('article'); card.className = 'panel';
    const heading = document.createElement('h2'); heading.textContent = `${node.node_id} · ${node.status === 'ONLINE' ? 'Đang bật' : 'Offline'}`;
    card.append(heading);
    function line(text) { const p = document.createElement('p'); p.textContent = text; card.append(p); }
    line(`Chiều cao: ${node.height} · ${node.block_count} block (gồm genesis)`);
    line(`Tip: ${shortHash(node.tip_hash)} · Giao dịch chờ: ${node.pending_count}`);
    line(`Chuỗi: ${node.chain_valid ? 'Hợp lệ' : 'Không hợp lệ'}`);
    line(node.verification ? `Hồ sơ: ${node.verification.status}` : 'Chưa có hồ sơ mẫu để xác minh.');
    if (node.local_chain_warning) line(node.local_chain_warning);
    const details = document.createElement('details'), label = document.createElement('summary'), pre = document.createElement('pre');
    label.textContent = 'Tip đầy đủ, lý do và các bước xác minh';
    pre.textContent = JSON.stringify(node, null, 2); details.append(label, pre); card.append(details); container.append(card);
  }
  $('network-technical').textContent = data ? JSON.stringify(data, null, 2) : '';
  $('network-credential').textContent = data?.mining
    ? `Đã tạo block #${data.mining.block.height} bằng PoW trên Node-1. Độ khó ${data.mining.block.difficulty}; hồ sơ ${data.credential_id}.`
    : data?.transaction ? 'Hồ sơ mẫu đã ký; chưa tạo được block. Giao dịch được giữ để thử lại.'
    : 'Thử: tắt Node-3 → tạo block → quan sát NOT_FOUND trên node offline → bật lại Node-3.';
}

async function readNetworkLab(s, timeout = 2000) {
  const controller = new AbortController(); s.abort = controller;
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await labResponse(await fetch(LAB_API + networkPath(s), { signal: controller.signal }));
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Hết thời gian đọc trạng thái mạng. Hãy làm mới.');
    throw error;
  } finally { clearTimeout(timer); if (s.abort === controller) s.abort = null; }
}

async function pollNetworkLab(s, complete) {
  const deadline = Date.now() + 5000;
  while (s === networkLab && Date.now() < deadline) {
    let data;
    try { data = await readNetworkLab(s, Math.min(2000, deadline - Date.now())); }
    catch (error) { if (s === networkLab) s.pollFailed = true; throw error; }
    if (s !== networkLab) return false;
    s.snapshot = data; showNetworkLab();
    if (complete(data)) return true;
    const remaining = deadline - Date.now();
    if (remaining > 0) await new Promise(resolve => setTimeout(resolve, Math.min(250, remaining)));
  }
  if (s !== networkLab) return false;
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
    const labs = ['sha', 'signatures', 'merkle', 'consensus', 'network'];
    const name = labs.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'sha';
    labs.forEach(id => { $('lab-' + id).hidden = id !== name; });
    document.querySelectorAll('[data-lab]').forEach(a => {
      if (a.dataset.lab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    document.title = `${name === 'sha' ? 'SHA-256' : name === 'merkle' ? 'Cây Merkle' : name === 'consensus' ? 'PoW–PoS' : name === 'network' ? 'Đồng bộ mạng' : 'Chữ ký số'} — TrustMeBro`;
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
  $('comparison-form').onsubmit = runComparison; $('comparison-reset').onclick = resetComparison;
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
  window.addEventListener('pagehide', () => {
    const oldNetwork = networkLab; oldNetwork.abort?.abort(); networkLab = freshNetworkLab(); showNetworkLab();
    $('network-status').textContent = 'Đã rời trang; khởi tạo mạng lab mới để tiếp tục.';
    if (oldNetwork.handle) navigator.sendBeacon(LAB_API + networkPath(oldNetwork) + '/reset');
    comparison = freshComparison(); showComparison();
    const old = signature; signature = freshSignature(); showSignature();
    $('sig-status').textContent = 'Đã rời trang; tạo khóa tạm mới để ký tiếp.';
    [old.key, old.other].filter(Boolean).forEach(k => navigator.sendBeacon(`${LAB_API}/signatures/keys/${encodeURIComponent(k.key_handle)}/reset`));
  });
  showSignature(); updateProofChoices();
})();
