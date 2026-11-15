/* MindCare flight-to-stack entrance, then the existing bounce-card spread.
   Native HTML controls remain in document flow; they are inert while stacked
   and become usable after an explicit spread. Reduced motion stays static. */
(() => {
  'use strict';
  const groups = [...document.querySelectorAll('[data-bounce-stack]')];
  if (!groups.length) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const wide = window.matchMedia('(min-width: 900px)');
  const enabled = () => wide.matches && !reduced.matches &&
    !document.body.classList.contains('reduced-motion') &&
    !document.body.classList.contains('high-contrast');

  groups.forEach((group, groupIndex) => {
    const cards = [...group.children];
    if (cards.length < 2) return;
    cards.forEach(card => card.setAttribute('data-bounce-card', ''));
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dashboard-stack-open';
    button.textContent = '✦ Touch to spread these cards';
    button.setAttribute('aria-label', 'Spread dashboard cards into their normal positions');
    button.hidden = true;
    group.appendChild(button);
    let flights = [];

    const clearFlights = () => {
      flights.forEach(animation => animation.cancel());
      flights = [];
    };
    const spread = () => {
      if (group.dataset.stackState !== 'stacked' &&
          group.dataset.stackState !== 'arriving') return;
      // Do not leave controls locked if the user changes accessibility settings
      // or opens the group while an entrance animation is still running.
      group.dataset.stackState = 'expanded';
      clearFlights();
      cards.forEach(card => {
        card.inert = false;
        card.removeAttribute('aria-hidden');
      });
      button.hidden = true;
    };

    const stack = () => {
      if (!enabled() || group.dataset.stackState === 'expanded') {
        group.dataset.stackState = 'expanded';
        cards.forEach(card => {card.inert = false;card.removeAttribute('aria-hidden');});
        button.hidden = true;
        return;
      }

      const rect = group.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const viewportW = window.innerWidth;
      const viewportH = window.innerHeight;
      const entries = cards.map((card,index) => {
        const box = card.getBoundingClientRect();
        const bx = box.left + box.width / 2;
        const by = box.top + box.height / 2;
        const tx = cx - bx;
        const ty = cy - by;
        const tilt = (index - (cards.length - 1) / 2) * 3.2;
        card.style.setProperty('--bounce-x', tx.toFixed(2) + 'px');
        card.style.setProperty('--bounce-y', ty.toFixed(2) + 'px');
        card.style.setProperty('--bounce-tilt', tilt.toFixed(2) + 'deg');
        card.style.setProperty('--bounce-delay', (index * 75) + 'ms');
        card.style.zIndex = String(index + 1);
        card.inert = true;
        card.setAttribute('aria-hidden', 'true');
        // A different window edge for each consecutive card; start outside
        // the viewport and land at the original stack center (not at the camera).
        const edge = (index + groupIndex) % 4;
        const startX = edge === 0 ? -box.width - 40 :
          edge === 1 ? viewportW + box.width + 40 :
          edge === 2 ? viewportW * .2 : viewportW * .8;
        const startY = edge === 2 ? -box.height - 40 :
          edge === 3 ? viewportH + box.height + 40 :
          Math.max(30,Math.min(viewportH - 30,cy));
        return {card,tx,ty,tilt,fromX:startX-bx,fromY:startY-by,index};
      });
      group.dataset.stackState = 'arriving';
      button.hidden = true;

      if (!Element.prototype.animate) {
        group.dataset.stackState = 'stacked';
        button.hidden = false;
        return;
      }

      // One card at a time, across the window. CSS supplies the stable final
      // stack position; Web Animations supplies the temporary flight path.
      flights = entries.map(({card,tx,ty,tilt,fromX,fromY,index}) => {
        const delay = groupIndex * 130 + index * 165;
        return card.animate([
          {transform:`translate3d(${fromX}px,${fromY}px,0) rotate(${tilt * 2}deg) scale(.7)`,opacity:0,filter:'blur(8px)',offset:0},
          {transform:`translate3d(${tx * .22 + fromX * .78}px,${ty * .22 + fromY * .78}px,0) rotate(${tilt * 1.6}deg) scale(.85)`,opacity:.82,filter:'blur(2px)',offset:.54},
          {transform:`translate3d(${tx}px,${ty}px,0) rotate(${tilt}deg) scale(.82)`,opacity:1,filter:'blur(0)',offset:1}
        ], {duration:920,delay,easing:'cubic-bezier(.2,.75,.25,1)',fill:'both'});
      });
      Promise.allSettled(flights.map(animation => animation.finished)).then(() => {
        if (group.dataset.stackState !== 'arriving') return;
        // Set stable stack state before canceling animations to avoid a jump.
        group.dataset.stackState = 'stacked';
        clearFlights();
        button.hidden = false;
      });
    };

    button.addEventListener('click',spread);
    group.addEventListener('pointerdown',event => {
      if (group.dataset.stackState === 'stacked' &&
          event.target.closest('[data-bounce-card]')) spread();
    });
    group.addEventListener('focusin',event => {
      if (group.dataset.stackState === 'stacked' && event.target !== button) spread();
    });

    // Keep first paint and no-JS fallback as normal accessible markup.
    window.requestAnimationFrame(() => window.requestAnimationFrame(stack));
    const onChange = () => {
      if (!enabled()) spread();
    };
    wide.addEventListener('change',onChange);
    reduced.addEventListener('change',onChange);
  });
})();
