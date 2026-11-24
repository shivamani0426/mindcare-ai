(() => {
  'use strict';
  if (!document.body.classList.contains('mc-world-page')) return;

  // First-visit portal. The real hero is already mounted behind both leaves.
  const door = document.getElementById('mc-door-intro');
  const enter = document.getElementById('mc-door-enter');
  const skip = document.getElementById('mc-door-skip');
  const replay = document.getElementById('mc-hero-replay');
  const world = document.querySelector('.mc-world-root');
  const skipLink = document.querySelector('.skip');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const contrast = matchMedia('(prefers-contrast: more)');
  const forced = matchMedia('(forced-colors: active)');
  const storageKey = 'mindcare-door-entered-v3';
  const motionAllowed = () => !reduce.matches && !contrast.matches && !forced.matches &&
    !document.body.classList.contains('reduced-motion');
  let seen = false;
  try { seen = sessionStorage.getItem(storageKey) === '1'; } catch (_) {}
  let phase = 'ready', target = 0, progress = 0, frame = 0, heroTimer = 0;
  let touchY = null, focusAfter = false;
  const clamp = value => Math.max(0, Math.min(1, value));
  const remember = () => { try { sessionStorage.setItem(storageKey, '1'); } catch (_) {} };
  const paint = () => {
    door.style.setProperty('--door-progress', progress.toFixed(4));
    door.style.setProperty('--door-angle', (progress * 98).toFixed(2) + 'deg');
    door.style.setProperty('--door-negative-angle', (-progress * 98).toFixed(2) + 'deg');
    door.dataset.progress = progress.toFixed(3);
  };
  const stop = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    clearTimeout(heroTimer);
    touchY = null;
  };
  const release = () => {
    door.hidden = true;
    world.inert = false;
    if (skipLink) skipLink.inert = false;
    document.body.classList.remove('mc-door-active');
    remember();
    if (focusAfter) {
      world.querySelector('.mc-hero-enter')?.focus({preventScroll:true});
      focusAfter = false;
    }
  };
  const finishImmediately = () => {
    const hadDoor = phase === 'door';
    stop();
    phase = 'ready';
    if (hadDoor) focusAfter = true;
    release();
    document.body.classList.remove('mc-door-arrival','mc-hero-assembling');
    document.body.classList.add('mc-hero-resting');
    if (replay) replay.hidden = !motionAllowed();
  };
  const reveal = () => {
    stop();
    phase = 'assembling';
    progress = target = 1;
    paint();
    release();
    document.body.classList.add('mc-door-arrival','mc-hero-assembling');
    document.body.classList.remove('mc-hero-resting');
    if (replay) replay.hidden = true;
    heroTimer = setTimeout(() => {
      phase = 'ready';
      document.body.classList.remove('mc-door-arrival','mc-hero-assembling');
      document.body.classList.add('mc-hero-resting');
      if (replay) replay.hidden = !motionAllowed();
    }, 2480);
  };
  const animate = () => {
    frame = 0;
    if (phase !== 'door') return;
    if (!motionAllowed()) { finishImmediately(); return; }
    const gap = target - progress;
    progress = Math.abs(gap) < .004 ? target : progress + gap * .16;
    paint();
    if (progress === 1) { reveal(); return; }
    if (progress !== target) frame = requestAnimationFrame(animate);
  };
  const advance = amount => {
    if (phase !== 'door') return;
    target = clamp(target + amount);
    if (!frame) frame = requestAnimationFrame(animate);
  };
  const showDoor = () => {
    if (!motionAllowed()) { finishImmediately(); return; }
    stop();
    phase = 'door';
    focusAfter = true;
    progress = target = 0;
    paint();
    document.body.classList.remove('mc-hero-assembling','mc-hero-resting','mc-door-arrival');
    document.body.classList.add('mc-door-active');
    door.hidden = false;
    world.inert = true;
    if (skipLink) skipLink.inert = true;
    if (replay) replay.hidden = true;
    window.scrollTo(0,0);
    enter.focus({preventScroll:true});
  };
  if (door && enter && skip && world) {
    door.addEventListener('wheel', event => {
      if (phase !== 'door' || event.ctrlKey) return;
      event.preventDefault();
      const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? innerHeight : 1);
      advance(pixels / Math.max(360, innerHeight * .65));
    }, {passive:false});
    door.addEventListener('touchstart', event => {
      touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
    }, {passive:true});
    door.addEventListener('touchmove', event => {
      if (phase !== 'door' || touchY === null || event.touches.length !== 1) return;
      const y = event.touches[0].clientY;
      const delta = touchY - y;
      if (Math.abs(delta) > 1) {
        event.preventDefault();
        advance(delta / Math.max(180, innerHeight * .38));
        touchY = y;
      }
    }, {passive:false});
    ['touchend','touchcancel'].forEach(name => door.addEventListener(name, () => {touchY = null;}));
    enter.addEventListener('click', () => advance(1));
    skip.addEventListener('click', finishImmediately);
    door.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); finishImmediately(); }
      else if (['ArrowDown','PageDown','End','ArrowUp','PageUp','Home'].includes(event.key)) {
        event.preventDefault();
        const step = {ArrowDown:.2,PageDown:.6,End:1,ArrowUp:-.2,PageUp:-.6,Home:-1}[event.key];
        advance(step);
      } else if (event.key === 'Tab') {
        event.preventDefault();
        (document.activeElement === enter ? skip : enter).focus();
      }
    });
    replay?.addEventListener('click', showDoor);
    [reduce,contrast,forced].forEach(pref => pref.addEventListener?.('change', () => {
      if (!motionAllowed() && phase !== 'ready') finishImmediately();
      else if (phase === 'ready' && replay) replay.hidden = !motionAllowed();
    }));
    if (motionAllowed() && !seen && !location.hash) showDoor();
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

  // Suspend the expensive decorative hero motion while visitors read the
  // lower sections. One observer; no scroll events, polling or layout writes.
  const heroForMotion = document.querySelector('.mc-world-hero');
  if (heroForMotion && 'IntersectionObserver' in window) {
    const heroVisibility = new IntersectionObserver(([entry]) => {
      document.body.classList.toggle('mc-hero-out-of-view', !entry.isIntersecting);
    },{threshold:0.01});
    heroVisibility.observe(heroForMotion);
  }

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
