(() => {
  'use strict';
  const root = document.documentElement;
  const stage = document.getElementById('mc-vortex');
  if (!stage) return;
  const key = 'mindcare-vortex-arrival-v4';
  const prefs = ['(prefers-reduced-motion: reduce)','(prefers-contrast: more)','(forced-colors: active)'].map(s => matchMedia(s));
  const motion = () => !prefs.some(p => p.matches) && !document.body.classList.contains('reduced-motion');
  let timer = 0, destination = null;
  const cleanup = () => {
    clearTimeout(timer);
    root.classList.remove('mc-vortex-departing','mc-vortex-arriving');
    stage.hidden = true;
    destination = null;
  };
  if (root.classList.contains('mc-vortex-arriving')) {
    stage.hidden = false;
    timer = setTimeout(cleanup, 1750);
  }
  const navigate = () => {
    if (!destination) return;
    const url = destination;
    destination = null;
    clearTimeout(timer);
    location.assign(url);
  };
  document.querySelectorAll('a[data-mc-vortex-link]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
          event.shiftKey || event.altKey || link.target || !motion()) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.pathname !== '/login') return;
      if (destination) { event.preventDefault(); return; }
      try { sessionStorage.setItem(key, String(Date.now())); } catch (_) { return; }
      event.preventDefault();
      destination = url.href;
      stage.hidden = false;
      root.classList.add('mc-vortex-departing');
      timer = setTimeout(navigate, 1350);
    });
  });
  prefs.forEach(p => p.addEventListener?.('change', () => {
    if (!motion()) {
      if (destination) { try { sessionStorage.removeItem(key); } catch (_) {} navigate(); }
      else cleanup();
    }
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { if (destination) navigate(); else cleanup(); }
  });
  // A restored back/forward-cache page must not keep an old transition.
  addEventListener('pageshow', event => { if (event.persisted) cleanup(); });
})();
