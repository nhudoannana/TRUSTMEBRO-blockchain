// Public pages have no RAM lease. Bootstrap lazily before this page's first API.
(function () {
  const nativeFetch = globalThis.fetch.bind(globalThis);
  let bootstrap = null, notice, message, retry;
  function showSessionNotice(error) {
    if (!notice) {
      notice = document.createElement('section'); notice.id = 'simulation-session-notice';
      notice.className = 'panel result warning'; notice.setAttribute('role', 'status');
      message = document.createElement('p'); retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'secondary'; retry.textContent = 'Thử kết nối phiên lại';
      notice.append(message, retry); document.body.prepend(notice);
      retry.onclick = async () => {
        retry.disabled = true;
        try {
          await ready(); notice.hidden = true;
          globalThis.window.dispatchEvent(new Event('simulation-ready'));
        } catch { /* The notice retains the actual connection error. */ }
        finally { retry.disabled = false; }
      };
    }
    message.textContent = error.code === 'session_capacity'
      ? 'Máy chủ đang đủ phiên mô phỏng. Bạn vẫn có thể đọc bài học và dùng SHA-256. Hãy thử kết nối lại khi có phiên trống; không phiên đang dùng nào bị xóa.'
      : 'Chưa kết nối được phiên mô phỏng. Hãy thử lại. ' + error.message;
    notice.hidden = false;
  }
  function ready() {
    if (!bootstrap) {
      bootstrap = nativeFetch('/api/session/bootstrap', { credentials: 'same-origin', cache: 'no-store' })
        .then(async response => {
          const data = await response.json();
          if (!response.ok) {
            const error = new Error(data.detail?.message || 'Không kết nối được phiên mô phỏng.');
            error.code = data.detail?.code; throw error;
          }
          if (notice) notice.hidden = true;
          return data;
        }).catch(error => { bootstrap = null; showSessionNotice(error); throw error; });
    }
    return bootstrap;
  }
  globalThis.fetch = async (input, options) => {
    const path = typeof input === 'string' ? input.split('?')[0] : input.url;
    if (!path?.startsWith('/api/') || ['/api/health', '/api/session/bootstrap'].includes(path))
      return nativeFetch(input, options);
    await ready();
    const response = await nativeFetch(input, options);
    if (response.status === 503) {
      const data = await response.clone().json();
      if (data.detail?.code === 'session_capacity') {
        bootstrap = null;
        showSessionNotice({ code: data.detail.code, message: data.detail.message });
      }
    }
    return response;
  };
})();
