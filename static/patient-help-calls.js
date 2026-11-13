(() => {
  'use strict';
  const dialog = document.getElementById('phone-call-options');
  if (!dialog) return;
  const heading = dialog.querySelector('#phone-call-heading');
  const description = dialog.querySelector('#phone-call-description');
  const displayedNumber = dialog.querySelector('#phone-dialog-number');
  const dialLink = dialog.querySelector('#phone-dialog-dial');
  const notice = dialog.querySelector('#phone-dialog-notice');
  const copyStatus = dialog.querySelector('#phone-copy-status');
  const copyFromDialog = dialog.querySelector('#phone-dialog-copy');
  const isPhoneLike = navigator.userAgentData?.mobile === true ||
    /Android|iPhone|iPod|Mobile/i.test(navigator.userAgent || '') ||
    (/Macintosh/i.test(navigator.userAgent || '') && navigator.maxTouchPoints > 1);
  const validNumber = number => /^\+?[0-9]{2,15}$/.test(number);
  let selectedNumber = '';
  let lastOpener = null;

  const status = (message, near = null) => {
    if (near) {
      let region = near.parentElement?.querySelector('[data-phone-copy-status]');
      if (!region) {
        region = document.createElement('span');
        region.dataset.phoneCopyStatus = '';
        region.setAttribute('role', 'status');
        region.setAttribute('aria-live', 'polite');
        region.className = 'phone-inline-status';
        near.parentElement?.appendChild(region);
      }
      if (region) region.textContent = message;
      return;
    }
    copyStatus.textContent = message;
  };

  async function copyNumber(number, button) {
    if (!validNumber(number)) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API not available');
      await navigator.clipboard.writeText(number);
      status('Copied ' + number + '. Dial it using your phone.', button);
    } catch (_) {
      // Older browsers and restricted contexts might block Clipboard API.
      // Never silently claim that copying worked.
      status('Copy this number manually: ' + number, button);
      if (!button) {
        displayedNumber.focus?.();
        const selection = window.getSelection?.();
        const range = document.createRange?.();
        if (selection && range) {
          range.selectNodeContents(displayedNumber);
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
    }
  }

  function openOptions(anchor) {
    const number = anchor.dataset.phoneNumber || '';
    if (!validNumber(number)) return;
    const emergency = anchor.dataset.phoneEmergency === '1';
    const label = anchor.dataset.phoneLabel || 'Trusted contact';
    lastOpener = anchor;
    selectedNumber = number;
    heading.textContent = emergency ? 'Call emergency services' : 'Call ' + label;
    description.textContent = 'This computer may not have a phone dialer. The website itself cannot make telephone calls.';
    displayedNumber.textContent = number;
    displayedNumber.setAttribute('tabindex', '0');
    dialLink.href = 'tel:' + number;
    notice.textContent = emergency
      ? 'If this is an emergency in India, use a phone to dial 112 now. The website does not send an alert or your location.'
      : 'Use a phone, a connected calling app, or copy the number to dial from another device.';
    copyStatus.textContent = '';
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  function closeOptions() {
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
    lastOpener?.focus();
  }

  document.querySelectorAll('[data-phone-dial]').forEach(anchor => {
    anchor.addEventListener('click', event => {
      // On phones leave the native tel: link untouched: one tap opens the dialer.
      // On computers, explain why a tel: link might otherwise do nothing.
      if (isPhoneLike) return;
      event.preventDefault();
      openOptions(anchor);
    });
  });
  document.querySelectorAll('[data-phone-copy]').forEach(button => {
    button.addEventListener('click', () => copyNumber(button.dataset.phoneNumber || '', button));
  });
  copyFromDialog?.addEventListener('click', () => copyNumber(selectedNumber));
  dialog.querySelectorAll('[data-phone-dialog-close]').forEach(button => button.addEventListener('click', closeOptions));
  dialog.addEventListener('click', event => { if (event.target === dialog) closeOptions(); });
  dialog.addEventListener('close', () => lastOpener?.focus());
})();
