(() => {
  'use strict';
  if (!document.body.classList.contains('mc-world-page')) return;

  // A robust two-phase sequence: FIRST unfold the paper, THEN build the hero.
  // Previously both animations ran together, with the hero hidden beneath
  // the opaque paper overlay. Keep all existing links and artwork untouched.
  const paperIntro = document.getElementById('mc-paper-intro');
  const paperTouch = document.getElementById('mc-paper-touch');
  const paperSkip = document.getElementById('mc-paper-skip');
  const replay = document.getElementById('mc-hero-replay');
  const world = document.querySelector('.mc-world-root');
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const introStorageKey = 'mindcare-paper-unfold-seen-v2';
  const motionAllowed = () => !motionPreference.matches &&
    !document.body.classList.contains('reduced-motion');
  let introSeen = false;
  try { introSeen = window.sessionStorage.getItem(introStorageKey) === '1'; }
  catch (_) { /* Private mode may restrict session storage. */ }
  let phase = 'ready';
  let sequenceToken = 0;
  let paperTimer = null;
  let heroTimer = null;
  const clearSequenceTimers = () => {
    window.clearTimeout(paperTimer);
    window.clearTimeout(heroTimer);
  };
  const finishImmediately = () => {
    ++sequenceToken;
    clearSequenceTimers();
    phase = 'ready';
    paperIntro.hidden = true;
    world.inert = false;
    document.body.classList.remove('mc-paper-active','mc-paper-revealing','mc-hero-assembling');
    document.body.classList.add('mc-hero-resting');
    if (replay) replay.hidden = !motionAllowed();
    try { window.sessionStorage.setItem(introStorageKey, '1'); }
    catch (_) {}
  };
  const beginHeroAssembly = () => {
    phase = 'assembling';
    const token = ++sequenceToken;
    // Remove paper BEFORE animation class is applied. This ensures the full
    // growing orb and all four-edge text flights are actually visible.
    paperIntro.hidden = true;
    world.inert = false;
    document.body.classList.remove('mc-paper-active','mc-paper-revealing','mc-hero-resting');
    if (replay) replay.hidden = true;
    // Force layout between the two animation phases to avoid canceled or
    // coalesced style changes when Chromium renders two states in one frame.
    void document.body.offsetHeight;
    document.body.classList.add('mc-hero-assembling');
    heroTimer = window.setTimeout(() => {
      if (sequenceToken !== token) return;
      document.body.classList.remove('mc-hero-assembling');
      document.body.classList.add('mc-hero-resting');
      phase = 'ready';
      if (replay) replay.hidden = !motionAllowed();
    }, 2480);
  };
  const unfoldPaper = () => {
    if (phase !== 'paper') return;
    if (!motionAllowed()) { finishImmediately(); return; }
    phase = 'unfolding';
    const token = ++sequenceToken;
    document.body.classList.add('mc-paper-revealing');
    try { window.sessionStorage.setItem(introStorageKey, '1'); }
    catch (_) {}
    // Paper completes at 1400ms; begin content only once it is out of sight.
    paperTimer = window.setTimeout(() => {
      if (sequenceToken !== token) return;
      beginHeroAssembly();
    }, 1450);
  };
  const showPaper = () => {
    if (!motionAllowed() || !paperIntro || !paperTouch || !paperSkip || !world) {
      finishImmediately(); return;
    }
    ++sequenceToken;
    clearSequenceTimers();
    phase = 'paper';
    document.body.classList.remove('mc-hero-assembling','mc-hero-resting','mc-paper-revealing');
    paperIntro.hidden = false;
    world.inert = true;
    if (replay) replay.hidden = true;
    document.body.classList.add('mc-paper-active');
    paperTouch.focus({preventScroll:true});
  };
  if (paperIntro && paperTouch && paperSkip && world) {
    paperTouch.addEventListener('click', unfoldPaper);
    paperSkip.addEventListener('click', finishImmediately);
    paperIntro.addEventListener('keydown', event => {
      if (event.key === 'Escape') finishImmediately();
    });
    replay?.addEventListener('click',showPaper);
    motionPreference.addEventListener?.('change', () => {
      if (!motionAllowed()) finishImmediately();
    });
    if (motionAllowed() && !introSeen && !window.location.hash) showPaper();
    else finishImmediately();
  }

  // Three fully accessible, keyboard-operable capability tabs.
  const tabs = [...document.querySelectorAll('.mc-cap-tab[role="tab"]')];
  const activateTab = (selected, focus = false) => {
    tabs.forEach(tab => {
      const active = tab === selected;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
    if (focus) selected.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', event => {
      let targetIndex;
      if (event.key === 'ArrowRight') targetIndex = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') targetIndex = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') targetIndex = 0;
      else if (event.key === 'End') targetIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[targetIndex], true);
    });
  });

  // Two simulated patient/caregiver previews; no autoplay or network traffic.
  const slideButtons = [...document.querySelectorAll('[data-mc-slide]')];
  const slides = [...document.querySelectorAll('.mc-product-slide')];
  const showSlide = index => {
    if (index < 0 || index >= slides.length) return;
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    slideButtons.forEach((button, i) => {
      button.setAttribute('aria-pressed', String(i === index));
    });
  };
  slideButtons.forEach((button, index) => {
    button.addEventListener('click', () => showSlide(index));
    button.addEventListener('keydown', event => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + slideButtons.length) % slideButtons.length;
      showSlide(next);
      slideButtons[next].focus();
    });
  });

  // Highlight actual section in sticky nav, without moving keyboard focus.
  const navLinks = [...document.querySelectorAll('.mc-world-nav-links a[href^="#"]')];
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (!visible.length) return;
      const id = '#' + visible[0].target.id;
      navLinks.forEach(link => {
        if (link.getAttribute('href') === id) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
    }, {rootMargin: '-70px 0px -40% 0px', threshold: [0, .15, .4]});
    ['overview', 'capabilities', 'discover', 'access'].forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
  }
})();
