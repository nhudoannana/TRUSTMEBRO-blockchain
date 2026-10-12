(function() {
  function initNavbar() {
    const menuBtn = document.getElementById('menu-btn');
    const mainNav = document.getElementById('main-nav');
    if (menuBtn && mainNav && !menuBtn._hasNavbarListener) {
      menuBtn._hasNavbarListener = true;
      menuBtn.addEventListener('click', function() {
        const open = mainNav.classList.toggle('open');
        menuBtn.setAttribute('aria-expanded', String(open));
      });
    }
  }
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initNavbar);
    } else {
      initNavbar();
    }
  }
})();
