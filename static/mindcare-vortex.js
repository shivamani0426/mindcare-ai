(() => {
  'use strict';
  const root = document.documentElement;
  const stage = document.getElementById('mc-vortex');
  if (!stage || !document.body.classList.contains('mc-world-page')) return;
  const prefs = ['(prefers-reduced-motion: reduce)','(prefers-contrast: more)','(forced-colors: active)'].map(s => matchMedia(s));
  const motion = () => !prefs.some(p => p.matches) && !document.body.classList.contains('reduced-motion');
  let destination = null, controller = null, mounted = false, busy = false;
  let timer = 0, generation = 0;
  const clear = () => {
    clearTimeout(timer);
    controller?.abort();
    controller = null;
    root.classList.remove('mc-vortex-departing','mc-vortex-arriving','mc-vortex-open');
    root.style.removeProperty('--mc-vortex-scroll-offset');
    stage.hidden = true;
    stage.dataset.phase = 'idle';
    document.querySelector('.site-shell')?.removeAttribute('inert');
    document.querySelector('.skip')?.removeAttribute('inert');
    destination = null;
    busy = false;
  };
  const fallback = () => {
    const url = destination;
    ++generation;
    clear();
    if (url && !mounted) location.assign(url);
  };
  const finish = () => {
    clear();
    const heading = document.getElementById('auth-title');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({preventScroll:true});
    }
  };
  // The landing's contraction and portal growth share a clock. Do not swap
  // the page until BOTH compositor animations have reached their end.
  const openingFinished = outgoing => new Promise(resolve => {
    const space = stage.querySelector('.mc-vortex-space');
    const expected = new Map([[outgoing,'mc-vortex-landing-infall'],[space,'mc-vortex-grow']]);
    const remaining = new Set(expected.keys());
    let done = false, watchdog, raf;
    const complete = () => {
      if (done) return;
      done = true;
      clearTimeout(watchdog);
      cancelAnimationFrame(raf);
      expected.forEach((name,element) => element.removeEventListener('animationend',onEnd));
      // Explicit terminal styles also cover Safari throttling or missing events.
      root.classList.add('mc-vortex-open');
      const landing = getComputedStyle(outgoing);
      const portal = getComputedStyle(space);
      const matrix = new DOMMatrixReadOnly(portal.transform);
      document.dispatchEvent(new CustomEvent('mindcare:vortex-opened', {detail:{
        landingOpacity:Number(landing.opacity),
        portalScale:Math.hypot(matrix.m11,matrix.m12,matrix.m13)
      }}));
      resolve();
    };
    const ended = element => {
      remaining.delete(element);
      if (!remaining.size) complete();
    };
    const onEnd = event => {
      const element = event.currentTarget;
      if (event.target === element && event.animationName === expected.get(element)) ended(element);
    };
    expected.forEach((name,element) => element.addEventListener('animationend',onEnd));
    // Observe finished promises as well as DOM events; WebKit can delay events.
    raf = requestAnimationFrame(() => {
      expected.forEach((name,element) => {
        const animation = element.getAnimations?.().find(a => a.animationName === name);
        animation?.finished.then(() => ended(element), () => {});
      });
    });
    watchdog = setTimeout(complete, 2200);
  });
  const fetchLogin = async url => {
    const response = await fetch(url, {
      credentials:'same-origin', cache:'no-store', signal:controller.signal,
      redirect:'follow', headers:{Accept:'text/html'}
    });
    if (!response.ok || response.redirected || new URL(response.url).origin !== location.origin ||
        new URL(response.url).pathname !== url.pathname) throw Error('Login navigation required');
    const doc = new DOMParser().parseFromString(await response.text(),'text/html');
    const shell = doc.querySelector('.site-shell');
    const form = shell?.querySelector('[data-auth-mode="login"] form#auth-email-form');
    const csrf = doc.querySelector('meta[name="csrf-token"]')?.content;
    if (!doc.body.classList.contains('mindcare-auth-route') || !form || !csrf ||
        !form.querySelector('input[name="csrf_token"]') || shell.querySelector('script,iframe,object,embed'))
      throw Error('Unexpected login page');
    return {doc,shell,csrf};
  };
  const open = async url => {
    const token = ++generation;
    busy = true;
    destination = url.href;
    controller = new AbortController();
    const outgoing = document.querySelector('.site-shell');
    // Preserve the visible scroll position before freezing the landing viewport.
    root.style.setProperty('--mc-vortex-scroll-offset', (-window.scrollY) + 'px');
    outgoing.inert = true;
    const skip = document.querySelector('.skip');
    if (skip) skip.inert = true;
    stage.hidden = false;
    stage.dataset.phase = 'opening';
    const opened = openingFinished(outgoing);
    root.classList.add('mc-vortex-departing');
    timer = setTimeout(fallback, 6000);
    try {
      const [page] = await Promise.all([fetchLogin(url), opened]);
      if (token !== generation) return;
      if (!motion()) { fallback(); return; }
      clearTimeout(timer);
      const next = document.importNode(page.shell,true);
      next.inert = true;
      next.querySelector('#auth-email-form').action = url.href;
      // Keep the same document and the same portal node. Only swap the real,
      // same-origin server-rendered page below it, including its CSRF token.
      window.dispatchEvent(new Event('mindcare:landing-dispose'));
      history.pushState({mindcareLogin:true},'',url.href);
      mounted = true;
      document.title = page.doc.title;
      document.querySelector('meta[name="csrf-token"]').content = page.csrf;
      const larger = document.body.classList.contains('large-text');
      document.body.className = page.doc.body.className;
      if (larger) document.body.classList.add('large-text');
      document.body.dataset.patient = '0';
      document.querySelector('.site-shell').replaceWith(next);
      window.scrollTo(0,0);
      stage.dataset.phase = 'emerging';
      root.classList.add('mc-vortex-arriving');
      root.style.removeProperty('--mc-vortex-scroll-offset');
      document.dispatchEvent(new Event('mindcare:login-mounted'));
      // The portal stays alive behind the incoming page until the emergence
      // itself ends. No second portal, flash, restart or arbitrary route delay.
      next.addEventListener('animationend', event => {
        if (event.target === next && event.animationName === 'mc-vortex-auth-emerge') finish();
      });
      timer = setTimeout(finish, 1800);
    } catch (_) {
      if (token === generation) {
        if (mounted) { clear(); location.reload(); }
        else fallback();
      }
    }
  };
  document.querySelectorAll('a[data-mc-vortex-link]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
          event.shiftKey || event.altKey || link.target || !motion() || !window.fetch || !window.AbortController) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.pathname !== '/login') return;
      event.preventDefault();
      if (!busy) open(url);
    });
  });
  prefs.forEach(p => p.addEventListener?.('change', () => {
    if (!motion() && busy) { if (mounted) finish(); else fallback(); }
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && busy) { if (mounted) finish(); else fallback(); }
  });
  // Back/forward across this enhanced navigation uses the canonical server page.
  window.addEventListener('popstate', () => { if (mounted) location.reload(); });
  window.addEventListener('pageshow', event => { if (event.persisted) clear(); });
})();
