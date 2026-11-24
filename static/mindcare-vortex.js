(() => {
  'use strict';
  const root = document.documentElement;
  const stage = document.getElementById('mc-vortex');
  if (!stage || !document.body.classList.contains('mc-world-page')) return;
  const space = stage.querySelector('.mc-vortex-space');
  const backdrop = stage.querySelector('.mc-vortex-backdrop');
  const prefs = ['(prefers-reduced-motion: reduce)','(prefers-contrast: more)','(forced-colors: active)'].map(s => matchMedia(s));
  const motion = () => !prefs.some(p => p.matches) && !document.body.classList.contains('reduced-motion');
  let destination = null, controller = null, mounted = false, busy = false, scene = null;
  let generation = 0, requestTimer = 0, group = [], gravity = null;
  const report = (reason) => document.dispatchEvent(new CustomEvent('mindcare:gravity-fallback',{detail:{reason}}));
  const portalTransform = scale => 'translate3d(-50%,-50%,0) scale(' + scale + ')';
  // One bounded compositor surface follows a tightening spiral, with
  // synchronized rotation, radius, depth tilt and contraction. No DOM
  // cloning, mesh, animated filter, extra canvas or per-frame layout.
  const spiralPath = () => {
    const radius = Math.min(window.innerWidth,window.innerHeight) * .10;
    const anchors = [
      // time, scale, accumulated turn (degrees), orbit radius, tilt, opacity
      [0,1,0,0,0,1],
      [.18,.91,-22,.90,7,1],
      [.43,.63,-112,1,18,1],
      [.72,.26,-242,.42,12,.95],
      [1,.035,-360,0,0,0]
    ];
    const frames = [];
    // Sample a true curved orbit so it doesn't cut across straight chords.
    for (let i=0;i<anchors.length-1;i++) {
      const a=anchors[i], b=anchors[i+1];
      for (let step=0;step<8;step++) {
        const t=step/8;
        const [offset,scale,angle,r,tilt,opacity]=a.map((v,k)=>v+(b[k]-v)*t);
        const theta=angle*Math.PI/180;
        const x=radius*r*Math.cos(theta);
        const y=radius*r*Math.sin(theta)*.72;
        frames.push({offset,opacity,transform:`translate3d(${x.toFixed(3)}px,${y.toFixed(3)}px,0) rotateZ(${angle}deg) rotateY(${tilt}deg) scale(${scale})`});
      }
    }
    frames.push({offset:1,opacity:0,transform:'translate3d(0px,0px,0) rotateZ(-360deg) rotateY(0deg) scale(.035)'});
    return frames;
  };
  const duration = 1650;
  const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const reset = () => {
    clearTimeout(requestTimer);
    gravity?.destroy(); gravity = null;
    controller?.abort();
    controller = null;
    group.forEach(a => a.cancel());
    group = [];
    if (scene?.isConnected) {
      scene.querySelectorAll('[data-mc-vacuum-offscreen]').forEach(el => el.removeAttribute('data-mc-vacuum-offscreen'));
      const shell = scene.querySelector('.site-shell');
      if (shell) scene.replaceWith(shell);
      else scene.remove();
    }
    scene = null;
    root.classList.remove('mc-vortex-departing','mc-vortex-arriving','mc-vortex-open');
    root.style.removeProperty('--mc-vortex-scroll-offset');
    stage.hidden = true;
    stage.dataset.phase = 'idle';
    space.style.removeProperty('transform');
    backdrop.style.removeProperty('opacity');
    document.querySelector('.site-shell')?.removeAttribute('inert');
    document.querySelector('.skip')?.removeAttribute('inert');
    destination = null;
    busy = false;
  };
  const fallback = () => {
    const url = destination;
    ++generation;
    reset();
    if (url && !mounted) location.assign(url);
  };
  const finish = () => {
    ++generation;
    reset();
    const heading = document.getElementById('auth-title');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({preventScroll:true});
    }
  };
  const setPose = (element, pose) => {
    if (pose.transform) element.style.transform = pose.transform;
    if (pose.opacity !== undefined) element.style.opacity = String(pose.opacity);
  };
  // All three compositor animations share one start time. Commit their
  // terminal poses BEFORE cancelling; no animationend race or cleanup timer.
  const play = async (specs, token) => {
    for (const [element,frames] of specs) setPose(element,frames[0]);
    await frame();
    if (token !== generation) return false;
    const start = document.timeline.currentTime;
    const animations = specs.map(([element,frames]) => {
      const a = element.animate(frames,{duration,easing:'cubic-bezier(.42,0,.58,1)',fill:'both'});
      a.startTime = start;
      return a;
    });
    group = animations;
    const phase = stage.dataset.phase;
    document.dispatchEvent(new CustomEvent('mindcare:vortex-motion',{detail:{phase,duration}}));
    // The GPU path advances all three WAAPI effects with one bounded frame clock.
    // The existing wall-clock compositor path is used when GPU preparation fails.
    const rendered = gravity?.run(animations,phase,duration);
    if (rendered) await rendered;
    else {
      // Preserve normal compositor playback, but bound gaps between poses
      // on slow renderers. A real timer (not RAF) guarantees that a
      // throttled/background tab cannot delay navigation indefinitely.
      let raf = 0, deadline = 0, previous = 0;
      await new Promise(resolve => {
        let done = false;
        const complete = () => {
          if (done) return;
          done = true;
          cancelAnimationFrame(raf);
          clearTimeout(deadline);
          resolve();
        };
        const tick = () => {
          if (token !== generation) { complete(); return; }
          const current = Number(animations[0].currentTime);
          if (current - previous > 100) {
            previous = Math.min(duration, previous + 100);
            animations.forEach(a => { a.currentTime = previous; });
          } else {
            previous = Math.max(previous, current);
          }
          if (previous >= duration) complete();
          else raf = requestAnimationFrame(tick);
        };
        deadline = setTimeout(complete, duration * 2.6);
        raf = requestAnimationFrame(tick);
      });
    }
    if (token !== generation) return false;
    gravity?.settle(phase);
    specs.forEach(([element,frames]) => setPose(element,frames[frames.length-1]));
    animations.forEach(a => a.cancel());
    group = [];
    return true;
  };
  const fetchLogin = async url => {
    const response = await fetch(url, {
      credentials:'same-origin', cache:'no-store', signal:controller.signal,
      redirect:'follow', headers:{Accept:'text/html'}
    });
    if (!response.ok || response.redirected || new URL(response.url).origin !== location.origin ||
        new URL(response.url).pathname !== url.pathname) throw Error('Login navigation required');
    const doc = new DOMParser().parseFromString(await response.text(),'text/html');
    const shell = doc.querySelector('.site-shell');
    const form = shell?.querySelector('[data-auth-mode="login"] form#auth-email-form');
    const csrf = doc.querySelector('meta[name="csrf-token"]')?.content;
    if (!doc.body.classList.contains('mindcare-auth-route') || !form || !csrf ||
        !form.querySelector('input[name="csrf_token"]') || shell.querySelector('script,iframe,object,embed'))
      throw Error('Unexpected login page');
    return {doc,shell,csrf};
  };
  const open = async url => {
    const token = ++generation;
    busy = true;
    destination = url.href;
    controller = new AbortController();
    const outgoing = document.querySelector('.site-shell');
    const skip = document.querySelector('.skip');
    const scroll = window.scrollY;
    const vacuum = spiralPath();
    const emission = vacuum.slice().reverse().map(k => ({...k,offset:1-k.offset}));
    // Cull the long landing's below-fold sections before promoting its viewport.
    // Their layout below the visible slice is not part of the vacuum effect.
    const below = [...outgoing.querySelectorAll('.mc-world-root > *')].filter(el => el.getBoundingClientRect().top >= window.innerHeight);
    below.forEach(el => el.setAttribute('data-mc-vacuum-offscreen',''));
    scene = document.createElement('div');
    scene.className = 'mc-vacuum-scene';
    scene.dataset.scene = 'landing';
    setPose(scene,vacuum[0]);
    root.style.setProperty('--mc-vortex-scroll-offset', (-scroll) + 'px');
    outgoing.inert = true;
    if (skip) skip.inert = true;
    outgoing.before(scene);
    scene.append(outgoing);
    root.classList.add('mc-vortex-departing');
    stage.hidden = false;
    stage.dataset.phase = 'absorbing';
    // Stop background section animations before the visible scene moves.
    window.dispatchEvent(new Event('mindcare:landing-dispose'));
    // This deadline is only for HTTP, never for snapshot capture or animation.
    requestTimer = setTimeout(() => { if (token === generation) controller?.abort(); },12000);
    const login = fetchLogin(url).finally(() => { if (token === generation) clearTimeout(requestTimer); });
    login.catch(() => {});
    try {
      // Snapshot preparation is optional and bounded. The existing DOM path
      // remains authoritative even if WebGL or capture is unavailable.
      try { gravity = window.MindcareGravity?.create() || null; } catch (error) {
        document.dispatchEvent(new CustomEvent('mindcare:gravity-fallback',{detail:{reason:'renderer setup: '+String(error.message||error)}}));
        gravity = null;
      }
      const renderer = gravity;
      const captured = renderer ? await renderer.capture(scene) : false;
      if (token !== generation) return;
      if (renderer && !captured) { renderer.destroy(); gravity = null; }
      const absorbed = await play([
        [scene,vacuum],
        [space,[{transform:portalTransform(.035),offset:0},{transform:portalTransform(.48),offset:.28},{transform:portalTransform(.88),offset:.65},{transform:portalTransform(1),offset:1}]],
        [backdrop,[{opacity:0,offset:0},{opacity:0,offset:.35},{opacity:1,offset:1}]]
      ],token);
      if (!absorbed) return;
      stage.dataset.phase = 'holding';
      const matrix = new DOMMatrixReadOnly(getComputedStyle(space).transform);
      document.dispatchEvent(new CustomEvent('mindcare:vortex-opened',{detail:{
        landingOpacity:Number(getComputedStyle(scene).opacity),portalScale:Math.hypot(matrix.m11,matrix.m12,matrix.m13)
      }}));
      const page = await login;
      if (token !== generation) return;
      if (!motion()) { fallback(); return; }
      clearTimeout(requestTimer);
      const next = document.importNode(page.shell,true);
      next.inert = true;
      next.querySelector('#auth-email-form').action = url.href;
      history.pushState({mindcareLogin:true},'',url.href);
      mounted = true;
      document.title = page.doc.title;
      document.querySelector('meta[name="csrf-token"]').content = page.csrf;
      const larger = document.body.classList.contains('large-text');
      document.body.className = page.doc.body.className;
      if (larger) document.body.classList.add('large-text');
      document.body.dataset.patient = '0';
      // Swap only while the viewport scene is invisible and tiny. It keeps
      // the same transform origin, actual dimensions and depth plane.
      scene.replaceChildren(next);
      scene.dataset.scene = 'login';
      root.style.removeProperty('--mc-vortex-scroll-offset');
      window.scrollTo(0,0);
      root.classList.add('mc-vortex-arriving');
      stage.dataset.phase = 'emitting';
      document.dispatchEvent(new Event('mindcare:login-mounted'));
      // Give the real login a layout/paint opportunity at the tiny pose.
      await frame();
      if (token !== generation) return;
      const loginRenderer = gravity;
      const loginCaptured = loginRenderer ? await loginRenderer.capture(scene) : false;
      if (token !== generation) return;
      if (loginRenderer && !loginCaptured) { loginRenderer.destroy(); gravity = null; }
      const emitted = await play([
        [scene,emission],
        [space,[{transform:portalTransform(1),offset:0},{transform:portalTransform(.88),offset:.35},{transform:portalTransform(.48),offset:.72},{transform:portalTransform(.035),offset:1}]],
        [backdrop,[{opacity:1,offset:0},{opacity:0,offset:.65},{opacity:0,offset:1}]]
      ],token);
      if (emitted) finish();
    } catch (error) {
      if (token !== generation) return;
      report('transition: '+String(error.message||error));
      if (mounted) { reset(); location.reload(); }
      else fallback();
    }
  };
  document.querySelectorAll('a[data-mc-vortex-link]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
          event.shiftKey || event.altKey || link.target || !motion() ||
          !window.fetch || !window.AbortController || !Element.prototype.animate || !document.timeline) return;
      const url = new URL(link.href,location.href);
      if (url.origin !== location.origin || url.pathname !== '/login') return;
      event.preventDefault();
      if (!busy) open(url);
    });
  });
  prefs.forEach(p => p.addEventListener?.('change',() => {
    if (!motion() && busy) { if (mounted) finish(); else fallback(); }
  }));
  document.addEventListener('keydown',event => {
    if (event.key === 'Escape' && busy) { if (mounted) finish(); else fallback(); }
  });
  window.addEventListener('popstate',() => { if (mounted || busy) location.reload(); });
  window.addEventListener('pageshow',event => { if (event.persisted) { ++generation; reset(); } });
})();
