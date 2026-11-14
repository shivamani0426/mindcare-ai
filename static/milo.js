/**
 * Milo — tiny on-device animated patient companion.
 *
 * Does not call an AI service, record interactions, monitor behaviour,
 * alter care data, or contact a caregiver. It gently explores the edges of
 * the viewport and provides opt-in, rule-based page guidance.
 */
(() => {
  'use strict';
  const roamer = document.getElementById('milo-roamer');
  const mascot = document.getElementById('milo-character');
  const panel = document.getElementById('milo-panel');
  const nav = document.getElementById('milo-nav-toggle');
  if (!roamer || !mascot || !panel || !nav || document.body.dataset.patient !== '1') return;

  const closeButton = document.getElementById('milo-close');
  const hideButton = document.getElementById('milo-hide');
  const motionButton = document.getElementById('milo-motion-toggle');
  const explainButton = document.getElementById('milo-explain');
  const speakButton = document.getElementById('milo-speak');
  const tip = document.getElementById('milo-tip');
  const status = document.getElementById('milo-movement-status');
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const saveKey = 'mindcare-milo-hidden-v1';
  const motionKey = 'mindcare-milo-paused-v1';
  const gamePage = roamer.dataset.miloPage === 'play_game';
  const BOX_W = 94;
  const BOX_H = 126;
  let x = 0;
  let y = 0;
  let timer = null;
  let walking = false;
  let panelOpen = false;
  let hidden = false;
  let paused = false;
  let hovering = false;

  function readPreference(key) {
    try { return window.localStorage.getItem(key) === '1'; } catch (_) { return false; }
  }
  function savePreference(key, enabled) {
    try { window.localStorage.setItem(key, enabled ? '1' : '0'); } catch (_) { /* session-only */ }
  }
  function reduced() {
    return motionPreference.matches || document.body.classList.contains('reduced-motion');
  }
  function canMove() {
    return !hidden && !paused && !hovering && !panelOpen && !gamePage && !reduced() &&
      !roamer.contains(document.activeElement) &&
      !document.hidden && !document.querySelector('dialog[open], [aria-modal="true"]:not([hidden])') &&
      !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  }
  function bounds() {
    return {
      maxX: Math.max(10, window.innerWidth - BOX_W - 12),
      maxY: Math.max(75, window.innerHeight - BOX_H - 10)
    };
  }
  function clamp(value, lower, upper) {
    return Math.max(lower, Math.min(upper, value));
  }
  function stopTimer() {
    window.clearTimeout(timer);
    timer = null;
    roamer.classList.remove('milo-walking');
    walking = false;
  }
  function place(nx, ny, seconds = 0) {
    const limit = bounds();
    x = clamp(Math.round(nx), 10, limit.maxX);
    y = clamp(Math.round(ny), 75, limit.maxY);
    roamer.style.setProperty('--milo-travel-time', seconds + 's');
    roamer.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)';
    walking = seconds > 0;
    roamer.classList.toggle('milo-walking', walking);
    roamer.dataset.miloState = walking ? 'walking' : 'resting';
  }

  function importantTargets() {
    const selector = 'main a, main button, main input, main select, main textarea, ' +
      'header a, header button, [role="button"], .incoming-call';
    return [...document.querySelectorAll(selector)]
      .filter(el => !roamer.contains(el) && !panel.contains(el) &&
        !el.hidden && el.getClientRects().length > 0)
      .map(el => el.getBoundingClientRect())
      .filter(r => r.width > 0 && r.height > 0 && r.bottom > 0 &&
        r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth);
  }
  function overlapArea(a,b) {
    return Math.max(0, Math.min(a.right,b.right)-Math.max(a.left,b.left)) *
      Math.max(0, Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
  }

  // Candidate locations trace the edges and lower third of the page.
  // Prefer clear areas; never intentionally stop on top of a form control.
  function chooseTarget() {
    const {maxX,maxY} = bounds();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const candidates = [
      [12,maxY], [maxX,maxY],
      [12,clamp(vh*.59,75,maxY)], [maxX,clamp(vh*.59,75,maxY)],
      [12,clamp(vh*.35,75,maxY)], [maxX,clamp(vh*.35,75,maxY)]
    ];
    if (vw > 760) {
      candidates.push([Math.round(maxX*.28),maxY],
                      [Math.round(maxX*.53),maxY],
                      [Math.round(maxX*.75),maxY]);
    }
    // A patient reading a text field should never have Milo walking into it.
    const targets = importantTargets();
    const scored = candidates.map(([cx,cy]) => {
      const rect = {left:cx-10,top:cy-6,right:cx+BOX_W+10,bottom:cy+BOX_H+5};
      const collisions = targets.reduce((sum,target) => sum + overlapArea(rect,target),0);
      const distance = Math.hypot(cx-x,cy-y);
      return {cx,cy,collisions,distance};
    }).filter(p => p.distance > (vw < 500 ? 55 : 110));
    const safe = scored.filter(p => p.collisions < 1);
    if (!safe.length) return null; // Rest where we are rather than obscure a control.
    // Prefer varied routes without abrupt movements.
    safe.sort((a,b)=>b.distance-a.distance);
    return safe[Math.floor(Math.random()*Math.min(4,safe.length))];
  }
  function planNext(delay = 6500) {
    stopTimer();
    if (!canMove()) return;
    timer = window.setTimeout(() => {
      if (!canMove()) {stopTimer(); return;}
      const target = chooseTarget();
      if (!target) {planNext(4200);return;}
      // Slow steps (70–115 px/s), then a clear resting pause.
      const distance = Math.hypot(target.cx-x,target.cy-y);
      const seconds = clamp(distance/100,3.2,7.7);
      roamer.classList.toggle('milo-facing-left',target.cx < x);
      place(target.cx,target.cy,seconds);
      timer = window.setTimeout(() => {
        roamer.classList.remove('milo-walking');
        walking = false;
        roamer.dataset.miloState = 'resting';
        planNext(5500 + Math.random()*4200);
      }, seconds*1000 + 100);
    }, delay);
  }
  function dock() {
    stopTimer();
    const {maxX,maxY} = bounds();
    place(maxX,maxY,0);
  }
  function syncMotionControl() {
    motionButton.textContent = (paused || reduced() || gamePage) ?
      '▶ ' + motionButton.dataset.resumeLabel :
      '⏸ ' + motionButton.dataset.pauseLabel;
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.disabled = reduced() || gamePage;
    motionButton.title = reduced() ? 'Movement is disabled by your accessibility preferences.' :
      gamePage ? 'Milo rests while you play.' : '';
  }
  function setVisible(visible) {
    hidden = !visible;
    roamer.hidden = !visible;
    if (!visible) closePanel(false);
    nav.setAttribute('aria-pressed', String(visible));
    const label = visible ? nav.dataset.hideLabel : nav.dataset.showLabel;
    nav.setAttribute('aria-label',label);
    nav.title = label;
    savePreference(saveKey,!visible);
    if (visible) {dock();planNext(4300);} else stopTimer();
  }
  function openPanel() {
    if (hidden) setVisible(true);
    stopTimer();
    panelOpen = true;
    dock();
    panel.hidden = false;
    mascot.setAttribute('aria-expanded','true');
    closeButton.focus({preventScroll:true});
  }
  function closePanel(returnFocus = true) {
    panelOpen = false;
    panel.hidden = true;
    mascot.setAttribute('aria-expanded','false');
    if (returnFocus && !hidden) mascot.focus({preventScroll:true});
    if (!hidden) planNext();
  }

  // If Milo wanders under a mouse or receives keyboard focus, stop him in
  // place so tapping remains easy for patients with tremors or slow movement.
  roamer.addEventListener('pointerenter', () => {
    hovering = true;
    const rect = roamer.getBoundingClientRect();
    stopTimer();
    place(rect.left,rect.top,0);
  });
  roamer.addEventListener('pointerleave', () => {
    hovering = false;
    if (canMove()) planNext(6000);
  });
  roamer.addEventListener('focusin', () => {
    const rect = roamer.getBoundingClientRect();
    stopTimer();
    place(rect.left,rect.top,0);
  });
  roamer.addEventListener('focusout', () => {
    if (canMove()) planNext(6000);
  });
  nav.addEventListener('click', () => setVisible(hidden));
  mascot.addEventListener('click', () => panelOpen ? closePanel() : openPanel());
  closeButton.addEventListener('click', () => closePanel());
  hideButton.addEventListener('click', () => {
    setVisible(false);
    nav.focus({preventScroll:true});
  });
  motionButton.addEventListener('click', () => {
    if (reduced() || gamePage) return;
    paused = !paused;
    savePreference(motionKey,paused);
    syncMotionControl();
    if (paused) {
      // Stop at the closest safe rest location instead of covering content.
      stopTimer();
      dock();
      if (status) status.textContent = motionButton.dataset.resumeLabel;
    } else if (status) status.textContent = motionButton.dataset.pauseLabel;
  });
  explainButton.addEventListener('click', () => {
    tip.hidden = false;
    speakButton.hidden = false;
  });
  speakButton.addEventListener('click', () => {
    const text = tip.textContent.trim();
    // Speak only on a deliberate click; never play audio while wandering.
    if (window.MindCareVoice?.speak) {
      window.MindCareVoice.speak(text);
    } else if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = ({hi:'hi-IN',kn:'kn-IN',en:'en-IN'})[roamer.dataset.miloLanguage] || 'en-IN';
      utterance.rate = .85;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } else if (status) {
      status.textContent = speakButton.dataset.unavailableLabel || 'Voice guidance unavailable.';
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panelOpen) closePanel();
  });
  document.addEventListener('pointerdown', event => {
    if (panelOpen && !panel.contains(event.target) && !mascot.contains(event.target))
      closePanel(false);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopTimer();
    else if (canMove()) planNext(4500);
  });
  document.addEventListener('focusin', event => {
    if (['INPUT','TEXTAREA','SELECT'].includes(event.target?.tagName)) stopTimer();
    else if (canMove() && timer === null && !walking) planNext(5500);
  });
  window.addEventListener('resize', () => {
    if (hidden) return;
    const {maxX,maxY} = bounds();
    // On resize, return to a predictable corner instead of clipping.
    if (x > maxX || y > maxY || panelOpen) dock();
    if (canMove()) planNext(5000);
  });
  motionPreference.addEventListener?.('change', () => {
    syncMotionControl();
    if (reduced()) dock();
    else if (canMove()) planNext();
  });
  paused = readPreference(motionKey);
  const initiallyHidden = readPreference(saveKey);
  syncMotionControl();
  dock();
  setVisible(!initiallyHidden);
})();
