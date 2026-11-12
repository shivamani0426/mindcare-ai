(() => {
  'use strict';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const fontButton = document.getElementById('font-toggle');
  try { if (localStorage.getItem('mindcare-large-text')==='1') document.body.classList.add('large-text'); } catch (_) {}
  fontButton?.addEventListener('click', () => {
    document.body.classList.toggle('large-text');
    fontButton.setAttribute('aria-pressed', String(document.body.classList.contains('large-text')));
    try { localStorage.setItem('mindcare-large-text', document.body.classList.contains('large-text') ? '1' : '0'); } catch (_) {}
  });
  fontButton?.setAttribute('aria-pressed',String(document.body.classList.contains('large-text')));
  document.querySelectorAll('.flash-close').forEach(b => b.addEventListener('click', () => b.closest('.flash')?.remove()));
  document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    const value = b.dataset.copy || '';
    try { await navigator.clipboard.writeText(value); b.textContent = 'Copied!'; }
    catch (_) { b.textContent = 'Select code to copy'; }
  }));
  document.querySelectorAll('[data-autosubmit]').forEach(s => s.addEventListener('change', () => s.form?.submit()));
  document.querySelectorAll('[data-confirm]').forEach(b => b.addEventListener('click', e => {
    if (!confirm(b.dataset.confirm || 'Are you sure?')) e.preventDefault();
  }));
  const roles = document.querySelectorAll('input[name="role"]');
  const extra = document.querySelector('.patient-extra');
  if (roles.length && extra) {
    const updateRole = () => { extra.hidden = document.querySelector('input[name="role"]:checked')?.value !== 'patient'; };
    roles.forEach(r => r.addEventListener('change', updateRole)); updateRole();
  }
  document.querySelectorAll('.trend-chart').forEach(el => {
    let values=[];
    try { values=JSON.parse(el.dataset.series || '[]'); } catch (_) { return; }
    if (!values.length) return;
    const NS = 'http://www.w3.org/2000/svg';
    const s = document.createElementNS(NS, 'svg'); s.setAttribute('viewBox', '0 0 600 225'); s.setAttribute('role', 'img');
    s.setAttribute('aria-label', 'Daily average scores ' + values.map(d => d.day + ': ' + d.score + '%').join(', '));
    const mk=(name, attrs, value) => { const e=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v))); if(value!=null)e.textContent=value;s.appendChild(e);return e; };
    [0,25,50,75,100].forEach(n=> {const y=190-n*1.65;mk('line',{x1:35,y1:y,x2:582,y2:y,class:'chart-grid'});mk('text',{x:5,y:y+4,class:'chart-label'},String(n));});
    const points=values.map((v,i)=>({x:values.length===1?310:40+(i/(values.length-1))*535,y:190-v.score*1.65}));
    if(points.length>1)mk('polyline',{points:points.map(p=>p.x+','+p.y).join(' '),class:'chart-line'});
    points.forEach((p,i)=> {mk('circle',{cx:p.x,cy:p.y,r:6,class:'chart-point'}); mk('text',{x:p.x,y:218,'text-anchor':'middle',class:'chart-label'},values[i].day);});
    el.appendChild(s);
  });
  // Client-side voice reminders only. No background notification or server-side promise.
  const voiceButton=document.getElementById('voice-enable');
  const toast=document.getElementById('voice-toast');
  if (voiceButton) {
    let lastKey='';
    let enabled = false;
    const tick = async () => {
      if (!enabled || document.hidden) return;
      try {
        const resp=await fetch('/api/reminders/today',{credentials:'same-origin'});
        if (!resp.ok) return;
        const {reminders=[]}=await resp.json();
        const now=new Date();
        const hhmm=String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');
        const due=reminders.find(r=>!r.done && r.time===hhmm);
        const key=now.toDateString()+hhmm+(due?.id||'');
        if(due && key!==lastKey) {
          lastKey=key;
          const message='A gentle reminder: '+due.title+'.';
          if(toast){toast.textContent='🔔 '+message;toast.hidden=false;setTimeout(()=>toast.hidden=true,15000);}
          if('speechSynthesis' in window) {window.speechSynthesis.cancel();window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));}
        }
      } catch (_) { /* Offline? Keep the app usable. */ }
    };
    voiceButton.addEventListener('click', () => {
      if(!('speechSynthesis' in window)){voiceButton.textContent='Voice is unavailable in this browser';voiceButton.disabled=true;return;}
      enabled=!enabled;
      voiceButton.textContent=enabled?'🔊 Spoken reminders are on':'🔊 Enable spoken reminders';
      if(enabled){window.speechSynthesis.speak(new SpeechSynthesisUtterance('Spoken reminders are enabled.'));tick();}
    });
    setInterval(tick,30000);
  }
})();
