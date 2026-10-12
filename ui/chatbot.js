/*
 * TRUSTMEBRO — Trợ lý AI (Chatbot-1) widget.
 * Nâng cấp từ widget gốc: lifecycle có token + AbortController, guard in-flight,
 * lịch sử chỉ trong bộ nhớ của tab (không localStorage/sessionStorage),
 * xử lý lỗi theo hợp lệ của api/chatbot_api.py, lab_links an toàn, a11y.
 * Trang cần nạp ui/session.js trước file này (đã quy định trong kế hoạch C3/C4).
 */
(() => {
  'use strict';

  // Tránh tiêm lặp.
  if (document.getElementById('chatbot-bubble')) return;

  // ===== Cấu hình =====
  const API_STATUS = '/api/chatbot/status';
  const API_CHAT = '/api/chatbot';
  const AVATAR_URL = '/ui/chatbot-avatar.png';
  const REQUEST_TIMEOUT_MS = 25000;      // gồm cả bootstrap phiên của session.js
  const STATUS_TTL_MS = 5 * 60 * 1000;   // kiểm tra lại trạng thái khi mở nếu đã cũ
  const MAX_STORED_PAIRS = 10;           // tối đa 10 cặp thành công (20 tin) trong RAM
  const REQUIRE_CONSENT = true;          // kế hoạch C3 §5: xác nhận trước khi gửi
  const DEFAULT_LIMITS = Object.freeze({
    messageBytes: 2048, historyMessages: 6, historyBytes: 12288, answerBytes: 4096,
  });
  const GENERATION_RE = /^[A-Za-z0-9_-]{1,128}$/;
  // Phản chiếu bộ lọc SENSITIVE của backend để không gửi (và không đưa vào history) chuỗi giống khóa/hash.
  const SENSITIVE_PATTERNS = [
    /BEGIN[^\r\n]*PRIVATE KEY/i,
    /AIza[A-Za-z0-9_-]{20,}/i,
    /[a-f0-9]{64,}/i,
    /[A-Za-z0-9+/=_-]{128,}/i,
    /"(?:private_key|private_key_pem|wallets|transactions|mempool|credential_id|key_handle)"\s*:/i,
  ];

  const SUGGESTIONS = [
    'Merkle Root dùng để làm gì?',
    'Khác biệt giữa PoW và PoS?',
    'Hiệu ứng tuyết lở SHA-256 là gì?',
    'Fork chọn nhánh theo tổng work nghĩa là gì?',
  ];
  const STATIC_LINKS = [
    { label: 'Mở các lab', href: '/ui/labs.html' },
    { label: 'Đọc lý thuyết', href: '/ui/theory.html' },
  ];

  const T = {
    greeting: 'Xin chào! Mình là Trợ lý AI của TrustMeBro. Bạn có thể hỏi về lý thuyết mật mã và blockchain ' +
      '(SHA-256, Merkle, PoW/PoS, chữ ký số…) hoặc cách dùng các bài lab. Mình giải thích khái niệm và gợi ý ' +
      'thao tác; mình không đọc được trạng thái lab của bạn.',
    consent: 'Bạn đang hỏi AI. Câu hỏi và vài lượt hội thoại được gửi đến Gemini qua máy chủ. Không gửi khóa, ví, ' +
      'dữ liệu cá nhân hoặc dữ liệu lab. Trợ lý không đọc trạng thái lab và có thể trả lời sai.',
    consentLabel: 'Tôi hiểu và muốn tiếp tục',
    disclaimer: 'Trợ lý AI giải thích kiến thức; không gửi khóa riêng hoặc dữ liệu cá nhân.',
    blocked: 'AI chưa trả lời nội dung này; hãy hỏi về khái niệm.',
    sensitive: 'Không gửi khóa, ví hoặc dữ liệu lab; hãy hỏi về khái niệm.',
    timeout: 'Máy chủ phản hồi quá lâu (25 giây). Lượt này có thể vẫn đang chạy trên máy chủ; nếu gửi lại ngay ' +
      'bạn có thể nhận thông báo “đang xử lý”.',
    network: 'Không kết nối được máy chủ. Hãy kiểm tra mạng hoặc việc chạy server rồi thử lại. Các lab vẫn dùng bình thường.',
    aborted: 'Yêu cầu đã bị ngắt (rời hoặc tải lại trang). Hãy thử lại.',
    badResponse: 'Máy chủ trả về dữ liệu không đúng định dạng nên câu trả lời không được hiển thị. Hãy thử lại.',
    notFound: 'Không tìm thấy dịch vụ trợ lý AI trên máy chủ này. Các lab vẫn dùng bình thường.',
    sessionChanged: 'Phiên mô phỏng đã thay đổi nên các câu hỏi trước không còn được gửi kèm. ' +
      'Đang kết nối lại; hãy gửi lại câu hỏi của bạn.',
    truncated: 'Câu trả lời đã bị rút gọn do giới hạn độ dài.',
    notRemembered: 'Lượt hỏi–đáp này không được gửi lại làm ngữ cảnh vì chứa chuỗi hex/base64 dài.',
  };
  const STATUS_LABEL = {
    idle: 'Đang chuẩn bị…', loading: 'Đang kiểm tra…', ready: 'Sẵn sàng hỗ trợ',
    unavailable: 'Chưa khả dụng', error: 'Mất kết nối',
  };
  const UNAVAILABLE_TEXT = {
    disabled: 'Trợ lý AI chưa được bật trên máy chủ này; các lab vẫn dùng bình thường.',
    sdk_missing: 'Máy chủ chưa cài thư viện AI tùy chọn; các lab vẫn dùng bình thường.',
    key_missing: 'Máy chủ chưa cấu hình khóa AI; các lab vẫn dùng bình thường.',
    config_invalid: 'Cấu hình trợ lý AI chưa hợp lệ; các lab vẫn dùng bình thường.',
  };
  // Mã lỗi POST đã biết → hành vi UI.
  const UNAVAILABLE_BY_CODE = {
    chat_disabled: 'disabled', sdk_unavailable: 'sdk_missing',
    key_unavailable: 'key_missing', provider_configuration: 'config_invalid',
  };
  const CODE_RULES = {
    malformed_json: { restore: true },
    origin_rejected: { restore: true },
    body_too_large: { restore: true, text: 'Nội dung gửi đi quá lớn. Hãy rút ngắn câu hỏi rồi thử lại.' },
    unsupported_media_type: { restore: true },
    invalid_input: { restore: true },
    sensitive_input: { restore: true },
    session_changed: { restore: true, session: true },
    chat_busy: { retry: true, hint: 'Hãy đợi vài giây rồi bấm “Thử lại”.' },
    chat_rate_limited: { restore: true, cooldown: 60 },
    chat_budget_exhausted: { restore: true, cooldown: 60 },
    chat_capacity: { retry: true },
    session_capacity: { retry: true },
    provider_quota: { retry: true },
    provider_timeout: { retry: true },
    provider_unavailable: { retry: true },
    provider_invalid_response: { retry: true },
  };

  // ===== Tiện ích =====
  const encoder = new TextEncoder();
  const byteLen = (text) => encoder.encode(text).length;
  const looksSensitive = (text) => SENSITIVE_PATTERNS.some((re) => re.test(text));
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function attrs(node, map) {
    for (const [key, value] of Object.entries(map)) node.setAttribute(key, value);
    return node;
  }
  function icon(paths) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    attrs(svg, { viewBox: '0 0 24 24', class: 'cb-icon', 'aria-hidden': 'true', focusable: 'false' });
    for (const d of paths) {
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    }
    return svg;
  }
  function safeText(value, max = 300) {
    return typeof value === 'string' ? value.trim().slice(0, max) : '';
  }
  function formatWait(seconds) {
    const s = Math.max(1, Math.ceil(seconds));
    if (s < 60) return `${s} giây`;
    if (s < 3600) return `${Math.floor(s / 60)} phút ${String(s % 60).padStart(2, '0')} giây`;
    return `${Math.floor(s / 3600)} giờ ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')} phút`;
  }
  // Chỉ nhận đường dẫn cùng nguồn trong /ui/ (khớp danh mục liên kết của backend).
  function safeLink(item) {
    if (!item || typeof item !== 'object') return null;
    const label = safeText(item.label, 60);
    const href = item.href;
    if (!label || typeof href !== 'string' || !/^\/ui\/[^\s\\]*$/.test(href)) return null;
    let url;
    try { url = new URL(href, window.location.origin); } catch (error) { return null; }
    if (url.origin !== window.location.origin) return null;
    return { label, href: url.pathname + url.search + url.hash };
  }

  class CbError extends Error {
    constructor(kind, cause) {
      super(kind);
      this.kind = kind;       // timeout | network | aborted | bad_response
      this.cause = cause;
    }
  }

  // ===== Trạng thái (chỉ trong RAM của tab) =====
  const state = {
    open: false,
    status: 'idle',            // idle | loading | ready | unavailable | error
    statusCode: '',
    statusFailure: null,
    statusMessage: '',
    statusRequest: null,
    checkedAt: 0,
    generation: '',
    limits: { ...DEFAULT_LIMITS },
    consent: !REQUIRE_CONSENT,
    pairs: [],                 // các cặp {q, a} đã thành công
    busy: false,
    current: null,
    epoch: 0,
    dirty: false,
    cooldownUntil: 0,
    cooldownTimer: 0,
    composing: false,
  };
  let chips = [];
  let chipsBox = null;
  let statusNotice = null;
  let statusNoticeKey = '';

  // ===== DOM =====
  const bubble = attrs(el('button', 'cb-bubble'), {
    id: 'chatbot-bubble', type: 'button', 'aria-expanded': 'false',
    'aria-controls': 'chatbot-window', 'aria-label': 'Mở trợ lý AI',
  });
  bubble.title = 'Trợ lý TRUSTMEBRO AI';
  const tooltip = attrs(el('div', 'cb-tooltip', '💬 Trợ lý TRUSTMEBRO AI'), { id: 'chatbot-tooltip', 'aria-hidden': 'true' });

  const win = attrs(el('section', 'cb-window'), {
    id: 'chatbot-window', role: 'dialog', 'aria-modal': 'false', 'aria-label': 'Trợ lý TRUSTMEBRO AI', tabindex: '-1',
  });

  const avatar = attrs(el('div', 'cb-avatar'), { 'aria-hidden': 'true' });
  const statusText = el('span', 'cb-status-text', STATUS_LABEL.idle);
  const statusLine = el('p', 'cb-status');
  statusLine.dataset.state = 'idle';
  statusLine.append(statusText);
  const titleBox = el('div', 'cb-title-box');
  titleBox.append(attrs(el('div', 'cb-title', 'Trợ lý TRUSTMEBRO AI'), { role: 'heading', 'aria-level': '2' }), statusLine);
  const profile = el('div', 'cb-profile');
  profile.append(avatar, titleBox);

  const clearBtn = attrs(el('button', 'cb-btn-icon'), { type: 'button', 'aria-label': 'Xóa đoạn chat', title: 'Xóa đoạn chat' });
  clearBtn.append(icon(['M3 6h18', 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6', 'M14 11v6']));
  const closeBtn = attrs(el('button', 'cb-btn-icon'), { type: 'button', 'aria-label': 'Thu nhỏ trợ lý AI', title: 'Thu nhỏ' });
  closeBtn.append(icon(['m6 9 6 6 6-6']));
  const headerActions = el('div', 'cb-header-actions');
  headerActions.append(clearBtn, closeBtn);
  const header = el('div', 'cb-header');
  header.append(profile, headerActions);

  const msgs = attrs(el('div', 'cb-messages'), {
    role: 'log', 'aria-live': 'polite', 'aria-relevant': 'additions', 'aria-label': 'Đoạn hội thoại',
    'aria-busy': 'false', tabindex: '0',
  });

  let consentBox = null;
  let consentCheck = null;
  if (REQUIRE_CONSENT) {
    consentBox = el('div', 'cb-consent');
    const label = el('label', 'cb-consent-label');
    consentCheck = attrs(el('input', 'cb-checkbox'), { type: 'checkbox' });
    label.append(consentCheck, el('span', '', T.consentLabel));
    consentBox.append(el('p', 'cb-consent-text', T.consent), label);
  }

  const form = attrs(el('form', 'cb-footer'), { novalidate: '' });
  const hintEl = attrs(el('div', 'cb-hint'), { id: 'cb-hint', 'aria-live': 'off' });
  const input = attrs(el('textarea', 'cb-input'), {
    rows: '1', placeholder: 'Hỏi về blockchain hoặc dự án…', autocomplete: 'off',
    'aria-label': 'Câu hỏi cho trợ lý AI', 'aria-describedby': 'cb-hint cb-disclaimer', enterkeyhint: 'send',
  });
  const sendBtn = attrs(el('button', 'cb-send-btn'), { type: 'submit', 'aria-label': 'Gửi câu hỏi', title: 'Gửi' });
  sendBtn.append(icon(['m22 2-7 20-4-9-9-4Z', 'M22 2 11 13']));
  const row = el('div', 'cb-row');
  row.append(input, sendBtn);
  const disclaimer = attrs(el('p', 'cb-disclaimer', T.disclaimer), { id: 'cb-disclaimer' });
  form.append(hintEl, row, disclaimer);

  const srLive = attrs(el('div', 'cb-sr'), { role: 'status', 'aria-live': 'polite' });
  win.append(header, msgs);
  if (consentBox) win.append(consentBox);
  win.append(form, srLive);
  document.body.append(bubble, tooltip, win);

  // Ảnh nhân vật chỉ là trang trí; nếu thiếu file thì dùng biểu tượng dự phòng.
  const probe = new Image();
  probe.onerror = () => { bubble.classList.add('cb-no-avatar'); avatar.classList.add('cb-no-avatar'); };
  probe.src = AVATAR_URL;

  const narrowQuery = typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 599px)') : null;

  // ===== Hiển thị tin nhắn (luôn dùng textContent) =====
  function append(node, force) {
    const nearBottom = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 96;
    msgs.append(node);
    if (force || nearBottom) msgs.scrollTop = msgs.scrollHeight;
  }
  function makeBubble(role, text) {
    const box = el('div', `cb-msg cb-msg--${role}`);
    box.append(el('span', 'cb-sr', role === 'user' ? 'Bạn: ' : 'Trợ lý: '), el('span', 'cb-text', text));
    return box;
  }
  function buildLinks(links) {
    const group = attrs(el('div', 'cb-links'), { role: 'group', 'aria-label': 'Liên kết đến phòng lab' });
    for (const item of links) {
      const link = attrs(el('a', 'cb-link', item.label), { href: item.href });
      link.addEventListener('click', () => {
        const samePage = new URL(item.href, window.location.origin).pathname === window.location.pathname;
        if (samePage && narrowQuery && narrowQuery.matches) setOpen(false, { restoreFocus: false });
      });
      group.append(link);
    }
    return group;
  }
  function buildNotice(kind, text, options = {}) {
    const box = el('div', `cb-notice cb-notice--${kind}`);
    box.append(el('span', 'cb-sr', kind === 'error' ? 'Lỗi: ' : 'Lưu ý: '), el('span', 'cb-text', text));
    if (options.links && options.links.length) box.append(buildLinks(options.links));
    if (options.actions && options.actions.length) {
      const actionRow = el('div', 'cb-notice-actions');
      for (const action of options.actions) {
        const button = attrs(el('button', 'cb-action', action.label), { type: 'button' });
        button.addEventListener('click', () => action.onClick(box));
        actionRow.append(button);
      }
      box.append(actionRow);
    }
    return box;
  }
  function addLoading() {
    const box = attrs(el('div', 'cb-msg cb-msg--bot cb-msg--loading'), { role: 'status', 'aria-label': 'Trợ lý đang trả lời' });
    const dots = attrs(el('div', 'cb-loading-dots'), { 'aria-hidden': 'true' });
    dots.append(el('span'), el('span'), el('span'));
    box.append(dots);
    append(box, true);
    return box;
  }
  function markFailed(userEl) {
    userEl.classList.add('cb-msg--failed');
    if (!userEl.querySelector('.cb-failed-label')) userEl.append(el('div', 'cb-failed-label', 'Chưa gửi được'));
  }
  function unmarkFailed(userEl) {
    userEl.classList.remove('cb-msg--failed');
    const label = userEl.querySelector('.cb-failed-label');
    if (label) label.remove();
  }
  function announce(text) {
    srLive.textContent = '';
    window.setTimeout(() => { srLive.textContent = text; }, 30);
  }

  function renderWelcome() {
    const greeting = makeBubble('bot', T.greeting);
    chipsBox = el('div', 'cb-chips');
    chips = SUGGESTIONS.map((text) => {
      const chip = attrs(el('button', 'cb-chip', text), { type: 'button' });
      chip.addEventListener('click', () => { if (canAsk()) ask(text); });
      chipsBox.append(chip);
      return chip;
    });
    greeting.append(chipsBox);
    append(greeting, true);
  }
  function dismissChips() {
    if (chipsBox) { chipsBox.remove(); chipsBox = null; }
    chips = [];
  }

  // ===== Trạng thái kết nối =====
  function setStatus(next, code = '') {
    state.status = next;
    state.statusCode = code;
    statusLine.dataset.state = next;
    bubble.dataset.state = next;
    statusText.textContent = STATUS_LABEL[next];
    updateControls();
  }
  function removeStatusNotice() {
    if (statusNotice) statusNotice.remove();
    statusNotice = null;
    statusNoticeKey = '';
  }
  function renderStatusNotice() {
    if (state.status !== 'unavailable' && state.status !== 'error') { removeStatusNotice(); return; }
    let text;
    let kind;
    if (state.status === 'unavailable') {
      text = state.statusMessage || UNAVAILABLE_TEXT[state.statusCode] || UNAVAILABLE_TEXT.config_invalid;
      kind = 'warn';
    } else {
      text = planFailure(state.statusFailure || new CbError('network')).text || T.network;
      kind = 'error';
    }
    const key = `${state.status}|${text}`;
    if (statusNotice && statusNotice.isConnected && statusNoticeKey === key) return;
    removeStatusNotice();
    statusNotice = buildNotice(kind, text, {
      links: STATIC_LINKS,
      actions: [{ label: 'Kiểm tra lại', onClick: () => { refreshStatus(); } }],
    });
    statusNoticeKey = key;
    append(statusNotice);
  }
  function parseStatus(data) {
    if (!data || typeof data !== 'object' || typeof data.code !== 'string') return null;
    if (typeof data.context_generation !== 'string' || !GENERATION_RE.test(data.context_generation)) return null;
    const limits = { ...DEFAULT_LIMITS };
    const raw = data.limits;
    if (raw && typeof raw === 'object') {
      const pick = (key, fallback) => (Number.isInteger(raw[key]) && raw[key] > 0 ? raw[key] : fallback);
      limits.messageBytes = pick('message_bytes', limits.messageBytes);
      limits.historyBytes = pick('history_bytes', limits.historyBytes);
      limits.answerBytes = pick('answer_bytes', limits.answerBytes);
      limits.historyMessages = Math.floor(pick('history_messages', limits.historyMessages) / 2) * 2;
    }
    return {
      code: data.code,
      configured: data.configured === true && data.code === 'configured',
      generation: data.context_generation,
      limits,
    };
  }
  function refreshStatus() {
    if (state.statusRequest) return state.statusRequest.promise;
    const request = { controller: new AbortController() };
    state.statusMessage = '';
    setStatus('loading');
    renderStatusNotice();
    request.promise = callApi(API_STATUS, {
      method: 'GET', cache: 'no-store', credentials: 'same-origin', headers: { Accept: 'application/json' },
    }, request.controller).then((result) => {
      if (!result.ok) throw failureFromResponse(result);
      const parsed = parseStatus(result.data);
      if (!parsed) throw new CbError('bad_response');
      state.generation = parsed.generation;
      state.limits = parsed.limits;
      state.checkedAt = Date.now();
      state.statusFailure = null;
      setStatus(parsed.configured ? 'ready' : 'unavailable', parsed.code);
    }).catch((error) => {
      state.checkedAt = 0;
      state.statusFailure = normalizeError(error);
      setStatus('error', state.statusFailure.code || state.statusFailure.kind);
    }).finally(() => {
      state.statusRequest = null;
      renderStatusNotice();
    });
    state.statusRequest = request;
    return request.promise;
  }

  // ===== Gọi API với deadline tường minh =====
  function callApi(url, options, controller) {
    return new Promise((resolve, reject) => {
      let finished = false;
      const timer = window.setTimeout(() => {
        if (finished) return;
        finished = true;
        controller.abort();
        reject(new CbError('timeout'));
      }, REQUEST_TIMEOUT_MS);
      const settle = (fn, value) => {
        if (finished) return;
        finished = true;
        window.clearTimeout(timer);
        fn(value);
      };
      window.fetch(url, { ...options, signal: controller.signal }).then(async (response) => {
        let data;
        try { data = await response.json(); } catch (error) { data = undefined; }
        settle(resolve, {
          ok: response.ok, status: response.status, data, retryAfter: response.headers.get('Retry-After'),
        });
      }).catch((error) => {
        settle(reject, new CbError(error && error.name === 'AbortError' ? 'aborted' : 'network', error));
      });
    });
  }
  function normalizeError(error) {
    return error && typeof error.kind === 'string' ? error : new CbError('network', error);
  }
  function failureFromResponse(result) {
    const body = result.data && typeof result.data === 'object' ? result.data : null;
    const detail = body && body.detail && typeof body.detail === 'object' && !Array.isArray(body.detail) ? body.detail : null;
    let retryAfter = detail && Number.isFinite(detail.retry_after_seconds) ? detail.retry_after_seconds : null;
    if (retryAfter === null && typeof result.retryAfter === 'string' && /^\d+$/.test(result.retryAfter)) {
      retryAfter = Number(result.retryAfter);
    }
    return {
      kind: 'http', status: result.status,
      code: detail && typeof detail.code === 'string' ? detail.code : '',
      message: detail ? safeText(detail.message) : '',
      retryAfter: retryAfter && retryAfter > 0 ? retryAfter : null,
    };
  }
  function parseAnswer(data) {
    if (!data || typeof data !== 'object') return null;
    if (data.code === 'answered') {
      if (typeof data.answer !== 'string' || !data.answer.trim()) return null;
    } else if (data.code === 'blocked') {
      if (data.answer !== null && data.answer !== undefined) return null;
    } else {
      return null;
    }
    const seen = new Set();
    const links = [];
    for (const item of Array.isArray(data.lab_links) ? data.lab_links : []) {
      const link = safeLink(item);
      if (link && !seen.has(link.href) && links.length < 3) { seen.add(link.href); links.push(link); }
    }
    return {
      code: data.code,
      answer: data.code === 'answered' ? data.answer : '',
      message: safeText(data.message),
      truncated: data.truncated === true,
      generation: typeof data.context_generation === 'string' && GENERATION_RE.test(data.context_generation)
        ? data.context_generation : '',
      links,
    };
  }

  // ===== Hội thoại =====
  function buildHistory() {
    const maxPairs = Math.floor(state.limits.historyMessages / 2);
    const picked = [];
    let bytes = 0;
    for (let i = state.pairs.length - 1; i >= 0 && picked.length < maxPairs; i -= 1) {
      const pair = state.pairs[i];
      const size = byteLen(pair.q) + byteLen(pair.a);
      if (bytes + size > state.limits.historyBytes) break;
      bytes += size;
      picked.unshift(pair);
    }
    return picked.flatMap((pair) => [
      { role: 'user', content: pair.q },
      { role: 'assistant', content: pair.a },
    ]);
  }
  const isStale = (req) => state.current !== req || req.epoch !== state.epoch;
  function remainingCooldown() {
    return Math.max(0, Math.ceil((state.cooldownUntil - Date.now()) / 1000));
  }
  function canAsk() {
    return state.status === 'ready' && state.consent && !state.busy && remainingCooldown() === 0;
  }
  function startCooldown(seconds) {
    state.cooldownUntil = Date.now() + Math.max(1, seconds) * 1000;
    window.clearInterval(state.cooldownTimer);
    state.cooldownTimer = window.setInterval(() => {
      if (remainingCooldown() === 0) { window.clearInterval(state.cooldownTimer); state.cooldownTimer = 0; }
      updateControls();
    }, 1000);
    updateControls();
  }
  function restoreDraft(text, focusInside) {
    if (input.value.trim()) return;       // không ghi đè nội dung người dùng đang soạn
    input.value = text;
    autosize();
    updateControls();
    if (focusInside) input.focus();
  }

  async function ask(text, reuseEl) {
    if (state.busy) return;               // guard đồng bộ: chặn spam Enter/chip/click
    state.busy = true;
    const req = {
      text, epoch: state.epoch, controller: new AbortController(), abortReason: '',
      userEl: null, loadingEl: null, focusInside: win.contains(document.activeElement),
    };
    state.current = req;
    state.dirty = true;
    if (reuseEl) { unmarkFailed(reuseEl); req.userEl = reuseEl; } else { req.userEl = makeBubble('user', text); append(req.userEl, true); }
    req.loadingEl = addLoading();
    dismissChips();
    updateControls();
    const history = buildHistory();
    try {
      const result = await callApi(API_CHAT, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ context_generation: state.generation, message: text, history }),
      }, req.controller);
      if (isStale(req)) return;
      if (!result.ok) throw failureFromResponse(result);
      const data = parseAnswer(result.data);
      if (!data) throw new CbError('bad_response');
      showAnswer(req, data);
    } catch (error) {
      if (isStale(req)) return;
      await showFailure(req, normalizeError(error));
    } finally {
      if (state.current === req) {
        state.current = null;
        state.busy = false;
        req.loadingEl.remove();
        updateControls();
        const lost = document.activeElement === document.body || document.activeElement === null;
        if (state.open && req.focusInside && lost && !input.disabled) input.focus();
      }
    }
  }

  function showAnswer(req, data) {
    req.loadingEl.remove();
    if (data.generation) state.generation = data.generation;
    if (data.code === 'blocked') {
      append(buildNotice('warn', data.message || T.blocked, { links: data.links }));   // không đưa vào history
      return;
    }
    const answerEl = makeBubble('bot', data.answer);
    if (data.truncated) answerEl.append(el('div', 'cb-note', T.truncated));
    const remember = !looksSensitive(req.text) && !looksSensitive(data.answer) &&
      byteLen(data.answer) <= state.limits.answerBytes;
    if (remember) {
      state.pairs.push({ q: req.text, a: data.answer });
      while (state.pairs.length > MAX_STORED_PAIRS) state.pairs.shift();
    } else {
      answerEl.append(el('div', 'cb-note', T.notRemembered));
    }
    if (data.links.length) answerEl.append(buildLinks(data.links));
    append(answerEl);
  }

  function planFailure(failure) {
    if (failure.kind === 'timeout') return { text: T.timeout, retry: true };
    if (failure.kind === 'aborted') return { text: T.aborted, retry: true };
    if (failure.kind === 'bad_response') return { text: T.badResponse, retry: true };
    if (failure.kind === 'network') {
      const cause = failure.cause;
      const bootstrapMessage = cause && typeof cause.code === 'string' ? safeText(cause.message, 200) : '';
      return { text: bootstrapMessage || T.network, retry: true };
    }
    const rule = CODE_RULES[failure.code] || null;
    if (UNAVAILABLE_BY_CODE[failure.code]) {
      return { unavailable: UNAVAILABLE_BY_CODE[failure.code], message: failure.message, restore: true };
    }
    if (!rule) {
      if (failure.status === 404 || failure.status === 405) return { text: T.notFound };
      const server = failure.message || `Máy chủ trả về lỗi ${failure.status || ''}`.trim();
      return failure.status >= 500 ? { text: server, retry: true } : { text: server, restore: true };
    }
    const base = rule.text || failure.message || 'Không gửi được câu hỏi.';
    const plan = { text: rule.hint ? `${base} ${rule.hint}` : base, retry: !!rule.retry, restore: !!rule.restore };
    if (failure.code === 'session_changed') { plan.text = T.sessionChanged; plan.session = true; }
    const wait = failure.retryAfter || rule.cooldown || 0;
    if (wait) {
      plan.cooldown = wait;
      plan.text = `${base} Gửi lại được sau ${formatWait(wait)}.`;
    }
    return plan;
  }

  async function showFailure(req, failure) {
    req.loadingEl.remove();
    markFailed(req.userEl);
    const plan = planFailure(failure);
    if (plan.unavailable) {
      state.statusFailure = null;
      state.statusMessage = plan.message;
      setStatus('unavailable', plan.unavailable);
      renderStatusNotice();
    } else {
      const actions = plan.retry ? [{ label: 'Thử lại', onClick: (box) => retry(req, box) }] : [];
      append(buildNotice(plan.cooldown || plan.retry || plan.session ? 'warn' : 'error', plan.text, { actions }));
    }
    if (plan.cooldown) startCooldown(plan.cooldown);
    if (plan.restore) restoreDraft(req.text, req.focusInside);
    if (plan.session) {
      state.pairs = [];                    // bỏ hội thoại cũ, không phát lại
      await refreshStatus();               // kết nối lại tường minh để lấy generation mới
    }
  }
  function retry(req, box) {
    if (!canAsk()) return;
    box.remove();
    ask(req.text, req.userEl);
  }

  function clearChat() {
    state.epoch += 1;
    if (state.current) {
      state.current.abortReason = 'reset';
      state.current.controller.abort();
      state.current = null;
    }
    state.busy = false;
    state.pairs = [];
    state.dirty = false;
    msgs.textContent = '';
    statusNotice = null;
    statusNoticeKey = '';
    input.value = '';
    autosize();
    renderWelcome();
    renderStatusNotice();
    updateControls();
    announce('Đã xóa đoạn chat.');
    if (state.open && !input.disabled) input.focus();
  }

  // ===== Nhập liệu =====
  function autosize() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  }
  function submitFromInput() {
    const text = input.value.trim();
    if (!text) { updateControls(); return; }
    if (!state.consent && consentCheck) { consentCheck.focus(); updateControls(); return; }
    if (!canAsk()) { updateControls(); return; }
    if (byteLen(text) > state.limits.messageBytes) { updateControls(); return; }
    if (looksSensitive(text)) {
      append(buildNotice('error', T.sensitive), true);
      state.dirty = true;
      updateControls();
      return;                              // giữ nguyên bản nháp để người dùng sửa
    }
    input.value = '';
    autosize();
    ask(text);
  }
  function updateControls() {
    const cooling = remainingCooldown();
    const trimmed = input.value.trim();
    const bytes = trimmed ? byteLen(trimmed) : 0;
    const limit = state.limits.messageBytes;
    const over = bytes > limit;
    const mayAsk = state.status === 'ready' && state.consent && !state.busy && cooling === 0;
    input.disabled = state.status === 'unavailable';
    sendBtn.disabled = !(mayAsk && trimmed && !over);
    for (const chip of chips) chip.disabled = !mayAsk;
    clearBtn.disabled = !(state.dirty || state.busy || input.value);
    msgs.setAttribute('aria-busy', state.busy ? 'true' : 'false');
    let hint = '';
    let tone = '';
    if (cooling > 0) hint = `Hãy đợi ${formatWait(cooling)} trước khi gửi tiếp.`;
    else if (over) { hint = `Câu hỏi dài ${bytes}/${limit} byte — hãy rút ngắn.`; tone = 'error'; }
    else if (state.busy) hint = 'Đang chờ trả lời… bạn vẫn có thể soạn câu tiếp theo.';
    else if (REQUIRE_CONSENT && !state.consent) hint = 'Hãy xác nhận lưu ý ở trên trước khi gửi.';
    else if (state.status === 'loading') hint = 'Đang kiểm tra trợ lý…';
    else if (bytes >= limit * 0.7) hint = `${bytes}/${limit} byte`;
    hintEl.textContent = hint;
    hintEl.dataset.tone = tone;
  }

  // ===== Mở / đóng =====
  function setOpen(open, options = {}) {
    if (state.open === open) return;
    state.open = open;
    win.classList.toggle('open', open);
    bubble.setAttribute('aria-expanded', String(open));
    if (open) {
      const stale = state.status === 'idle' || state.status === 'error' || state.status === 'unavailable' ||
        (state.status === 'ready' && Date.now() - state.checkedAt > STATUS_TTL_MS);
      if (stale) refreshStatus();
      (input.disabled ? closeBtn : input).focus();
    } else if (options.restoreFocus !== false) {
      bubble.focus();
    }
  }

  // ===== Sự kiện =====
  bubble.addEventListener('click', () => setOpen(!state.open));
  closeBtn.addEventListener('click', () => setOpen(false));
  clearBtn.addEventListener('click', clearChat);
  form.addEventListener('submit', (event) => { event.preventDefault(); submitFromInput(); });
  input.addEventListener('input', () => { autosize(); updateControls(); });
  input.addEventListener('compositionstart', () => { state.composing = true; });
  input.addEventListener('compositionend', () => { state.composing = false; });
  input.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    if (event.isComposing || state.composing || event.keyCode === 229) return;   // đang gõ IME tiếng Việt
    event.preventDefault();
    submitFromInput();
  });
  if (consentCheck) {
    consentCheck.addEventListener('change', () => {
      state.consent = consentCheck.checked;
      consentBox.hidden = state.consent;
      updateControls();
      if (state.consent && !input.disabled) input.focus();
    });
  }
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !state.open || event.defaultPrevented || event.isComposing) return;
    const active = document.activeElement;
    if (active && active !== document.body && active !== bubble && !win.contains(active)) return;
    event.preventDefault();
    setOpen(false);
  });
  window.addEventListener('pagehide', () => {
    if (state.current) { state.current.abortReason = 'pagehide'; state.current.controller.abort(); }
    if (state.statusRequest) state.statusRequest.controller.abort();
  });
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    if (state.status === 'loading' && !state.statusRequest) setStatus('idle');
    if (state.open && state.status === 'idle') refreshStatus();
    updateControls();
  });

  // ===== Khởi tạo =====
  renderWelcome();
  updateControls();
})();
