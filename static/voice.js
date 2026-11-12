/* A warm spoken guide for patients. Uses device voices, never uploads speech or health data. */
(() => {
  'use strict';
  if (document.body?.dataset.patient !== '1') return;
  const supported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  const synth = supported ? window.speechSynthesis : null;
  const toast = document.getElementById('voice-toast');
  const status = document.getElementById('voice-status');
  const replay = document.getElementById('voice-replay');
  const greeting = 'Hello. Welcome to MindCare. I am here to help you, one gentle step at a time.';
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
    if (!lang.startsWith('en')) return -1000;
    let points = 10;
    if (lang.startsWith('en-in')) points += 8;
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
    voice = [...available].sort((a,b) => score(b)-score(a))[0];
    if (score(voice) < 0) voice = null;
  };
  if (supported) {
    chooseVoice();
    synth.addEventListener?.('voiceschanged', chooseVoice);
    if (status) status.textContent = 'Gentle voice is on';
  } else if (status) status.textContent = 'Voice unavailable on this device';

  const speak = (message, options={}) => {
    if (!supported || !message || document.hidden || callPause) return false;
    const clean = String(message).trim().slice(0,240);
    const now = Date.now();
    if (!options.repeat && clean === lastSpoken && now - lastTime < 2800) return false;
    lastSpoken = clean;
    lastTime = now;
    try {
      const utterance = new SpeechSynthesisUtterance(clean);
      if (!voice) chooseVoice();
      if (voice) {utterance.voice=voice; utterance.lang=voice.lang;}
      else utterance.lang='en-IN';
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
