const $ = id => document.getElementById(id);
const shortValue = value => value.length > 28 ? `${value.slice(0,12)}…${value.slice(-8)}` : value;
let explorerVersion = 0, explorerAbort = null, explorerSnapshot = null;

function explorerText(parent, tag, text) {
  const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
}

function explorerFull(parent, label, value) {
  const details = document.createElement('details');
  explorerText(details, 'summary', label); explorerText(details, 'pre', value); parent.append(details);
}

function explorerValue(parent, label, value) {
  if (value == null || value === '') return;
  explorerText(parent, 'p', `${label}: ${shortValue(String(value))}`);
  explorerFull(parent, `${label} — đầy đủ`, String(value));
}

function clearExplorerDetail() {
  $('explorer-detail').replaceChildren(); $('explorer-prompt').hidden = false;
}

function clearExplorerList() {
  explorerSnapshot = null; $('explorer-blocks').replaceChildren();
  $('explorer-genesis-blocks').replaceChildren(); $('explorer-genesis-section').hidden = true;
  $('explorer-workspace').hidden = true;
  $('explorer-summary').replaceChildren(); $('explorer-genesis').hidden = true;
  $('explorer-warning').hidden = true; clearExplorerDetail();
}

function showExplorerNode(data) {
  const summary = $('explorer-summary'); summary.replaceChildren();
  explorerText(summary, 'p', `${data.node_id} · ${data.status === 'ONLINE' ? 'Đang bật' : 'OFFLINE'} · Chiều cao: ${data.tip_height} (genesis = 0)`);
  explorerValue(summary, 'Tip hash', data.tip_hash);
  $('explorer-warning').textContent = data.local_chain_warning || '';
  $('explorer-warning').hidden = !data.local_chain_warning;
}

function showExplorerBlocks(data) {
  showExplorerNode(data);
  const onlyGenesis = data.blocks.every(block => block.height === 0);
  $('explorer-genesis').hidden = !onlyGenesis;
  $('explorer-block-panel').hidden = onlyGenesis;
  $('explorer-workspace').className = onlyGenesis ? 'workspace genesis-only' : 'workspace';
  $('explorer-workspace').hidden = onlyGenesis;
  $('explorer-genesis-section').hidden = !data.blocks.some(block => block.height === 0);
  $('explorer-genesis-blocks').replaceChildren();
  const container = $('explorer-blocks'); container.replaceChildren();
  for (const block of [...data.blocks].sort((a,b) => b.height-a.height)) {
    const button = document.createElement('button'); button.className = 'block-choice';
    button.setAttribute('aria-pressed', 'false'); button.dataset.height = String(block.height);
    explorerText(button, 'span', `${block.height === 0 ? 'Genesis' : 'Block #' + block.height} · ${block.consensus_type || 'Không có dữ liệu đồng thuận'} · ${block.transaction_count} giao dịch`);
    explorerText(button, 'small', `Hash: ${shortValue(block.hash)}`);
    explorerText(button, 'small', `Trước: ${shortValue(block.previous_hash)} · ${block.timestamp}`);
    button.onclick = () => loadExplorerBlock(block.height);
    (block.height === 0 ? $('explorer-genesis-blocks') : container).append(button);
  }
}

function showExplorerDetail(data) {
  $('explorer-workspace').hidden = false;
  const container = $('explorer-detail'); container.replaceChildren(); $('explorer-prompt').hidden = true;
  const block = data.block, header = data.header;
  explorerText(container, 'h3', `${block.height === 0 ? 'Genesis' : 'Block #' + block.height} · ${block.consensus_type || 'Không có dữ liệu đồng thuận'}`);
  explorerText(container, 'p', `${data.node_id} · ${block.timestamp} · ${block.transaction_count} giao dịch`);
  explorerValue(container, 'Hash block', block.hash); explorerValue(container, 'Hash trước', header.previous_hash);
  explorerValue(container, 'Merkle root', header.merkle_root);
  if (header.consensus_type === 'PoW') {
    explorerText(container, 'p', `PoW · Nonce: ${header.nonce ?? 'Không có dữ liệu'} · Độ khó: ${header.difficulty ?? 'Không có dữ liệu'}`);
  } else if (header.consensus_type === 'PoS') {
    explorerText(container, 'h3', 'Validator tạo block — ký block');
    explorerValue(container, 'Địa chỉ validator trong header', header.validator_address);
    if (data.validator) {
      explorerText(container, 'p', `Tên trong registry hiện tại: ${data.validator.name}`);
      explorerValue(container, 'Khóa công khai validator', data.validator.public_key_hex);
    } else explorerText(container, 'p', 'Không có khóa registry khớp chữ ký để hiển thị danh tính validator.');
  }
  explorerFull(container, 'Header đầy đủ (giá trị backend)', JSON.stringify(header, null, 2));
  if (!data.transactions.length) explorerText(container, 'p', 'Block không có giao dịch.');
  for (const tx of data.transactions) {
    const card = document.createElement('article'); card.className = 'transaction';
    explorerText(card, 'h3', `${tx.tx_type} · ${shortValue(tx.tx_id)}`);
    if (tx.payload?.issuer_name) explorerText(card, 'p', `Đơn vị phát hành được ghi trong payload: ${tx.payload.issuer_name}`);
    explorerValue(card, 'Ví phát hành — khóa ký giao dịch', tx.sender_public_key);
    explorerText(card, 'p', 'Payload thật của giao dịch:'); explorerText(card, 'pre', JSON.stringify(tx.payload, null, 2));
    explorerFull(card, 'Giao dịch đầy đủ — tx_id, chữ ký và metadata', JSON.stringify(tx, null, 2)); container.append(card);
  }
}

async function explorerRead(height = null) {
  const list = height === null, node = $('explorer-node').value;
  const expected = explorerSnapshot, block = expected?.blocks.find(b => b.height === height);
  if (!list && !block) return;
  const version = ++explorerVersion;
  explorerAbort?.abort(); const controller = new AbortController(); explorerAbort = controller;
  if (list) clearExplorerList(); else clearExplorerDetail();
  $('explorer-refresh').disabled = true; $('explorer-error').hidden = true; $('explorer-error').textContent = '';
  explorerButtons().forEach(button => {
    button.disabled = true; button.setAttribute('aria-pressed', String(!list && button.dataset.height === String(height)));
  });
  $('explorer-status').textContent = 'Đang đọc dữ liệu backend…';
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`/api/explorer/blocks${list ? '' : '/' + height}?node_id=${encodeURIComponent(node)}`, { signal: controller.signal });
    const data = await response.json();
    if (version !== explorerVersion) return;
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || `Lỗi HTTP ${response.status}`);
      error.status = response.status; throw error;
    }
    if (!list && (data.context_generation !== expected.context_generation
        || data.reset_count !== expected.reset_count || data.block.hash !== block.hash)) {
      clearExplorerList(); throw new Error('Phiên hoặc chuỗi đã thay đổi. Bấm Làm mới để đọc lại.');
    }
    if (list) { explorerSnapshot = data; showExplorerBlocks(data); }
    else { showExplorerNode(data); showExplorerDetail(data); }
    $('explorer-status').textContent = 'Đã đọc snapshot. Bấm Làm mới sau thao tác trong journey; trang không tự đồng bộ.';
  } catch (error) {
    if (version !== explorerVersion) return;
    if (error.status === 404) clearExplorerList();
    $('explorer-error').textContent = error.name === 'AbortError' ? 'Hết thời gian đọc dữ liệu. Hãy bấm Làm mới.'
      : error.status === 404 && !list ? `Block #${height} không còn trên node đã chọn; phiên có thể đã reset. ${error.message}` : error.message;
    $('explorer-error').hidden = false; $('explorer-status').textContent = 'Chưa đọc được dữ liệu mới. Không hiển thị chi tiết cũ.';
  } finally {
    clearTimeout(timer);
    if (version === explorerVersion) {
      explorerAbort = null; $('explorer-refresh').disabled = false;
      explorerButtons().forEach(button => { button.disabled = false; });
    }
  }
}

function loadExplorerBlocks() { return explorerRead(); }
function loadExplorerBlock(height) { return explorerRead(height); }

function explorerButtons() {
  return [...$('explorer-blocks').querySelectorAll('button'), ...$('explorer-genesis-blocks').querySelectorAll('button')];
}

async function enterExplorer() {
  const params = new URLSearchParams(window.location?.search || '');
  const node = params.get('node_id'), rawHeight = params.get('height');
  const validNode = !params.has('node_id') || (params.getAll('node_id').length === 1 && ['Node-1','Node-2','Node-3'].includes(node));
  const validHeight = !params.has('height') || (params.getAll('height').length === 1 && /^(0|[1-9]\d*)$/.test(rawHeight) && Number.isSafeInteger(Number(rawHeight)));
  if (validNode && node) $('explorer-node').value = node;
  const selected = $('explorer-node').value;
  const pending = loadExplorerBlocks(), version = explorerVersion;
  await pending;
  if (version !== explorerVersion || $('explorer-node').value !== selected || !explorerSnapshot) return;
  if (!validNode || !validHeight) {
    $('explorer-error').textContent = 'Liên kết có node hoặc chiều cao block không hợp lệ. Hãy chọn node và block trong danh sách.';
    $('explorer-error').hidden = false;
  } else if (rawHeight !== null) {
    const height = Number(rawHeight);
    if (explorerSnapshot.blocks.some(block => block.height === height)) await loadExplorerBlock(height);
    else {
      $('explorer-error').textContent = `Block #${height} không còn trên node đã chọn; phiên có thể đã reset hoặc node chưa nhận block. Hãy kiểm tra hành trình/mạng rồi làm mới.`;
      $('explorer-error').hidden = false;
    }
  }
}

(function setupExplorer() {
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
  $('explorer-node').onchange = loadExplorerBlocks; $('explorer-refresh').onclick = loadExplorerBlocks;
  window.addEventListener('simulation-ready', enterExplorer);
  window.addEventListener('pageshow', event => { restoreTheme(); if (event.persisted) enterExplorer(); });
  window.addEventListener('pagehide', () => { ++explorerVersion; explorerAbort?.abort(); clearExplorerList(); });
  restoreTheme(); enterExplorer();
})();
