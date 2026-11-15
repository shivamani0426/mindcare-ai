/* Fly-in everywhere, no stacks: preserve original position and interaction.
   Decorative, per-element Web Animations. Never hides emergency/help controls.
   Every private screen can be used without animations, JS or storage. */
(() => {
  'use strict';
  if (!document.body.classList.contains('mc-app-shell')) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const disabled = () => reduced.matches ||
    document.body.classList.contains('reduced-motion') ||
    document.body.classList.contains('high-contrast');
  // Never cloak controls needed for urgent support.
  const urgent = '.patient-support-quick, .simple-bottom-actions, .sos-callout, .incoming-call, .milo-roamer, .milo-help-panel, [data-quick-support-button]';
  if (disabled() || !Element.prototype.animate) return;
  const main = document.querySelector('main');
  if (!main) return;

  const curtain = document.createElement('div');
  curtain.className = 'mc-flight-curtain';
  curtain.setAttribute('aria-hidden', 'true');
  document.body.appendChild(curtain);
  const skip = document.createElement('button');
  skip.className = 'mc-flight-skip';
  skip.type = 'button';
  skip.textContent = 'Skip animation';
  skip.setAttribute('aria-label', 'Skip flying entrance animation');
  document.body.appendChild(skip);
  document.body.dataset.flightState = 'arriving';

  const targets = new Set();
  // Select individual text, headings, images and actionable interface pieces.
  // Skip decorative nested content when the parent already provides a card.
  const selector = [
    '.page-heading', '.welcome-banner', '.simple-banner', '.caregiver-hero',
    '.patient-top-tiles > *', '.caregiver-stats > *',
    '.caregiver-middle-grid > *', '.dashboard-side > *',
    '.game-shortcuts > *', '.stats-row > *', '.simple-actions > *',
    '.games-catalog > *', '.family-grid > *', '.family-gallery-wrap',
    '.reminder-row', '.contact-row', '.caregiver-patient-card',
    'h1','h2','h3','p','.eyebrow','.soft-label','label',
    '.button','button','.panel','.feature-icon','.clinical-note',
    '.patient-selector','img','.caregiver-filter-bar'
  ].join(',');
  main.querySelectorAll(selector).forEach(el => {
    if (el.closest(urgent)) return;
    if (el.closest('dialog, [hidden]')) return;
    if (el.matches('input,textarea,select')) return;
    if (el.closest('.family-photo-viewer')) return;
    if (el.getClientRects().length === 0) return;
    targets.add(el);
  });

  let pending = [];
  let skipRequested = false;
  const now = () => window.performance?.now?.() || Date.now();
  const startAt = now();
  const initial = [];
  const later = [];
  [...targets].forEach((el,index) => {
    const rect = el.getBoundingClientRect();
    const item = {el,index};
    el.setAttribute('data-flight-item','');
    if (rect.top < window.innerHeight + 160 && rect.bottom > -100) initial.push(item);
    else later.push(item);
  });

  const finishAll = () => {
    if (skipRequested) return;
    skipRequested = true;
    pending.forEach(a => {try {a.finish();} catch (_) {a.cancel();}});
    pending = [];
    curtain.remove();
    skip.remove();
    [...targets].forEach(el => el.removeAttribute('data-flight-item'));
    document.body.dataset.flightState = 'ready';
    observer?.disconnect();
  };
  let observer = null;
  skip.addEventListener('click', finishAll);
  reduced.addEventListener?.('change', () => {if (disabled()) finishAll();});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !skipRequested) finishAll();
  });

  const animateItem = ({el,index},delay=0) => {
    if (skipRequested || !el.isConnected || disabled()) return;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const vw = window.innerWidth, vh = window.innerHeight;
    const side = index % 4;
    const fromX = side === 0 ? -(rect.right + 70) :
      side === 1 ? (vw - rect.left + 70) : (side === 2 ? vw*.14 : -vw*.14);
    const fromY = side === 2 ? -(rect.bottom + 80) :
      side === 3 ? vh - rect.top + 85 : (side === 0 ? -36 : 36);
    const a = el.animate([
      {transform:`translate3d(${fromX}px,${fromY}px,0) rotate(${side%2?-4:4}deg) scale(.91)`,
       opacity:0,filter:'blur(8px)',offset:0},
      {transform:'translate3d(0,0,0) rotate(0deg) scale(1)',
       opacity:1,filter:'blur(0)',offset:1}
    ],{duration:930,delay,easing:'cubic-bezier(.17,.83,.27,1)',fill:'both'});
    pending.push(a);
    a.finished.then(() => {
      a.cancel();
      el.removeAttribute('data-flight-item');
    }).catch(() => {});
  };

  const header = document.querySelector('.site-header');
  if (header && !disabled()) {
    const a = header.animate([
      {opacity:0,transform:'translateY(-110px)',filter:'blur(8px)'},
      {opacity:1,transform:'translateY(0)',filter:'blur(0)'}
    ],{duration:1050,delay:110,easing:'cubic-bezier(.17,.83,.27,1)',fill:'both'});
    pending.push(a);
    a.finished.then(()=>a.cancel()).catch(()=>{});
  }
  // Make the entire window briefly dark, then peel it away as the text arrives.
  const shade = curtain.animate([
    {opacity:1,offset:0},{opacity:1,offset:.26},{opacity:0,offset:1}
  ],{duration:850,easing:'ease-out',fill:'both'});
  pending.push(shade);
  shade.finished.then(() => curtain.remove()).catch(()=>{});

  initial.forEach((item,n) => animateItem(item,200+Math.min(1450,n*48)));
  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        const item = later.find(x => x.el === entry.target);
        if (item) animateItem(item,65);
      });
    },{rootMargin:'0px 0px 70px 0px',threshold:.01});
    later.forEach(item => observer.observe(item.el));
  }
  // Interactions must not depend on delayed animations; safe fallback.
  const duration = 3000;
  window.setTimeout(() => {
    if (skipRequested) return;
    curtain.remove();
    skip.remove();
    document.body.dataset.flightState = 'ready';
  },duration);
})();
