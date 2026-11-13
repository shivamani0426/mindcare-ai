/* A warm spoken guide for patients. Uses device voices, never uploads speech or health data. */
(() => {
  'use strict';
  if (document.body?.dataset.patient !== '1') return;
  const supported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  const synth = supported ? window.speechSynthesis : null;
  const toast = document.getElementById('voice-toast');
  const status = document.getElementById('voice-status');
  const replay = document.getElementById('voice-replay');
  const language = (document.documentElement.lang || 'en').slice(0,2);
  const speechCopy = {
    en:{hello:'Hello. Welcome to MindCare. I am here to help you, one gentle step at a time.',
      reminder: title=>'A gentle reminder. It is time for '+title+'.'},
    hi:{hello:'नमस्ते। माइंडकेयर में आपका स्वागत है। हम धीरे-धीरे आगे बढ़ेंगे।',
      reminder:title=>'एक प्यार भरी याद। अब '+title+' का समय है।'},
    kn:{hello:'ನಮಸ್ಕಾರ. ಮೈಂಡ್‌ಕೇರ್‌ಗೆ ಸ್ವಾಗತ. ನಿಧಾನವಾಗಿ, ಒಂದೊಂದೇ ಹೆಜ್ಜೆ ಇಡೋಣ.',
      reminder:title=>'ಒಂದು ಸೌಮ್ಯ ಜ್ಞಾಪನೆ. ಈಗ '+title+' ಮಾಡುವ ಸಮಯವಾಗಿದೆ.'}
  };
  const greeting = speechCopy.en.hello;
  let nativeLanguageVoice = language === 'en';
  let voice = null;
  let unlocked = false;
  let greetingPlayed = false;
  try {greetingPlayed=sessionStorage.getItem('mindcare-voice-welcomed')==='1';} catch (_) {}
  let lastSpoken = '';
  let lastTime = 0;
  let reminderInProgress = false;
  let pendingAnnouncement = null;
  let callPause = false;
  const announced = new Set();

  const score = (v) => {
    const name = (v.name || '').toLowerCase();
    const lang = (v.lang || '').toLowerCase();
    if (!lang.startsWith(language === 'hi' || language === 'kn' ? language : 'en')) return -1000;
    let points = 10;
    if (lang.startsWith((language === 'hi' || language === 'kn' ? language : 'en')+'-in')) points += 8;
    if (v.localService) points += 3;
    if (name.includes('natural') || name.includes('neural') || name.includes('enhanced')) points += 12;
    // These are voice names, not a gender classification of a person.
    const gentleNames = ['jenny','aria','samantha','ava','moira','karen','serena','zira',
      'hazel','susan','tessa','heera','neerja','salli','joanna','female','priya','emma','kate'];
    if (gentleNames.some(n => name.includes(n))) points += 90;
    if (name.includes('male') && !name.includes('female')) points -= 65;
    if (name.includes('daniel') || name.includes('david') || name.includes('mark')) points -= 50;
    return points;
  };
  const chooseVoice = () => {
    if (!synth) return;
    const available = synth.getVoices();
    if (!available.length) return;
    const chosen = [...available].sort((a,b) => score(b)-score(a))[0];
    nativeLanguageVoice = !!chosen && score(chosen) >= 0;
    if (nativeLanguageVoice) voice = chosen;
    else {
      // Never attempt to read Hindi or Kannada as nonsensical English phonetics.
      // Speak clear English on devices that lack a local-language TTS voice.
      voice = available.find(v=>(v.lang||'').toLowerCase().startsWith('en')) || null;
    }
    if (status) status.textContent = nativeLanguageVoice ?
      ({hi:'हिंदी में आवाज़ चालू है',kn:'ಕನ್ನಡದಲ್ಲಿ ಧ್ವನಿ ಆನ್ ಆಗಿದೆ'}[language] || 'Gentle voice is on') :
      'This device uses English voice guidance';
  };
  if (supported) {
    chooseVoice();
    synth.addEventListener?.('voiceschanged', chooseVoice);
    if (status && !status.textContent) status.textContent = 'Gentle voice is on';
  } else if (status) status.textContent = 'Voice unavailable on this device';

  const speak = (message, options={}) => {
    if (!supported || !message || document.hidden || callPause) return false;
    const original = String(message).trim();
    let rendered = original;
    if (nativeLanguageVoice && language !== 'en') {
      if (original === greeting) rendered = speechCopy[language].hello;
      else if (original.startsWith('A gentle reminder. It is time for ') && original.endsWith('.')) {
        rendered = speechCopy[language].reminder(original.slice(33, -1));
      } else rendered = window.MindCareGameTranslate?.(original) || original;
    }
    const clean = rendered.slice(0,240);
    const now = Date.now();
    if (!options.repeat && clean === lastSpoken && now - lastTime < 2800) return false;
    lastSpoken = clean;
    lastTime = now;
    try {
      const utterance = new SpeechSynthesisUtterance(clean);
      if (!voice) chooseVoice();
      if (voice) {utterance.voice=voice; utterance.lang=voice.lang;}
      else utterance.lang = nativeLanguageVoice ?
        ({hi:'hi-IN',kn:'kn-IN'}[language] || 'en-IN') : 'en-IN';
      utterance.rate=.86; // Slower, clear and unhurried.
      utterance.pitch=1.12;
      utterance.volume=.95;
      if (options.replace !== false) synth.cancel();
      synth.speak(utterance);
      return true;
    } catch (_) { return false; }
  };
  const announce = (message, duration=11000) => {
    if (toast) {
      toast.textContent='🔔 '+message;
      toast.hidden=false;
      setTimeout(()=>{if(toast.textContent==='🔔 '+message)toast.hidden=true;},duration);
    }
    speak(message,{repeat:true});
  };
  const unlock = () => {
    if (unlocked) return;
    unlocked=true;
    if (pendingAnnouncement) {
      const pending=pendingAnnouncement;pendingAnnouncement=null;
      announce(pending.message,15000);
      try {localStorage.setItem(pending.key,'1');} catch (_) {}
    } else if (!greetingPlayed && !document.hidden) {
      greetingPlayed=true;
      try {sessionStorage.setItem('mindcare-voice-welcomed','1');} catch (_) {}
      speak(greeting);
    }
  };
  // Browser autoplay rules can require a tap or keypress before any speech.
  document.addEventListener('pointerdown', unlock, {capture:true});
  document.addEventListener('keydown', unlock, {capture:true});
  replay?.addEventListener('click', () => {unlocked=true;speak(greeting,{repeat:true});});
  window.MindCareVoice = {speak, announce, available:supported,
    replay() {unlocked=true; speak(greeting,{repeat:true});},
    pause() {callPause = true; try {synth?.cancel();} catch (_) {}},
    resume() {callPause = false;}};

  const tick = async () => {
    if (reminderInProgress || document.hidden || callPause || !navigator.onLine) return;
    reminderInProgress=true;
    try {
      const resp = await fetch('/api/reminders/today', {credentials:'same-origin',cache:'no-store'});
      if (!resp.ok) return;
      const {reminders=[]} = await resp.json();
      const now=new Date();
      const day=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0');
      const currentMinutes=now.getHours()*60+now.getMinutes();
      // Only announce reminders due within the last two minutes; old ones can
      // still be marked complete without repeated distressing announcements.
      const due=reminders.filter(r=>{
        const match=/^([01]\d|2[0-3]):([0-5]\d)$/.exec(r.time||'');
        if (!match || r.done) return false;
        const minutes=Number(match[1])*60+Number(match[2]);
        return currentMinutes>=minutes && currentMinutes-minutes<=2;
      });
      for(const item of due) {
        const key='mindcare-voice-reminder:'+day+':'+item.id;
        if (announced.has(key)) continue;
        try {if(localStorage.getItem(key)==='1') {announced.add(key);continue;}} catch (_) {}
        announced.add(key);
        const message='A gentle reminder. It is time for '+item.title+'.';
        if (!unlocked) {
          pendingAnnouncement={key,message};
          if(toast){toast.textContent='🔔 '+message;toast.hidden=false;}
        } else {
          try {localStorage.setItem(key,'1');} catch (_) {}
          announce(message,15000);
        }
        break; // Avoid speaking several reminders on top of each other.
      }
    } catch (_) { /* Network or login can be interrupted without blocking games. */ }
    finally {reminderInProgress=false;}
  };
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
  setInterval(tick,20000);
  tick();
})();
