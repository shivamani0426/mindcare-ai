/* Decorative CSS 3D parallax: one frame per pointer update, no render loop. */
(() => {
  'use strict';
  const hero = document.querySelector('.mc-world-hero');
  const depth = hero?.querySelector('.mc-cinematic-depth');
  if (!depth) return;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const contrast = matchMedia('(prefers-contrast: more)');
  const pointer = matchMedia('(hover: hover) and (pointer: fine)');
  let frame = 0, x = 0, y = 0;
  const active = () => pointer.matches && !reduce.matches && !contrast.matches &&
    !document.hidden && document.body.classList.contains('mc-hero-resting') &&
    !document.body.classList.contains('mc-hero-out-of-view');
  const reset = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    depth.style.removeProperty('--mc-tilt-x');
    depth.style.removeProperty('--mc-tilt-y');
  };
  const paint = () => {
    frame = 0;
    if (!active()) { reset(); return; }
    depth.style.setProperty('--mc-tilt-x', (y * -5).toFixed(2) + 'deg');
    depth.style.setProperty('--mc-tilt-y', (x * 7).toFixed(2) + 'deg');
  };
  hero.addEventListener('pointermove', event => {
    if (!active() || event.pointerType === 'touch') return;
    const rect = hero.getBoundingClientRect();
    x = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - .5) * 2));
    y = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - .5) * 2));
    if (!frame) frame = requestAnimationFrame(paint);
  }, {passive:true});
  hero.addEventListener('pointerleave', reset, {passive:true});
  [reduce, contrast, pointer].forEach(media => media.addEventListener?.('change', reset));
  document.addEventListener('visibilitychange', reset);
  window.addEventListener('pagehide', reset);
})();
