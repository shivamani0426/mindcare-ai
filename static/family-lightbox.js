(() => {
  'use strict';
  const items = [...document.querySelectorAll('[data-family-photo-open]')]
    .filter(button => button.dataset.fullSrc);
  if (!items.length) return;

  // This is a same-origin, authenticated photo viewer. No third-party media service is used.
  const viewer = document.createElement('dialog');
  viewer.className = 'family-photo-viewer';
  viewer.setAttribute('aria-label', 'Full-screen family photo viewer');
  viewer.innerHTML = `
    <div class="family-viewer-bar">
      <div class="family-viewer-brand" aria-hidden="true">✦ MindCare family photos</div>
      <div class="family-viewer-actions">
        <button type="button" class="family-viewer-fullscreen" aria-label="Enter device full screen">⛶ Full screen</button>
        <button type="button" class="family-viewer-close" aria-label="Close full-screen photo">✕ Close</button>
      </div>
    </div>
    <div class="family-viewer-stage">
      <button type="button" class="family-viewer-previous" aria-label="Previous family photo">‹</button>
      <img class="family-viewer-image" alt="" draggable="false">
      <button type="button" class="family-viewer-next" aria-label="Next family photo">›</button>
    </div>
    <div class="family-viewer-footer" aria-live="polite">
      <span class="family-viewer-caption"></span>
      <span class="family-viewer-count"></span>
    </div>`;
  document.body.appendChild(viewer);
  const image = viewer.querySelector('.family-viewer-image');
  const caption = viewer.querySelector('.family-viewer-caption');
  const count = viewer.querySelector('.family-viewer-count');
  const closeButton = viewer.querySelector('.family-viewer-close');
  const fullscreenButton = viewer.querySelector('.family-viewer-fullscreen');
  const previous = viewer.querySelector('.family-viewer-previous');
  const next = viewer.querySelector('.family-viewer-next');
  let current = 0;
  let opener = null;
  let touchStartX = 0;
  let touchStartY = 0;

  function show(index) {
    current = (index + items.length) % items.length;
    const item = items[current];
    const label = item.dataset.photoCaption || item.getAttribute('aria-label') || 'Family photo';
    image.alt = label;
    image.src = item.dataset.fullSrc;
    caption.textContent = label;
    count.textContent = `${current + 1} of ${items.length}`;
    previous.disabled = items.length === 1;
    next.disabled = items.length === 1;
    viewer.classList.remove('family-photo-load-error');
  }

  function closeViewer() {
    if (document.fullscreenElement === viewer && document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    }
    if (typeof viewer.close === 'function' && viewer.open) viewer.close();
    else viewer.removeAttribute('open');
  }

  items.forEach((item, index) => {
    item.addEventListener('click', () => {
      opener = item;
      show(index);
      if (typeof viewer.showModal === 'function') viewer.showModal();
      else viewer.setAttribute('open', '');
      document.body.classList.add('family-viewer-active');
      closeButton.focus();
    });
  });
  image.addEventListener('error', () => {
    viewer.classList.add('family-photo-load-error');
    caption.textContent = 'This photo could not be displayed. Please try again.';
  });
  closeButton.addEventListener('click', closeViewer);
  previous.addEventListener('click', () => show(current - 1));
  next.addEventListener('click', () => show(current + 1));
  viewer.addEventListener('click', event => {
    // Tapping the dark backdrop outside the actual photograph also closes the viewer.
    if (event.target === viewer) closeViewer();
  });
  viewer.addEventListener('close', () => {
    document.body.classList.remove('family-viewer-active');
    image.removeAttribute('src');
    opener?.focus();
  });
  document.addEventListener('keydown', event => {
    if (!viewer.open) return;
    if (event.key === 'ArrowLeft' && items.length > 1) { event.preventDefault(); show(current - 1); }
    if (event.key === 'ArrowRight' && items.length > 1) { event.preventDefault(); show(current + 1); }
    if (event.key === 'Escape' && typeof viewer.close !== 'function') closeViewer();
  });
  viewer.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) return;
    touchStartX = event.touches[0].clientX;
    touchStartY = event.touches[0].clientY;
  }, { passive: true });
  viewer.addEventListener('touchend', event => {
    if (event.changedTouches.length !== 1 || items.length <= 1) return;
    const dx = event.changedTouches[0].clientX - touchStartX;
    const dy = event.changedTouches[0].clientY - touchStartY;
    if (Math.abs(dx) > 65 && Math.abs(dx) > Math.abs(dy) * 1.5) show(current + (dx < 0 ? 1 : -1));
  }, { passive: true });

  fullscreenButton.addEventListener('click', async () => {
    if (typeof viewer.requestFullscreen !== 'function') {
      fullscreenButton.hidden = true; // The viewport-sized lightbox is still available.
      return;
    }
    try {
      if (document.fullscreenElement === viewer) await document.exitFullscreen();
      else await viewer.requestFullscreen();
    } catch (_) {
      // Some browsers, especially iOS, restrict the Fullscreen API.
      fullscreenButton.hidden = true;
    }
  });
  if (typeof viewer.requestFullscreen !== 'function') fullscreenButton.hidden = true;
  document.addEventListener('fullscreenchange', () => {
    const isFull = document.fullscreenElement === viewer;
    fullscreenButton.textContent = isFull ? '⤢ Exit full screen' : '⛶ Full screen';
    fullscreenButton.setAttribute('aria-label', isFull ? 'Exit device full screen' : 'Enter device full screen');
  });
})();
