const attackElement = id => document.getElementById(id);
const attackDescriptions = {
  tamper: 'Sửa tiêu đề sau khi ký, giữ nguyên tx_id, khóa gửi và chữ ký. Backend đối chiếu hash trước khi kiểm tra ECDSA.',
  impersonation: 'Khóa của kẻ giả danh ký một hồ sơ mang tên đơn vị được phép. Tên giống nhau không cấp quyền: danh sách cho phép dùng khóa công khai.',
  replay: 'Gửi lại chính giao dịch nền đã được chấp nhận, giữ nguyên toàn bộ dữ liệu, tx_id và chữ ký.'
};
const attackLayers = {
  transaction_hash: 'Đối chiếu hash giao dịch (tx_id)', signature: 'Chữ ký số ECDSA',
  issuer_authorization: 'Quyền phát hành theo khóa công khai',
  duplicate_submission: 'Mempool — giao dịch đã tồn tại', admission: 'Kiểm tra tiếp nhận backend'
};
let attackState = { busy: false, result: null };
function attackText(parent, tag, text) {
  const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
}
function attackControls() {
  const s = attackState, scenario = attackElement('attack-scenario').value;
  attackElement('attack-scenario').disabled = attackElement('attack-title').disabled = s.busy;
  attackElement('attack-title').required = scenario === 'tamper';
  attackElement('attack-title-field').hidden = scenario !== 'tamper';
  attackElement('attack-explanation').textContent = attackDescriptions[scenario];
  const title = attackElement('attack-title').value.trim();
  const invalid = scenario === 'tamper' && (!title || title === 'Chứng chỉ mẫu lab');
  attackElement('attack-run').disabled = s.busy || invalid;
  attackElement('attack-control-note').textContent = s.busy ? 'Đang chờ backend; chưa thể chạy thêm lượt. Đặt lại sẽ bỏ qua kết quả muộn.'
    : invalid ? 'Nhập tiêu đề khác mẫu, không trống để chạy thử.' : 'Mỗi lượt bắt đầu bằng dữ liệu nền mới; không thay đổi lab khác.';
}
function clearAttackResult() {
  attackElement('attack-results').hidden = true;
  for (const id of ['attack-baseline', 'attack-data', 'attack-outcome']) attackElement(id).replaceChildren();
  attackElement('attack-technical').textContent = attackElement('attack-next').textContent = '';
  attackElement('attack-result-context').textContent = '';
}
function showAttackResult(data) {
  attackElement('attack-results').hidden = false;
  const outcome = attackElement('attack-outcome'); outcome.replaceChildren();
  const accepted = data.attack.submission.accepted;
  outcome.className = 'result ' + (accepted ? 'unexpected' : 'invalid');
  attackText(outcome, 'h2', accepted ? 'Giao dịch thử được chấp nhận — kết quả ngoài dự kiến' : '✗ Giao dịch thử bị từ chối');
  attackText(outcome, 'p', 'Giao dịch nền: ' + (data.baseline.submission.accepted ? '✓ Được chấp nhận' : '✗ Bị từ chối') + ' — ' + data.baseline.submission.reason);
  attackText(outcome, 'p', accepted ? 'Backend không từ chối giao dịch thử; không có lớp thất bại được báo.'
    : 'Kiểm tra thất bại đầu tiên: ' + (attackLayers[data.failure_layer] || data.failure_layer || 'Không được trả về'));
  attackText(outcome, 'p', data.attack.submission.reason);
  for (const [id, record, title] of [['attack-baseline', data.baseline, 'Nền hợp lệ'], ['attack-data', data.attack, 'Dữ liệu thử']]) {
    const panel = attackElement(id), tx = record.transaction; panel.replaceChildren();
    attackText(panel, 'h2', title);
    attackText(panel, 'p', 'Tiêu đề: ' + tx.payload.title);
    attackText(panel, 'p', 'Tên đơn vị được khai báo: ' + tx.payload.issuer_name);
    const short = value => value.slice(0, 12) + '…' + value.slice(-8);
    attackText(panel, 'p', 'Khóa gửi: ' + short(tx.sender_public_key)).title = tx.sender_public_key;
    attackText(panel, 'p', 'tx_id đã ghi: ' + short(tx.tx_id)).title = tx.tx_id;
    attackText(panel, 'p', 'Hash tính lại: ' + short(record.verification.computed_hash)).title = record.verification.computed_hash;
    attackText(panel, 'p', 'Xác minh giao dịch: ' + (record.verification.valid ? '✓ Hợp lệ' : '✗ Không hợp lệ'));
    attackText(panel, 'p', record.verification.reason);
    attackText(panel, 'p', record.verification.signature_checked ? 'Backend đã kiểm tra chữ ký ECDSA.' : 'Chưa chạy kiểm tra ECDSA: hash giao dịch không khớp trước đó.');
    attackText(panel, 'p', 'Gửi vào mempool: ' + (record.submission.accepted ? '✓ Chấp nhận' : '✗ Từ chối'));
    attackText(panel, 'p', record.submission.reason);
  }
  if (data.attacker) {
    for (const [label, identity] of [['Khóa được phép phát hành', data.authorized_issuer], ['Khóa của kẻ giả danh', data.attacker]]) {
      attackText(attackElement('attack-data'), 'p', `${label}: ${identity.address}`).title = identity.public_key_hex;
    }
  }
  attackElement('attack-next').textContent = accepted
    ? 'Đây là kết quả backend thực tế, không có từ chối được giả lập. Đọc các kiểm tra rồi thử kịch bản khác.'
    : data.failure_layer === 'transaction_hash' ? 'Nội dung đổi nhưng tx_id được giữ, nên lớp hash chặn trước ECDSA. Thử giả danh để phân biệt chữ ký hợp lệ với quyền phát hành.'
    : data.failure_layer === 'issuer_authorization' ? 'Khóa tự tạo có chữ ký hợp lệ nhưng không được phép phát hành. Thử replay để xem một giao dịch hợp lệ vẫn có thể bị từ chối.'
    : data.failure_layer === 'duplicate_submission' ? 'Gửi trùng cùng giao dịch bị từ chối; đây là replay, không phải chi tiêu kép tiền tệ. Có thể chạy lại trên mạng tạm mới.'
    : 'Đọc lý do tiếp nhận thực tế trong kết quả và chi tiết, rồi thử kịch bản khác.';
  attackElement('attack-technical').textContent = JSON.stringify(data, null, 2);
}
async function runAttack(event) {
  event.preventDefault(); const s = attackState;
  if (s.busy || attackElement('attack-run').disabled) return;
  const body = { scenario: attackElement('attack-scenario').value };
  if (body.scenario === 'tamper') body.edited_title = attackElement('attack-title').value;
  s.busy = true; s.result = null; clearAttackResult(); attackControls();
  attackElement('attack-error').hidden = true; attackElement('attack-error').textContent = '';
  attackElement('attack-status').textContent = 'Đang tạo nền hợp lệ và kiểm tra trên mạng tạm…';
  try {
    const response = await fetch('/api/labs/attacks/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await response.json(); if (s !== attackState) return;
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(Array.isArray(detail) ? detail.map(e => e.msg).join('; ') : typeof detail === 'string' ? detail : detail?.message || `Lỗi HTTP ${response.status}`);
    }
    s.result = data; showAttackResult(data);
    attackElement('attack-status').textContent = 'Đã nhận kết quả backend. Mạng tạm đã được dọn; có thể chạy lượt mới.';
  } catch (error) {
    if (s === attackState) {
      attackElement('attack-error').textContent = error.message; attackElement('attack-error').hidden = false;
      attackElement('attack-status').textContent = 'Lượt thử thất bại: chưa nhận được kết quả. Nếu phiên hết hạn, lượt mới dùng phiên mới.';
    }
  } finally { if (s === attackState) { s.busy = false; attackControls(); } }
}
function resetAttack() {
  attackState = { busy: false, result: null }; clearAttackResult();
  attackElement('attack-error').hidden = true; attackElement('attack-error').textContent = '';
  attackElement('attack-status').textContent = 'Đã đặt lại riêng lab này. Không reset phiên có hướng dẫn hoặc lab khác.';
  attackControls();
}
(function setupAttack() {
  function theme(value) {
    document.documentElement.dataset.theme = value;
    attackElement('attack-theme').title = value === 'light' ? 'Chế độ tối' : 'Chế độ sáng';
    attackElement('attack-theme').setAttribute('aria-pressed', String(value === 'light'));
    try { localStorage.setItem('trustmebro-theme', value); } catch {}
  }
  theme(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
  attackElement('attack-theme').onclick = () => theme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  window.addEventListener('pageshow', () => { try { theme(localStorage.getItem('trustmebro-theme') === 'light' ? 'light' : 'dark'); } catch {} });
  attackElement('attack-form').onsubmit = runAttack; attackElement('attack-reset').onclick = resetAttack;
  attackElement('attack-title').oninput = () => {
    attackControls();
    if (attackState.result) attackElement('attack-result-context').textContent = 'Đầu vào đã đổi — kết quả bên dưới thuộc lượt thử trước. Bấm Chạy thử để cập nhật.';
  };
  attackElement('attack-scenario').onchange = () => { if (!attackState.busy) resetAttack(); };
  window.addEventListener('pagehide', resetAttack); attackControls();
})();
