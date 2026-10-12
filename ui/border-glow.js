/**
 * BorderGlow — Native Vanilla JavaScript port of ReactBits BorderGlow
 * Reference: https://reactbits.dev/components/border-glow
 *
 * Provides high-performance spotlight and interactive border glow tracking pointer
 * coordinates without external dependencies.
 */
(function() {
  'use strict';

  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return;
  }

  function getCenterOfElement(el) {
    const rect = el.getBoundingClientRect();
    return [rect.width / 2, rect.height / 2];
  }

  function getEdgeProximity(el, x, y) {
    const [cx, cy] = getCenterOfElement(el);
    const dx = x - cx;
    const dy = y - cy;
    let kx = Infinity;
    let ky = Infinity;
    if (dx !== 0) kx = cx / Math.abs(dx);
    if (dy !== 0) ky = cy / Math.abs(dy);
    return Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);
  }

  function getCursorAngle(el, x, y) {
    const [cx, cy] = getCenterOfElement(el);
    const dx = x - cx;
    const dy = y - cy;
    if (dx === 0 && dy === 0) return 0;
    const radians = Math.atan2(dy, dx);
    let degrees = radians * (180 / Math.PI) + 90;
    if (degrees < 0) degrees += 360;
    return degrees;
  }

  function easeOutCubic(x) {
    return 1 - Math.pow(1 - x, 3);
  }

  function easeInCubic(x) {
    return x * x * x;
  }

  function animateValue({ start = 0, end = 100, duration = 1000, delay = 0, ease = easeOutCubic, onUpdate, onEnd }) {
    const t0 = performance.now() + delay;
    function tick() {
      const elapsed = performance.now() - t0;
      const t = Math.min(Math.max(elapsed / duration, 0), 1);
      onUpdate(start + (end - start) * ease(t));
      if (t < 1) {
        requestAnimationFrame(tick);
      } else if (onEnd) {
        onEnd();
      }
    }
    setTimeout(() => requestAnimationFrame(tick), delay);
  }

  function triggerSweep(card) {
    if (!card) return;
    const angleStart = 110;
    const angleEnd = 465;
    card.classList.add('sweep-active');
    card.style.setProperty('--cursor-angle', `${angleStart}deg`);

    animateValue({
      duration: 500,
      onUpdate: (v) => card.style.setProperty('--edge-proximity', v.toFixed(2))
    });
    animateValue({
      ease: easeInCubic,
      duration: 1500,
      end: 50,
      onUpdate: (v) => {
        const deg = (angleEnd - angleStart) * (v / 100) + angleStart;
        card.style.setProperty('--cursor-angle', `${deg.toFixed(2)}deg`);
      }
    });
    animateValue({
      ease: easeOutCubic,
      delay: 1500,
      duration: 2250,
      start: 50,
      end: 100,
      onUpdate: (v) => {
        const deg = (angleEnd - angleStart) * (v / 100) + angleStart;
        card.style.setProperty('--cursor-angle', `${deg.toFixed(2)}deg`);
      }
    });
    animateValue({
      ease: easeInCubic,
      delay: 2500,
      duration: 1500,
      start: 100,
      end: 0,
      onUpdate: (v) => card.style.setProperty('--edge-proximity', v.toFixed(2)),
      onEnd: () => card.classList.remove('sweep-active')
    });
  }

  function setupCard(card) {
    if (!card || card._borderGlowBound) return;
    card._borderGlowBound = true;

    // Ensure .edge-light span is injected for outer spotlight glow
    if (!card.querySelector(':scope > .edge-light')) {
      const edgeSpan = document.createElement('span');
      edgeSpan.className = 'edge-light';
      edgeSpan.setAttribute('aria-hidden', 'true');
      card.prepend(edgeSpan);
    }

    let rafId = null;
    let pendingX = 0;
    let pendingY = 0;

    function onPointerMove(e) {
      const rect = card.getBoundingClientRect();
      pendingX = e.clientX - rect.left;
      pendingY = e.clientY - rect.top;

      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          rafId = null;
          const edge = getEdgeProximity(card, pendingX, pendingY);
          const angle = getCursorAngle(card, pendingX, pendingY);
          card.style.setProperty('--edge-proximity', (edge * 100).toFixed(2));
          card.style.setProperty('--cursor-angle', `${angle.toFixed(2)}deg`);
        });
      }
    }

    function onPointerLeave() {
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      card.style.setProperty('--edge-proximity', '0');
    }

    card.addEventListener('pointermove', onPointerMove, { passive: true });
    card.addEventListener('pointerleave', onPointerLeave, { passive: true });

    if (card.dataset.animated === 'true') {
      triggerSweep(card);
    }
  }

  function initBorderGlow() {
    const cards = document.querySelectorAll('.border-glow, .border-glow-card');
    cards.forEach(setupCard);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBorderGlow);
  } else {
    initBorderGlow();
  }

  if (typeof MutationObserver !== 'undefined' && document.body) {
    const observer = new MutationObserver(() => initBorderGlow());
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.initBorderGlow = initBorderGlow;
  window.triggerBorderSweep = triggerSweep;
})();

