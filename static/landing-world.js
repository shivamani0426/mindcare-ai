(() => {
  'use strict';
  if (!document.body.classList.contains('mc-world-page')) return;

  // First-visit cinematic entrance. Keep the existing dialog/focus hooks
  // and replace only the entrance choreography, never the landing or login.
  const carpet = document.getElementById('mc-carpet-intro');
  const enter = document.getElementById('mc-carpet-enter');
  const skip = document.getElementById('mc-carpet-skip');
  const replay = document.getElementById('mc-hero-replay');
  const world = document.querySelector('.mc-world-root');
  const skipLink = document.querySelector('.skip');
  const prefs = ['(prefers-reduced-motion: reduce)','(prefers-contrast: more)','(forced-colors: active)'].map(s=>matchMedia(s));
  const motionAllowed = () => !prefs.some(p=>p.matches) && !document.body.classList.contains('reduced-motion');
  const storageKey = 'mindcare-z-entrance-v1';
  let seen = false;
  try { seen = sessionStorage.getItem(storageKey) === '1'; } catch (_) {}
  let phase = 'ready', frame = 0, started = null, touchY = null, focusAfter = false;
  let completed = 0;
  const clamp = v => Math.max(0,Math.min(1,v));
  const smooth = v => {const t=clamp(v);return t*t*(3-2*t);};
  const remember = () => {try{sessionStorage.setItem(storageKey,'1');}catch(_){}};
  const strokes = [...(carpet?.querySelectorAll('.mc-z-slash')||[])].map((group,index)=>({
    group, paths:[...group.querySelectorAll('path')], tip:group.querySelector('circle'),
    coords:[[180,300,820,300],[820,300,180,700],[180,700,820,700]][index]
  }));
  const starts=[180,535,890], cutTime=260, revealAt=1390, total=2080;
  const paint = elapsed => {
    const set=(k,v)=>carpet.style.setProperty(k,String(v));
    set('--z-title',1-smooth(elapsed/160));
    const reveal=smooth((elapsed-revealAt)/(total-revealAt));
    set('--z-reveal',reveal);
    set('--z-glow',1-smooth((elapsed-revealAt)/(total-revealAt)*1.4));
    carpet.dataset.progress=clamp(elapsed/total).toFixed(3);
    carpet.dataset.reveal=reveal.toFixed(3);
    strokes.forEach((stroke,i)=>{
      const p=clamp((elapsed-starts[i])/cutTime);
      const t=1-Math.pow(1-p,1.6);
      stroke.group.setAttribute('opacity',p>0?'1':'0');
      stroke.paths.forEach(path=>path.setAttribute('stroke-dashoffset',(1-t).toFixed(4)));
      const [x1,y1,x2,y2]=stroke.coords;
      stroke.tip.setAttribute('cx',x1+(x2-x1)*t);
      stroke.tip.setAttribute('cy',y1+(y2-y1)*t);
      stroke.tip.setAttribute('opacity',p>0&&p<1?'1':'0');
    });
    const count=starts.filter(start=>elapsed>=start+cutTime).length;
    if(count>completed){
      while(completed<count){
        completed++;
        carpet.dataset.cuts=String(completed);
        document.dispatchEvent(new CustomEvent('mindcare:entrance-cut',{detail:{cut:completed,reveal}}));
      }
    }
    carpet.dataset.cuts=String(completed);
  };
  const stop=()=>{if(frame)cancelAnimationFrame(frame);frame=0;started=null;touchY=null;};
  const release=()=>{
    carpet.hidden=true;
    world.inert=false;
    if(skipLink)skipLink.inert=false;
    document.body.classList.remove('mc-carpet-active','mc-carpet-arrival','mc-hero-assembling');
    document.body.classList.add('mc-hero-resting');
    enter.disabled=false;
    remember();
    if(focusAfter){world.querySelector('.mc-hero-enter')?.focus({preventScroll:true});focusAfter=false;}
    if(replay)replay.hidden=!motionAllowed();
  };
  const finishImmediately=()=>{stop();phase='ready';release();};
  const animate=now=>{
    frame=0;
    if(phase!=='cutting')return;
    if(!motionAllowed()){finishImmediately();return;}
    if(started===null)started=now;
    const elapsed=Math.min(total,now-started);
    paint(elapsed);
    if(elapsed>=total){finishImmediately();return;}
    frame=requestAnimationFrame(animate);
  };
  const begin=()=>{
    if(phase!=='waiting')return;
    phase='cutting';
    carpet.dataset.running='true';
    // The always-visible Skip remains the only focusable dialog control.
    skip.focus({preventScroll:true});
    enter.disabled=true;
    frame=requestAnimationFrame(animate);
  };
  const showCarpet=()=>{
    if(!motionAllowed()){finishImmediately();return;}
    stop();phase='waiting';focusAfter=true;completed=0;
    carpet.dataset.running='false';
    paint(0);
    document.body.classList.remove('mc-hero-assembling','mc-hero-resting','mc-carpet-arrival');
    document.body.classList.add('mc-carpet-active');
    carpet.hidden=false;world.inert=true;
    if(skipLink)skipLink.inert=true;
    if(replay)replay.hidden=true;
    enter.disabled=false;
    window.scrollTo(0,0);
    enter.focus({preventScroll:true});
  };
  window.addEventListener('mindcare:landing-dispose',()=>{stop();phase='disposed';},{once:true});
  if(carpet&&enter&&skip&&world&&strokes.length===3){
    carpet.addEventListener('wheel',event=>{
      if((phase!=='waiting'&&phase!=='cutting')||event.ctrlKey)return;
      event.preventDefault();if(event.deltaY>0)begin();
    },{passive:false});
    carpet.addEventListener('touchstart',event=>{touchY=event.touches.length===1?event.touches[0].clientY:null;},{passive:true});
    carpet.addEventListener('touchmove',event=>{
      if((phase!=='waiting'&&phase!=='cutting')||touchY===null||event.touches.length!==1)return;
      const delta=touchY-event.touches[0].clientY;
      if(Math.abs(delta)>12){event.preventDefault();if(delta>0)begin();}
    },{passive:false});
    ['touchend','touchcancel'].forEach(name=>carpet.addEventListener(name,()=>{touchY=null;}));
    enter.addEventListener('click',begin);
    skip.addEventListener('click',finishImmediately);
    carpet.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();finishImmediately();}
      else if(['ArrowDown','PageDown','End'].includes(event.key)){event.preventDefault();begin();}
      else if(event.key==='Tab'){event.preventDefault();(phase==='cutting'?skip:document.activeElement===enter?skip:enter).focus();}
    });
    replay?.addEventListener('click',showCarpet);
    prefs.forEach(pref=>pref.addEventListener?.('change',()=>{
      if(phase==='disposed')return;
      if(!motionAllowed()&&phase!=='ready')finishImmediately();
      else if(phase==='ready'&&replay)replay.hidden=!motionAllowed();
    }));
    if(motionAllowed()&&!seen&&!location.hash)showCarpet();
    else finishImmediately();
  }
  
  // Three fully accessible, keyboard-operable capability tabs.
  const tabs = [...document.querySelectorAll('.mc-cap-tab[role="tab"]')];
  const activateTab = (selected, focus = false) => {
    tabs.forEach(tab => {
      const active = tab === selected;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
    if (focus) selected.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', event => {
      let targetIndex;
      if (event.key === 'ArrowRight') targetIndex = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') targetIndex = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') targetIndex = 0;
      else if (event.key === 'End') targetIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[targetIndex], true);
    });
  });

  // Two simulated patient/caregiver previews; no autoplay or network traffic.
  const slideButtons = [...document.querySelectorAll('[data-mc-slide]')];
  const slides = [...document.querySelectorAll('.mc-product-slide')];
  const showSlide = index => {
    if (index < 0 || index >= slides.length) return;
    slides.forEach((slide, i) => { slide.hidden = i !== index; });
    slideButtons.forEach((button, i) => {
      button.setAttribute('aria-pressed', String(i === index));
    });
  };
  slideButtons.forEach((button, index) => {
    button.addEventListener('click', () => showSlide(index));
    button.addEventListener('keydown', event => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + slideButtons.length) % slideButtons.length;
      showSlide(next);
      slideButtons[next].focus();
    });
  });

  // Suspend the expensive decorative hero motion while visitors read the
  // lower sections. One observer; no scroll events, polling or layout writes.
  const heroForMotion = document.querySelector('.mc-world-hero');
  if (heroForMotion && 'IntersectionObserver' in window) {
    const heroVisibility = new IntersectionObserver(([entry]) => {
      document.body.classList.toggle('mc-hero-out-of-view', !entry.isIntersecting);
    },{threshold:0.01});
    heroVisibility.observe(heroForMotion);
    window.addEventListener('mindcare:landing-dispose', () => heroVisibility.disconnect(), {once:true});
  }

  // Highlight actual section in sticky nav, without moving keyboard focus.
  const navLinks = [...document.querySelectorAll('.mc-world-nav-links a[href^="#"]')];
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (!visible.length) return;
      const id = '#' + visible[0].target.id;
      navLinks.forEach(link => {
        if (link.getAttribute('href') === id) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
    }, {rootMargin: '-70px 0px -40% 0px', threshold: [0, .15, .4]});
    window.addEventListener('mindcare:landing-dispose', () => observer.disconnect(), {once:true});
    ['overview', 'capabilities', 'discover', 'access'].forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
  }
})();
