/* MindCare curved gallery: same-origin patient-approved photos only.
   Native horizontal scrolling + keyboard + optional pointer drag, no dependencies. */
(() => {
  'use strict';
  const gallery = document.querySelector('.family-circular-gallery');
  const wrap = document.querySelector('.family-gallery-wrap');
  if (!gallery || !wrap) return;
  const cards = [...gallery.querySelectorAll('.family-card')];
  const prev = wrap.querySelector('.family-gallery-previous');
  const next = wrap.querySelector('.family-gallery-next');
  if (!cards.length) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const motionOff = () => reduced.matches ||
    document.body.classList.contains('reduced-motion') ||
    document.body.classList.contains('high-contrast');
  let frame = null;
  let drag = null;
  let lastDragTime = 0;

  const currentIndex = () => {
    const center = gallery.getBoundingClientRect().left + gallery.clientWidth / 2;
    let selected = 0, min = Infinity;
    cards.forEach((card,index) => {
      const rect = card.getBoundingClientRect();
      const delta = Math.abs(rect.left + rect.width / 2 - center);
      if (delta < min) { min = delta; selected = index; }
    });
    return selected;
  };
  const update = () => {
    frame = null;
    const rect = gallery.getBoundingClientRect();
    const center = rect.left + rect.width / 2;
    const radius = Math.max(160,Math.min(390,rect.width*.45));
    cards.forEach(card => {
      const box = card.getBoundingClientRect();
      // Offset does not depend on transforms for scroll position accuracy.
      const untransformedCenter = rect.left + card.offsetLeft - gallery.offsetLeft
        - gallery.scrollLeft + card.offsetWidth / 2;
      const dist = Math.max(-1.5,Math.min(1.5,(untransformedCenter-center)/radius));
      if (motionOff()) {
        card.style.removeProperty('--gallery-angle');
        card.style.removeProperty('--gallery-lift');
        card.style.removeProperty('--gallery-scale');
        card.style.removeProperty('--gallery-opacity');
        return;
      }
      card.style.setProperty('--gallery-angle',(-dist*26).toFixed(2)+'deg');
      card.style.setProperty('--gallery-lift',(Math.abs(dist)*24).toFixed(1)+'px');
      card.style.setProperty('--gallery-scale',(1-Math.min(.18,Math.abs(dist)*.12)).toFixed(3));
      card.style.setProperty('--gallery-opacity',(1-Math.min(.4,Math.abs(dist)*.26)).toFixed(3));
    });
    const index = currentIndex();
    prev.disabled = cards.length < 2 || (index === 0 && gallery.scrollLeft < 8);
    next.disabled = cards.length < 2 || (index === cards.length-1 &&
      gallery.scrollLeft >= gallery.scrollWidth-gallery.clientWidth-8);
    gallery.setAttribute('aria-label',
      'Browse photos of loved ones, image '+(index+1)+' of '+cards.length);
  };
  const schedule = () => {
    if (frame === null) frame = window.requestAnimationFrame(update);
  };
  const moveTo = index => {
    const item = cards[Math.max(0,Math.min(cards.length-1,index))];
    const left = item.offsetLeft-gallery.offsetLeft - (gallery.clientWidth-item.offsetWidth)/2;
    gallery.scrollTo({left,behavior:motionOff()?'instant':'smooth'});
    schedule();
  };
  prev.addEventListener('click',()=>moveTo(currentIndex()-1));
  next.addEventListener('click',()=>moveTo(currentIndex()+1));
  gallery.addEventListener('keydown',event => {
    if (event.target !== gallery) return;
    if (event.key === 'ArrowRight') {event.preventDefault();moveTo(currentIndex()+1);}
    if (event.key === 'ArrowLeft') {event.preventDefault();moveTo(currentIndex()-1);}
    if (event.key === 'Home') {event.preventDefault();moveTo(0);}
    if (event.key === 'End') {event.preventDefault();moveTo(cards.length-1);}
  });
  gallery.addEventListener('scroll',schedule,{passive:true});
  window.addEventListener('resize',schedule,{passive:true});
  reduced.addEventListener?.('change',schedule);

  // Let the browser handle touch swiping. Provide mouse/pen drag on desktop.
  gallery.addEventListener('pointerdown',event => {
    if (event.pointerType === 'touch' || event.button !== 0 ||
        event.target.closest('input,textarea,select,.delete-link')) return;
    drag = {id:event.pointerId,x:event.clientX,left:gallery.scrollLeft,moved:false};
  });
  gallery.addEventListener('pointermove',event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX-drag.x;
    if (Math.abs(dx)>7) {
      drag.moved=true;
      gallery.scrollLeft=drag.left-dx;
      schedule();
    }
  });
  const finishDrag = event => {
    if (!drag || drag.id !== event.pointerId) return;
    if (drag.moved) lastDragTime=Date.now();
    drag=null;
  };
  gallery.addEventListener('pointerup',finishDrag);
  gallery.addEventListener('pointercancel',finishDrag);
  gallery.addEventListener('click',event => {
    if (Date.now()-lastDragTime<250 && event.target.closest('.family-photo-trigger')) {
      event.preventDefault();event.stopImmediatePropagation();
    }
  },true);
  // All original photo viewer actions remain native clickable buttons.
  schedule();
})();
