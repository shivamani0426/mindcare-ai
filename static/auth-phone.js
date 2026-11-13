/* Firebase phone number OTP: only loaded when both client and server config exist.
   The server independently verifies Firebase ID-token signature and phone provider. */
import {initializeApp} from 'https://www.gstatic.com/firebasejs/13.3.0/firebase-app.js';
import {
  getAuth, RecaptchaVerifier, signInWithPhoneNumber,
  setPersistence, inMemoryPersistence, signOut
} from 'https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js';

const flow = document.querySelector('[data-phone-auth]');
if (flow) {
  const config = JSON.parse(flow.dataset.firebaseConfig || 'null');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const sendForm = flow.querySelector('#phone-send-form');
  const verifyForm = flow.querySelector('#phone-verify-form');
  const phoneField = flow.querySelector('#auth-phone-number');
  const codeField = flow.querySelector('#auth-sms-code');
  const sendButton = flow.querySelector('#phone-send-button');
  const status = flow.querySelector('#auth-phone-status');
  const resetButton = flow.querySelector('#phone-try-again');
  const show = message => {if (status) status.textContent = message;};
  let confirmation = null;
  let recaptcha = null;
  let auth = null;
  let busy = false;
  let lastAttempt = 0;

  const feedback = error => {
    const code = error?.code || '';
    if (code === 'auth/invalid-phone-number') return 'Please include your country code, for example +919876543210.';
    if (code === 'auth/invalid-verification-code') return 'That SMS code is incorrect. Check the message and try again.';
    if (code === 'auth/code-expired' || code === 'auth/session-expired') return 'The SMS code expired. Send a new code.';
    if (code === 'auth/too-many-requests' || code === 'auth/quota-exceeded') return 'SMS verification is temporarily limited. Please try again later.';
    if (code === 'auth/operation-not-allowed' || code === 'auth/billing-not-enabled') return 'Phone verification is not enabled by the site administrator.';
    return 'Phone verification could not finish. Please check your connection and try again.';
  };

  try {
    if (!config?.apiKey || !config?.authDomain || !config?.projectId || !config?.appId)
      throw new Error('Missing Firebase public configuration');
    auth = getAuth(initializeApp(config));
    auth.useDeviceLanguage();
    await setPersistence(auth, inMemoryPersistence);
    recaptcha = new RecaptchaVerifier(auth, 'auth-recaptcha', {size:'normal'});
    await recaptcha.render();
  } catch (error) {
    show('Phone OTP is unavailable on this browser. Please use email sign-in.');
    if (sendButton) sendButton.disabled = true;
  }

  sendForm?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!auth || !recaptcha || busy) return;
    const phone = (phoneField?.value || '').trim().replace(/\s+/g, '');
    if (!/^\+[1-9][0-9]{7,14}$/.test(phone)) {
      show('Use the full international number, such as +919876543210.'); return;
    }
    if (Date.now() - lastAttempt < 60000) {
      show('Please allow a minute before requesting another SMS code.'); return;
    }
    busy = true;
    if (sendButton) sendButton.disabled = true;
    show('Sending a verification code to your phone…');
    try {
      confirmation = await signInWithPhoneNumber(auth, phone, recaptcha);
      lastAttempt = Date.now();
      if (sendForm) sendForm.hidden = true;
      if (verifyForm) verifyForm.hidden = false;
      codeField?.focus();
      show('Verification code sent. Enter the 6-digit code from your SMS.');
    } catch (error) {
      show(feedback(error));
      try {recaptcha.clear();} catch (_) {}
      recaptcha = new RecaptchaVerifier(auth, 'auth-recaptcha', {size:'normal'});
      try {await recaptcha.render();} catch (_) {}
    } finally {
      busy = false;
      if (sendButton) sendButton.disabled = false;
    }
  });

  verifyForm?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!confirmation || busy) return;
    const sms = (codeField?.value || '').trim();
    if (!/^[0-9]{6}$/.test(sms)) {show('Please enter the 6-digit SMS code.');return;}
    busy = true;
    const verifyButton = verifyForm.querySelector('button[type="submit"]');
    if (verifyButton) verifyButton.disabled = true;
    show('Verifying your number securely…');
    try {
      const result = await confirmation.confirm(sms);
      const idToken = await result.user.getIdToken(true);
      const response = await fetch('/auth/phone-session', {
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({id_token:idToken})
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok || !data.next_url || !data.next_url.startsWith('/')) {
        show(data.error || 'Phone sign-in could not be completed.');return;
      }
      show('Verified! Opening your secure MindCare account…');
      await signOut(auth);
      window.location.assign(data.next_url);
    } catch (error) {
      show(feedback(error));
    } finally {
      busy = false;
      if (verifyButton) verifyButton.disabled = false;
    }
  });
  resetButton?.addEventListener('click', () => {
    if (busy) return;
    confirmation = null;
    if (sendForm) sendForm.hidden = false;
    if (verifyForm) verifyForm.hidden = true;
    if (codeField) codeField.value = '';
    show('Enter another number and request a new SMS code.');
  });
}
