/* Opt-in device notifications while MindCare remains open.
   This does not pretend to deliver push notifications after a tab/browser closes. */
(() => {
  'use strict';
  if (document.body?.dataset.patient !== '1') return;
  const button = document.getElementById('reminder-notify-button');
  const label = document.getElementById('reminder-notify-status');
  const preference = 'mindcare-browser-reminder-alerts-v1';
  const supported = window.isSecureContext && 'Notification' in window;
  const lang = (document.documentElement.lang || '').slice(0, 2);
  const captions = {
    en: {on:'Alerts are enabled on this device while MindCare is open.',
      off:'Alerts are turned off on this device.',enable:'Enable browser alerts',
      disable:'Turn alerts off',denied:'Notifications are blocked. Allow them in your browser settings.',
      unavailable:'Notifications are unavailable in this browser.',
      alert:'MindCare reminder'},
    hi: {on:'माइंडकेयर खुला रहने पर सूचनाएँ चालू हैं।',off:'इस डिवाइस पर सूचनाएँ बंद हैं।',
      enable:'ब्राउज़र सूचनाएँ चालू करें',disable:'सूचनाएँ बंद करें',
      denied:'ब्राउज़र सेटिंग में सूचनाओं की अनुमति दें।',unavailable:'यह ब्राउज़र सूचनाएँ नहीं दिखा सकता।',alert:'माइंडकेयर याद दिलाना'},
    kn: {on:'ಮೈಂಡ್‌ಕೇರ್ ತೆರೆದಿರುವಾಗ ಸೂಚನೆಗಳು ಆನ್ ಆಗಿವೆ.',off:'ಈ ಸಾಧನದಲ್ಲಿ ಸೂಚನೆಗಳು ಆಫ್ ಆಗಿವೆ.',
      enable:'ಬ್ರೌಸರ್ ಸೂಚನೆಗಳನ್ನು ಆನ್ ಮಾಡಿ',disable:'ಸೂಚನೆಗಳನ್ನು ಆಫ್ ಮಾಡಿ',
      denied:'ಬ್ರೌಸರ್ ಸೆಟ್ಟಿಂಗ್‌ಗಳಲ್ಲಿ ಸೂಚನೆಗಳಿಗೆ ಅನುಮತಿ ನೀಡಿ.',unavailable:'ಈ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಸೂಚನೆಗಳು ಲಭ್ಯವಿಲ್ಲ.',alert:'ಮೈಂಡ್‌ಕೇರ್ ಜ್ಞಾಪನೆ'}
  }[lang] || null;
  const t = captions || {
    on:'Alerts work while MindCare is open.',off:'Alerts are off.',
    enable:'Enable browser alerts',disable:'Turn alerts off',
    denied:'Notifications are blocked in the browser.',unavailable:'Notifications unavailable.',
    alert:'MindCare reminder'
  };
  const delivered = new Set();
  let fetching = false;
  const enabled = () => {
    try {return localStorage.getItem(preference) === '1';} catch (_) {return false;}
  };
  const setEnabled = value => {try {localStorage.setItem(preference, value?'1':'0');} catch (_) {}};
  function refresh() {
    if (button) {
      button.disabled = !supported || (supported && Notification.permission === 'denied');
      button.textContent = enabled() && supported && Notification.permission === 'granted' ? t.disable : t.enable;
      button.setAttribute('aria-pressed', String(enabled() && supported && Notification.permission === 'granted'));
    }
    if (label) label.textContent = !supported ? t.unavailable :
      Notification.permission === 'denied' ? t.denied :
      enabled() && Notification.permission === 'granted' ? t.on : t.off;
  }
  button?.addEventListener('click', async () => {
    if (!supported) return;
    if (enabled()) {setEnabled(false);refresh();return;}
    let permission = Notification.permission;
    if (permission === 'default') {
      try {permission = await Notification.requestPermission();}
      catch (_) {permission = 'denied';}
    }
    if (permission === 'granted') setEnabled(true);
    refresh();
    if (enabled()) check();
  });
  function istNow() {
    const fields = new Intl.DateTimeFormat('en-GB', {
      timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',hourCycle:'h23'
    }).formatToParts(new Date());
    const parts = Object.fromEntries(fields.map(x=>[x.type,x.value]));
    return {day:parts.year+'-'+parts.month+'-'+parts.day,
      minutes:Number(parts.hour)*60+Number(parts.minute)};
  }
  async function check() {
    if (!supported || !enabled() || Notification.permission !== 'granted' || fetching || !navigator.onLine) return;
    fetching = true;
    try {
      const response = await fetch('/api/reminders/today',{credentials:'same-origin',cache:'no-store'});
      if (!response.ok) return;
      const result = await response.json();
      const now = istNow();
      for (const reminder of result.reminders || []) {
        if (reminder.done) continue;
        const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(reminder.time||'');
        if (!match) continue;
        const due = Number(match[1])*60+Number(match[2]);
        // A brief late grace period covers a sleeping or throttled background tab.
        if (now.minutes < due || now.minutes - due > 15) continue;
        const key = 'mindcare-reminder-notified:'+now.day+':'+reminder.id+':'+reminder.time;
        if (delivered.has(key)) continue;
        try {if(localStorage.getItem(key)==='1'){delivered.add(key);continue;}}catch (_) {}
        delivered.add(key);
        try {localStorage.setItem(key,'1');}catch (_) {}
        const n = new Notification(t.alert, {
          body:String(reminder.title||'').slice(0,110),tag:key,silent:false
        });
        n.onclick = () => {window.focus();window.location.assign('/reminders');n.close();};
      }
    } catch (_) { /* The app must remain usable when notification APIs/network fail. */ }
    finally {fetching=false;}
  }
  refresh();
  check();
  setInterval(check, 20000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
})();
