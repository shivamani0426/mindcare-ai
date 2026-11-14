/* MindCare dashboard bounce stacks — native HTML + CSS, no React dependency.
   Cards remain in document flow, retaining original links, forms and permissions.
   A clearly labelled button fans out each stack; no hidden card is actionable.
   Motion is disabled for reduced-motion and narrow screens; Simple View can animate. */
(() => {
  'use strict';
  const groups = [...document.querySelectorAll('[data-bounce-stack]')];
  if (!groups.length) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const wide = window.matchMedia('(min-width: 900px)');
  const enabled = () => wide.matches && !reduced.matches &&
    !document.body.classList.contains('reduced-motion') &&
    !document.body.classList.contains('high-contrast');

  groups.forEach(group => {
    const cards = [...group.children];
    if (cards.length < 2) return;
    cards.forEach(card => card.setAttribute('data-bounce-card', ''));
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dashboard-stack-open';
    button.textContent = '✦ Touch to spread these cards';
    button.setAttribute('aria-label', 'Spread dashboard cards into their normal positions');
    group.appendChild(button);

    const spread = () => {
      if (group.dataset.stackState !== 'stacked') return;
      group.dataset.stackState = 'expanded';
      cards.forEach(card => {
        card.inert = false;
        card.removeAttribute('aria-hidden');
      });
      button.hidden = true;
    };

    const stack = () => {
      if (!enabled() || group.dataset.stackState === 'expanded') {
        group.dataset.stackState = 'expanded';
        cards.forEach(card => { card.inert = false; card.removeAttribute('aria-hidden'); });
        button.hidden = true;
        return;
      }
      const rect = group.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      cards.forEach((card, index) => {
        const box = card.getBoundingClientRect();
        card.style.setProperty('--bounce-x', (cx - box.left - box.width / 2).toFixed(2) + 'px');
        card.style.setProperty('--bounce-y', (cy - box.top - box.height / 2).toFixed(2) + 'px');
        card.style.setProperty('--bounce-tilt', ((index - (cards.length - 1) / 2) * 3.2).toFixed(2) + 'deg');
        card.style.setProperty('--bounce-delay', (index * 75) + 'ms');
        card.style.zIndex = String(index + 1);
        card.inert = true;
        card.setAttribute('aria-hidden', 'true');
      });
      group.dataset.stackState = 'stacked';
      button.hidden = false;
    };

    button.addEventListener('click', spread);
    group.addEventListener('pointerdown', event => {
      if (group.dataset.stackState === 'stacked' &&
          event.target.closest('[data-bounce-card]')) spread();
    });
    group.addEventListener('focusin', event => {
      if (group.dataset.stackState === 'stacked' && event.target !== button) spread();
    });
    // First paint uses regular, accessible HTML. Only then apply the stack.
    window.requestAnimationFrame(() => window.requestAnimationFrame(stack));
    const onChange = () => {
      if (!enabled()) spread();
    };
    wide.addEventListener('change', onChange);
    reduced.addEventListener('change', onChange);
  });
})();
