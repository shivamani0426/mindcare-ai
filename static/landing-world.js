(() => {
  'use strict';
  if (!document.body.classList.contains('mc-world-page')) return;

  // A single, optional tactile paper-to-website introduction per browser tab.
  // The full site stays visible if scripts fail, if motion is reduced, or when
  // arriving at a deep section anchor. No tracking or server-side persistence.
  const paperIntro = document.getElementById('mc-paper-intro');
  const paperTouch = document.getElementById('mc-paper-touch');
  const paperSkip = document.getElementById('mc-paper-skip');
  const world = document.querySelector('.mc-world-root');
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const introStorageKey = 'mindcare-paper-unfold-seen-v1';
  let introSeen = false;
  try { introSeen = window.sessionStorage.getItem(introStorageKey) === '1'; }
  catch (_) { /* Private browsing can deny storage. */ }
  const canPresent = paperIntro && paperTouch && paperSkip && world &&
    !motionPreference.matches && !introSeen && !window.location.hash;
  if (canPresent) {
    let alreadyRevealed = false;
    let finishTimer;
    const finish = () => {
      window.clearTimeout(finishTimer);
      paperIntro.hidden = true;
      world.inert = false;
      document.body.classList.remove('mc-paper-active', 'mc-paper-revealing');
      alreadyRevealed = true;
    };
    const reveal = (animate = true) => {
      if (alreadyRevealed) return;
      alreadyRevealed = true;
      try { window.sessionStorage.setItem(introStorageKey, '1'); }
      catch (_) { /* Effect still opens. */ }
      world.inert = false;
      if (!animate || motionPreference.matches) {
        finish();
        return;
      }
      document.body.classList.add('mc-paper-revealing');
      // Allow separately arriving heading, navigation and actions to settle.
      finishTimer = window.setTimeout(finish, 2150);
    };
    world.inert = true;
    paperIntro.hidden = false;
    document.body.classList.add('mc-paper-active');
    paperTouch.addEventListener('click', () => reveal());
    paperSkip.addEventListener('click', () => reveal(false));
    paperIntro.addEventListener('keydown', event => {
      if (event.key === 'Escape') reveal(false);
    });
    motionPreference.addEventListener?.('change', () => {
      if (motionPreference.matches) reveal(false);
    });
    // Focus the paper action so keyboard visitors can instantly open the site.
    paperTouch.focus({preventScroll:true});
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
