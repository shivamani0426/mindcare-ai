/* Caregiver Dashboard 2.0 — accessible, local filtering only.
   No patient details are transmitted by the filter or stored in the browser. */
(() => {
  'use strict';
  const grid = document.querySelector('.caregiver-patient-grid');
  if (!grid) return;
  const search = document.getElementById('caregiver-patient-search');
  const filters = [...document.querySelectorAll('[data-care-filter]')];
  const cards = [...grid.querySelectorAll('[data-care-patient]')];
  const status = document.getElementById('caregiver-filter-status');
  const empty = document.getElementById('caregiver-no-results');
  let selected = 'all';

  function update() {
    const query = (search?.value || '').toLocaleLowerCase().trim();
    let count = 0;
    cards.forEach(card => {
      const matchingName = (card.dataset.patientName || '').includes(query);
      const matchingStatus = selected === 'all'
        || (selected === 'support' && card.dataset.careSupport === '1')
        || (selected === 'overdue' && card.dataset.careOverdue === '1')
        || (selected === 'unchecked' && card.dataset.careUnchecked === '1');
      card.hidden = !(matchingName && matchingStatus);
      if (!card.hidden) count++;
    });
    filters.forEach(button => {
      const active = button.dataset.careFilter === selected;
      button.setAttribute('aria-pressed', String(active));
    });
    if (status) status.textContent = 'Showing ' + count + ' of ' + cards.length + ' people';
    if (empty) empty.hidden = count !== 0;
  }

  search?.addEventListener('input', update);
  filters.forEach(button => button.addEventListener('click', () => {
    selected = button.dataset.careFilter || 'all';
    update();
  }));
  update();
})();
