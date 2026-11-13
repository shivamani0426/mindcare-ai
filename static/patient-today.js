/* Patient orientation display: India time in the patient's selected language. */
(() => {
  'use strict';
  const panel = document.querySelector('[data-patient-today]');
  if (!panel) return;
  const dateEl = panel.querySelector('[data-ist-date]');
  const timeEl = panel.querySelector('[data-ist-time]');
  const lang = {en:'en-IN',hi:'hi-IN',kn:'kn-IN'}[panel.dataset.language] || 'en-IN';
  function updateClock() {
    const now = new Date();
    try {
      dateEl.textContent = new Intl.DateTimeFormat(lang, {timeZone:'Asia/Kolkata',weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(now);
      timeEl.textContent = new Intl.DateTimeFormat(lang, {timeZone:'Asia/Kolkata',hour:'numeric',minute:'2-digit',hour12:true}).format(now) + ' IST';
    } catch (_) { timeEl.textContent = now.toLocaleTimeString(); }
  }
  updateClock();
  setInterval(updateClock, 60000);
})();
