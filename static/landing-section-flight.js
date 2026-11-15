/* MindCare public landing sections: the patient dashboard's four-edge fly-in
 * language, applied AFTER the existing paper -> bubble -> hero sequence.
 * Does not alter hero, links, accessibility, page layout or backend.
 * Web Animations API only; no third-party assets, timers per card, or scroll polling.
 */
(() => {
  'use strict';
  const root = document.querySelector('.mc-world-root');
  if (!root || !document.body.classList.contains('mc-world-page')) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const contrast = window.matchMedia('(prefers-contrast: more)');
  const noMotion = () => reduce.matches || contrast.matches ||
    document.body.classList.contains('reduced-motion') ||
    document.body.classList.contains('high-contrast');
  if (noMotion() || !Element.prototype.animate || !('IntersectionObserver' in window)) return;

  const selectors = [
    '.mc-world-manifesto', '.mc-world-media', '.mc-world-capabilities',
    '.mc-world-product', '.mc-world-access',
    '.mc-world-footer', '.mc-world-discover'
  ];
  // Identify actual existing sections instead of manipulating the page structure.
  const sections = [...new Set(selectors.flatMap(s => [...root.querySelectorAll(s)]))];
  if (!sections.length) return;
  let completed = false;
  let observer = null;
  let readyObserver = null;
  const played = new WeakSet();
  const queues = new Set();
  const animations = new Set();
  const itemSelectors = ':scope > :is(h2,h3,p,span,div,a,button,figure), h2, h3, .mc-section-lead, .mc-mini-pill, .mc-gallery-card, .mc-product-frame, .mc-media-frame, .mc-cap-tabs, .mc-cap-content, .mc-underlined-link';
  const itemsFor = section => {
    const all = [...section.querySelectorAll(itemSelectors)].filter(el => {
      if (el.closest('[hidden],dialog,[aria-hidden="true"]')) return false;
      if (!el.getClientRects().length) return false;
      if (el.closest('.mc-demo-app') && !el.classList.contains('mc-product-frame')) return false;
      return true;
    });
    // Choose the outermost visible UI pieces, not both a card and every child.
    const top = [];
    for (const el of all) {
      if (!top.some(parent => parent.contains(el))) top.push(el);
      if (top.length >= 18) break;
    }
    return top;
  };
  const cancelAll = () => {
    completed = true;
    observer?.disconnect();
    readyObserver?.disconnect();
    queues.clear();
    animations.forEach(animation => animation.cancel());
    animations.clear();
    sections.forEach(section => section.removeAttribute('data-mc-section-flight'));
  };
  const animateSection = section => {
    if (completed || noMotion() || played.has(section)) return;
    played.add(section);
    const items = itemsFor(section);
    section.dataset.mcSectionFlight = 'arriving';
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    // Avoid animating large section containers and their children simultaneously.
    items.forEach((el, index) => {
      const rect = el.getBoundingClientRect();
      const side = index % 4;
      const fromX = side === 0 ? Math.max(-260, -rect.right - 22)
        : side === 1 ? Math.min(260, vw - rect.left + 22)
        : side === 2 ? -36 : 36;
      const fromY = side === 2 ? -Math.min(200, rect.bottom + 22)
        : side === 3 ? Math.min(200, vh - rect.top + 22) : (side === 0 ? -14 : 14);
      const keyframes = [
        {transform:`translate3d(${fromX}px,${fromY}px,0) rotate(${side % 2 ? 2 : -2}deg)`,opacity:0,offset:0},
        {transform:'translate3d(0,0,0) rotate(0deg)',opacity:1,offset:1}
      ];
      const animation = el.animate(keyframes, {
        duration: matchMedia('(max-width: 700px)').matches ? 560 : 760,
        delay: Math.min(index * 85, 680),
        easing:'cubic-bezier(.17,.83,.27,1)',fill:'both'
      });
      animations.add(animation);
      animation.finished.then(() => {
        animation.cancel();
        animations.delete(animation);
      }).catch(() => animations.delete(animation));
    });
    section.dataset.mcSectionFlight = 'ready';
  };
  const heroIsBusy = () => document.body.classList.contains('mc-paper-active') ||
    document.body.classList.contains('mc-paper-revealing') ||
    document.body.classList.contains('mc-hero-assembling');
  const flush = () => {
    if (heroIsBusy()) return;
    for (const section of queues) animateSection(section);
    queues.clear();
    readyObserver?.disconnect();
    readyObserver = null;
  };
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      if (heroIsBusy()) queues.add(entry.target);
      else animateSection(entry.target);
    }
    if (queues.size && !readyObserver) {
      readyObserver = new MutationObserver(flush);
      readyObserver.observe(document.body,{attributes:true,attributeFilter:['class']});
    }
  }, {rootMargin:'0px 0px -12% 0px',threshold:0.06});
  for (const section of sections) observer.observe(section);
  reduce.addEventListener?.('change',() => {if (noMotion()) cancelAll()});
  contrast.addEventListener?.('change',() => {if (noMotion()) cancelAll()});
  window.addEventListener('pagehide',cancelAll,{once:true});
})();