/* Read only an ephemeral visual flag; never store authentication data. */
(() => {
  'use strict';
  try {
    const key = 'mindcare-vortex-arrival-v4';
    const pending = Number(sessionStorage.getItem(key));
    sessionStorage.removeItem(key);
    if (!pending || Date.now() - pending > 30000 || Date.now() < pending ||
        matchMedia('(prefers-reduced-motion: reduce)').matches ||
        matchMedia('(prefers-contrast: more)').matches ||
        matchMedia('(forced-colors: active)').matches) return;
    document.documentElement.classList.add('mc-vortex-arriving');
  } catch (_) { /* A blocked storage API must never block login. */ }
})();
