(() => {
  'use strict';

  // Prevent multiple injections
  if (document.getElementById('chatbot-bubble')) return;

  const SUGGESTIONS = [
    'Merkle Root dùng để làm gì?',
    'Khác biệt giữa PoW và PoS?',
    'Hiệu ứng tuyết lở SHA-256 là gì?',
    'Dự án này demo theo thứ tự nào?'
  ];

  let history = [];
  let isOpen = false;

  // Create Bubble Button & Tooltip
  const bubble = document.createElement('button');
  bubble.id = 'chatbot-bubble';
  bubble.type = 'button';
  bubble.setAttribute('aria-label', 'Mở trợ lý AI');
  bubble.title = 'Trợ lý TRUSTMEBRO AI';

  const tooltip = document.createElement('div');
  tooltip.id = 'chatbot-tooltip';
  tooltip.textContent = '💬 Trợ lý TRUSTMEBRO AI';

  // Create Chat Window
  const win = document.createElement('div');
  win.id = 'chatbot-window';
  win.innerHTML = `
    <div class="cb-header">
      <div class="cb-profile">
        <div class="cb-avatar"></div>
        <div class="cb-title-box">
          <h4 class="cb-title">Trợ lý TRUSTMEBRO AI</h4>
          <p class="cb-status">Sẵn sàng hỗ trợ</p>
        </div>
      </div>
      <div class="cb-actions">
        <button type="button" class="cb-btn-icon" id="cb-close" title="Thu nhỏ">✕</button>
      </div>
    </div>
    <div class="cb-messages" id="cb-messages">
      <div class="cb-msg bot">
        👋 Xin chào! Mình là <b>Trợ lý AI</b> của TrustMeBro. Bạn có thể hỏi mình về lý thuyết mật mã & blockchain (SHA-256, Merkle, PoW/PoS, Chữ ký số...), các bài lab thực hành, hoặc cách sử dụng dự án!
        <div class="cb-chips" id="cb-chips">
          ${SUGGESTIONS.map(s => `<button type="button" class="cb-chip">${s}</button>`).join('')}
        </div>
      </div>
    </div>
    <form class="cb-footer" id="cb-form">
      <input type="text" class="cb-input" id="cb-input" placeholder="Hỏi về blockchain hoặc dự án..." autocomplete="off" />
      <button type="submit" class="cb-send-btn" id="cb-send" aria-label="Gửi tin nhắn">➤</button>
    </form>
  `;

  document.body.appendChild(bubble);
  document.body.appendChild(tooltip);
  document.body.appendChild(win);

  const msgsContainer = document.getElementById('cb-messages');
  const inputEl = document.getElementById('cb-input');
  const formEl = document.getElementById('cb-form');
  const sendBtn = document.getElementById('cb-send');
  const closeBtn = document.getElementById('cb-close');

  function toggleWindow(show) {
    isOpen = typeof show === 'boolean' ? show : !isOpen;
    if (isOpen) {
      win.classList.add('open');
      inputEl.focus();
    } else {
      win.classList.remove('open');
    }
  }

  bubble.addEventListener('click', () => toggleWindow());
  closeBtn.addEventListener('click', () => toggleWindow(false));

  // Suggestion chips
  win.addEventListener('click', (e) => {
    if (e.target.classList.contains('cb-chip')) {
      const text = e.target.textContent.trim();
      sendMessage(text);
    }
  });

  function appendMessage(role, text) {
    const div = document.createElement('div');
    div.className = `cb-msg ${role}`;
    // Simple formatting for bold and linebreaks
    const formatted = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
      .replace(/\n/g, '<br/>');
    div.innerHTML = formatted;
    msgsContainer.appendChild(div);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;
  }

  function showLoading() {
    const div = document.createElement('div');
    div.className = 'cb-msg bot';
    div.id = 'cb-loading-msg';
    div.innerHTML = `
      <div class="cb-loading-dots">
        <span></span><span></span><span></span>
      </div>
    `;
    msgsContainer.appendChild(div);
    msgsContainer.scrollTop = msgsContainer.scrollHeight;
  }

  function removeLoading() {
    const el = document.getElementById('cb-loading-msg');
    if (el) el.remove();
  }

  async function sendMessage(text) {
    if (!text || !text.trim()) return;
    text = text.trim();
    appendMessage('user', text);
    history.push({ role: 'user', content: text });
    inputEl.value = '';
    sendBtn.disabled = true;
    showLoading();

    try {
      const resp = await fetch('/api/chatbot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: history.slice(-6)
        })
      });

      removeLoading();

      if (resp.ok) {
        const data = await resp.json();
        const reply = data.answer || 'Mình chưa có câu trả lời cho câu hỏi này.';
        appendMessage('bot', reply);
        history.push({ role: 'assistant', content: reply });
      } else {
        // Fallback message if server endpoint is offline or static server
        appendMessage('bot', '⚠️ Không thể kết nối tới server API (`/api/chatbot`). Nếu bạn đang chạy server tĩnh, hãy mở terminal chạy: `.\\.venv\\Scripts\\python.exe -m uvicorn api.wallet_api:app --port 8000` hoặc mở giao diện Streamlit tại `http://localhost:8501` nhé!');
      }
    } catch (err) {
      removeLoading();
      appendMessage('bot', '⚠️ Kết nối tới máy chủ bị gián đoạn. Bạn có thể mở giao diện Streamlit Trợ lý AI (port 8501) hoặc khởi động server uvicorn nhé!');
    } finally {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage(inputEl.value);
  });
})();

