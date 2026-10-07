// Final text is immediate; only the aria-hidden digits roll, once per new value.
globalThis.TrustCounter = (() => {
  const previous = new Map();
  const format = (value, decimals = 0) => value.toLocaleString('vi-VN', {
    useGrouping: false, minimumFractionDigits: decimals, maximumFractionDigits: decimals
  });
  function clear(prefix) {
    for (const [key, state] of previous) if (key.startsWith(prefix)) {
      state.animations.forEach(a => a.cancel()); previous.delete(key);
    }
  }
  function render(element, value, { key, decimals = 0 } = {}) {
    const old = previous.get(key);
    old?.animations.forEach(a => a.cancel());
    element.replaceChildren();
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      element.textContent = '—'; previous.delete(key); return;
    }
    const text = format(value, decimals), animations = [];
    const accessible = document.createElement('span'); accessible.textContent = text;
    Object.assign(accessible.style, { position: 'absolute', width: '1px', height: '1px',
      padding: '0', overflow: 'hidden', clipPath: 'inset(50%)', whiteSpace: 'nowrap' });
    const digits = document.createElement('span'); digits.setAttribute('aria-hidden', 'true');
    Object.assign(digits.style, { display: 'inline-flex', fontVariantNumeric: 'tabular-nums',
      minWidth: `${Math.max(3, old?.width || 0, text.length)}ch` });
    const animate = old && old.text !== text && !globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    for (let i = 0; i < text.length; i++) {
      const character = text[i], column = document.createElement('span');
      Object.assign(column.style, { display: 'inline-block', position: 'relative',
        height: '1.2em', lineHeight: '1.2em', overflow: 'hidden', width: /\d/.test(character) ? '1ch' : 'auto' });
      const digit = document.createElement('span'); digit.textContent = character;
      digit.style.display = 'block'; column.append(digit);
      const before = old?.text[old.text.length - text.length + i];
      if (animate && /\d/.test(character) && before !== character && typeof digit.animate === 'function') {
        const direction = value < old.value ? -1 : 1;
        if (before != null && /\d/.test(before)) {
          const outgoing = document.createElement('span'); outgoing.textContent = before;
          Object.assign(outgoing.style, { position: 'absolute', inset: '0' }); column.append(outgoing);
          animations.push(outgoing.animate([{ transform: 'translateY(0)' },
            { transform: `translateY(${-direction * 100}%)` }], { duration: 320, easing: 'ease-out', fill: 'forwards' }));
        }
        animations.push(digit.animate([{ transform: `translateY(${direction * 100}%)` },
          { transform: 'translateY(0)' }], { duration: 320, easing: 'ease-out' }));
      }
      digits.append(column);
    }
    element.append(accessible, digits);
    previous.set(key, { text, value, width: Math.max(old?.width || 0, text.length), animations });
  }
  return { render, clear };
})();
