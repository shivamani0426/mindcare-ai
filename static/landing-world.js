(() => {
  'use strict';
  if (!document.body.classList.contains('mc-world-page')) return;

  // Play on arrival at the actual homepage, not on an entry-button click.
  // One short compositor timeline; no frame-count-dependent animation loop.
  const intro=document.getElementById('mc-carpet-intro');
  const flight=intro?.querySelector('.mc-comet-flight');
  const sparks=intro?.querySelector('.mc-comet-sparks');
  const world=document.querySelector('.mc-world-root');
  const skipLink=document.querySelector('.skip');
  const preferences=['(prefers-reduced-motion: reduce)','(prefers-contrast: more)','(forced-colors: active)'].map(q=>matchMedia(q));
  const mobile=matchMedia('(max-width:600px),(pointer:coarse)');
  const motionAllowed=()=>!preferences.some(p=>p.matches)&&!document.body.classList.contains('reduced-motion');
  const storageKey='mindcare-comet-entered-v1';
  let seen=false, active=false, disposed=false, timer=0, animations=[], started=0;
  try{seen=sessionStorage.getItem(storageKey)==='1';}catch(_){}
  const notify=(phase,detail={})=>document.dispatchEvent(new CustomEvent('mindcare:comet-'+phase,{detail}));
  function finish(reason='complete'){
    const wasActive=active;
    active=false;clearTimeout(timer);timer=0;
    for(const animation of animations)animation.cancel();
    animations=[];
    if(intro)intro.hidden=true;
    if(sparks)sparks.replaceChildren();
    if(world)world.inert=false;
    if(skipLink)skipLink.inert=false;
    document.body.classList.remove('mc-carpet-active','mc-carpet-arrival','mc-hero-assembling');
    if(!disposed)document.body.classList.add('mc-hero-resting');
    if(wasActive)notify('finished',{reason,elapsed:performance.now()-started});
  }
  function play(){
    if(!intro||!flight||!sparks||!world||!motionAllowed()||typeof flight.animate!=='function'){finish('unsupported');return;}
    const w=window.innerWidth,h=window.innerHeight;
    if(w<=0||h<=0){finish('empty-viewport');return;}
    // Travel from just outside the top-right to outside the bottom-left.
    // The hot tip points exactly along the physical viewport diagonal.
    const x0=w*1.04,y0=-h*.04,x1=-w*.20,y1=h*1.20;
    const dx=x1-x0,dy=y1-y0,length=Math.hypot(dx,dy),ux=dx/length,uy=dy/length;
    const angle=Math.atan2(dy,dx)*180/Math.PI;
    const delay=55,travel=445,revealStart=delay+travel+25,revealDuration=300;
    const count=mobile.matches?14:30;
    const pose=(x,y,a)=>'translate3d('+x+'px,'+y+'px,0) rotate('+a+'deg)';
    const startPose=pose(x0,y0,angle),endPose=pose(x1,y1,angle);
    active=true;started=performance.now();
    try{sessionStorage.setItem(storageKey,'1');}catch(_){}
    intro.hidden=false;world.inert=true;if(skipLink)skipLink.inert=true;
    document.body.classList.remove('mc-hero-assembling','mc-hero-resting','mc-carpet-arrival');
    document.body.classList.add('mc-carpet-active');
    // A hard wall-clock release protects WebKit and interrupted animations.
    timer=setTimeout(()=>finish('deadline'),1600);
    try{
      const comet=flight.animate([
        {transform:startPose,opacity:1,offset:0},
        {transform:pose(x0+dx*.92,y0+dy*.92,angle),opacity:1,offset:.92},
        {transform:endPose,opacity:.35,offset:1}
      ],{duration:travel,delay,fill:'both',easing:'linear'});
      animations.push(comet);
      // World-space embers detach from the blade and scatter backward;
      // each has independent emission time, velocity, spread and lifetime.
      const fragment=document.createDocumentFragment(),particles=[];
      for(let i=0;i<count;i++){
        const node=document.createElement('span');node.className='mc-comet-spark';fragment.append(node);
        const t=.08+.78*i/(count-1),side=i%2===0?1:-1;
        const spread=side*(18+(i*31%104)),drift=38+(i*47%132);
        const sx=x0+dx*t-ux*24,sy=y0+dy*t-uy*24;
        const ex=sx-ux*drift-uy*spread,ey=sy-uy*drift+ux*spread+22;
        particles.push({node,t,sx,sy,ex,ey,rotation:Math.atan2(ey-sy,ex-sx)*180/Math.PI});
      }
      sparks.append(fragment);
      for(const p of particles){
        animations.push(p.node.animate([
          {transform:pose(p.sx,p.sy,p.rotation)+' scaleX(.65)',opacity:.9,offset:0},
          {transform:pose(p.sx+(p.ex-p.sx)*.36,p.sy+(p.ey-p.sy)*.36,p.rotation)+' scaleX(1.35)',opacity:1,offset:.32},
          {transform:pose(p.ex,p.ey,p.rotation)+' scaleX(.22)',opacity:0,offset:1}
        ],{delay:delay+travel*p.t,duration:190+((particles.indexOf(p)*37)%110),fill:'none',easing:'ease-out'}));
      }
      const reveal=intro.animate([{opacity:1},{opacity:0}],{delay:revealStart,duration:revealDuration,fill:'both',easing:'ease-out'});
      animations.push(reveal);
      notify('started',{x0,y0,x1,y1,angle,travel,delay,revealStart,revealDuration,count});
      reveal.finished.then(()=>{if(active)finish();},()=>{if(active)finish('cancelled');});
    }catch(_){finish('unsupported');}
  }
  document.addEventListener('keydown',event=>{if(active&&event.key==='Escape'){event.preventDefault();finish('escape');}});
  preferences.forEach(pref=>pref.addEventListener?.('change',()=>{if(active&&!motionAllowed())finish('preference');}));
  window.addEventListener('pagehide',()=>{if(active)finish('pagehide');});
  window.addEventListener('mindcare:landing-dispose',()=>{disposed=true;finish('disposed');},{once:true});
  // A new tab/first visit plays once. Refresh, back and deep links remain immediate.
  if(!seen&&!location.hash&&motionAllowed())play();else finish('bypass');

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
