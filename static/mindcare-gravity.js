/* Public-page snapshots stay in GPU memory; no uploads, persistence or user data capture.
   html2canvas is a locally vendored MIT dependency. The original DOM transition
   continues underneath so unsupported/slow devices can use the approved fallback. */
(() => {
  'use strict';
  const vertex = `attribute vec2 a_position;
varying vec2 v_uv;
void main(){v_uv=a_position*.5+.5;gl_Position=vec4(a_position,0.,1.);}`;
  const fragment = `precision highp float;
varying vec2 v_uv;
uniform sampler2D u_page;
uniform vec2 u_size;
uniform float u_pull;
uniform float u_time;
#define PI 3.14159265359
float hash(vec2 p){vec3 v=fract(vec3(p.xyx)*.1031);v+=dot(v,v.yzx+33.33);return fract((v.x+v.y)*v.z);}
float star(vec2 p,float cells,float seed){
  vec2 g=p*cells, id=floor(g), f=fract(g)-.5;
  float h=hash(id+seed);
  vec2 center=vec2(hash(id+11.2),hash(id+23.7))*.7-.35;
  float d=length(f-center);
  float strength=smoothstep(.73,.98,h);
  return (1.-smoothstep(.015,.12,d))*strength*(.72+.28*sin(u_time*1.1+h*24.));
}
void main(){
  float p=clamp(u_pull,0.,1.);
  float k=p*p*(3.-2.*p);
  float aspect=u_size.x/u_size.y;
  vec2 q=(v_uv-.5)*vec2(aspect,1.);
  float r=length(q);
  float theta=atan(q.y,q.x);
  // Inverse polar mapping: differential angular velocity twists inner and
  // outer image pixels by different amounts, rather than rotating a rectangle.
  float zoom=mix(1.,.018,k);
  float sr=r/max(zoom,.018);
  float curl=6.4*k/(.42+sr*1.55);
  float a=theta+curl+2.1*k;
  float stretch=1.+.50*sin(PI*p)*sin(a*2.+sr*3.2);
  vec2 source=vec2(cos(a),sin(a))*sr*stretch;
  source.y*=1.+.72*sin(PI*p);
  vec2 uv=source/vec2(aspect,1.)+.5;
  vec2 edge=min(uv,1.-uv);
  float inside=smoothstep(0.,.009,min(edge.x,edge.y));
  vec3 page=texture2D(u_page,clamp(uv,0.,1.)).rgb;
  float matter=inside*(1.-smoothstep(.83,1.,p));
  // Pull the star field into the same differential swirl; the exact pull
  // parameter reverses when the incoming page is reconstructed.
  float sa=theta+2.9*k/(.13+r*2.4);
  vec2 st=vec2(cos(sa),sin(sa))*r*(1.+1.8*k);
  float stars=star(st,43.,2.);
  vec3 sky=vec3(.011,.019,.035)+stars*vec3(.82,.92,1.);
  // Analytic, cinematic approximation of a lensed accretion disk.
  // No ray-marching, extra texture, render pass, or added motion clock.
  float ring=mix(.025,.205,k);
  vec2 n=q/ring;
  vec2 d=vec2(n.x*.985+n.y*.172,-n.x*.172+n.y*.985);
  float h=length(d);
  float aa=max(.008,1.25/(u_size.y*ring));
  float shadow=1.-smoothstep(.715-aa,.715+aa,h);
  float gravity=smoothstep(.02,.28,p);
  // The upper image of the far disk is bent around the shadow. Its weaker
  // lower counterpart and the narrow photon ring outline the horizon.
  float upper=smoothstep(-.10,.36,d.y);
  float lower=1.-smoothstep(-.42,-.06,d.y);
  float farBand=smoothstep(.76,.84,h)*(1.-smoothstep(1.12,1.49,h));
  float arcTexture=.68+.32*sin(31.*h+3.*theta-u_time*1.1);
  float boost=mix(.54,1.48,smoothstep(-1.1,1.1,d.x));
  float lensed=farBand*(upper+.29*lower)*arcTexture*boost;
  float photon=1.-smoothstep(aa,aa+.047,abs(h-.755));
  float halo=1.-smoothstep(.77,1.82,h);
  vec3 backGlow=vec3(.32,.115,.035)*halo*.40;
  backGlow+=lensed*mix(vec3(.92,.24,.035),vec3(1.,.83,.51),1.-smoothstep(.85,1.30,h));
  backGlow+=photon*vec3(1.,.88,.67)*(.65+.35*boost);
  // Project a thin, extended, inclined disk into the image plane. Radial
  // filaments suggest orbiting hot plasma and an asymmetric Doppler glow.
  float diskR=length(vec2(d.x,d.y/.245));
  float band=smoothstep(.79,.92,diskR)*(1.-smoothstep(2.25,2.92,diskR));
  float streak=.57+.43*sin(47.*diskR+4.*theta-u_time*1.5);
  float inner=1.-smoothstep(.90,1.95,diskR);
  vec3 plasma=mix(vec3(.80,.14,.025),vec3(1.,.87,.59),inner);
  vec3 diskLight=band*plasma*(.74+.44*streak)*boost;
  float rim=1.-smoothstep(aa*1.5,.13+aa,abs(diskR-.93));
  diskLight+=rim*vec3(1.,.94,.78)*.85*boost;
  float front=1.-smoothstep(-aa,aa,d.y);
  vec3 color=mix(sky,page,matter);
  // Occlude the rear disk at the event-horizon shadow, then lay the nearer
  // accretion stream across it. This ordering provides the 3D depth cue.
  color+=(backGlow+diskLight*(1.-front))*gravity*(1.-matter*.45);
  color=mix(color,vec3(.001,.001,.002),shadow*gravity);
  color+=diskLight*front*gravity;
  // Smooth handoff to/from actual DOM at the unwarped endpoint.
  float alpha=smoothstep(.01,.13,p);
  gl_FragColor=vec4(clamp(color,0.,1.),alpha);
}`;
  const cssClass='mc-gravity-canvas';
  const report=(reason)=>document.dispatchEvent(new CustomEvent('mindcare:gravity-fallback',{detail:{reason}}));
  const frame = () => new Promise(resolve=>requestAnimationFrame(resolve));
  const timeout = (promise,ms) => {
    let timer;
    return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('snapshot deadline')),ms);})]).finally(()=>clearTimeout(timer));
  };
  function create(){
    if(typeof window.html2canvas!=='function'){report('capture library unavailable');return null;}
    const canvas=document.createElement('canvas');
    canvas.className=cssClass;
    canvas.setAttribute('aria-hidden','true');
    canvas.hidden=true;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,depth:false,stencil:false,
      premultipliedAlpha:false,preserveDrawingBuffer:false,powerPreference:'low-power'});
    if(!gl){report('webgl unavailable');return null;}
    let destroyed=false, valid=false, raf=0, program, buffer, texture, vs, fs;
    let quality=0,resolveRun=null,epoch=performance.now();
    const stopRun=()=>{cancelAnimationFrame(raf);if(resolveRun){const done=resolveRun;resolveRun=null;done();}};
    const fail=()=>{valid=false;canvas.hidden=true;};
    const compile=(type,source)=>{
      const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)){const message=gl.getShaderInfoLog(shader);gl.deleteShader(shader);throw Error(message);}
      return shader;
    };
    try{
      vs=compile(gl.VERTEX_SHADER,vertex);fs=compile(gl.FRAGMENT_SHADER,fragment);
      program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
      gl.useProgram(program);
      buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
      const loc=gl.getAttribLocation(program,'a_position');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0);
      texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      gl.uniform1i(gl.getUniformLocation(program,'u_page'),0);
    }catch(error){
      report('shader initialization: '+String(error.message||error));
      if(program)gl.deleteProgram(program);if(vs)gl.deleteShader(vs);if(fs)gl.deleteShader(fs);
      if(buffer)gl.deleteBuffer(buffer);if(texture)gl.deleteTexture(texture);return null;
    }
    const uSize=gl.getUniformLocation(program,'u_size'),uPull=gl.getUniformLocation(program,'u_pull'),uTime=gl.getUniformLocation(program,'u_time');
    const resize=()=>{
      const w=window.innerWidth,h=window.innerHeight;
      const budget=quality===2?85000:quality===1?140000:matchMedia('(max-width:650px)').matches?160000:240000;
      const s=Math.min(1,Math.sqrt(budget/(w*h)),gl.getParameter(gl.MAX_TEXTURE_SIZE)/Math.max(w,h));
      canvas.width=Math.max(1,Math.round(w*s));canvas.height=Math.max(1,Math.round(h*s));
      gl.viewport(0,0,canvas.width,canvas.height);gl.uniform2f(uSize,canvas.width,canvas.height);
    };
    resize();
    // Do not insert the WebGL surface until the first capture is complete.
    // html2canvas clones the document and copying a live WebGL canvas can
    // trigger a synchronous readback, particularly on software graphics.
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();report('context lost');fail();},{once:true});
    const draw=(pull,now=performance.now())=>{
      if(!valid||destroyed||gl.isContextLost())return;
      gl.uniform1f(uPull,pull);gl.uniform1f(uTime,(now-epoch)/1000);
      canvas.dataset.pull=pull.toFixed(3);
      gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    };
    const capture=async(scene)=>{
      if(destroyed||gl.isContextLost()){report('context unavailable before capture');return false;}
      const w=scene.clientWidth,h=scene.clientHeight;
      if(w<1||h<1){report('empty capture dimensions');return false;}
      const scale=Math.min(1,Math.sqrt(300000/(w*h)),gl.getParameter(gl.MAX_TEXTURE_SIZE)/Math.max(w,h));
      // Clone only the visible public scene plus its style/ancestor chain.
      // Avoid expensive hidden entrance, below-fold content and live overlays.
      const captureIgnore=el=>{
        if(el===scene||el.contains(scene)||el.tagName==='HEAD'||document.head.contains(el))return false;
        if(!scene.contains(el))return true;
        return el.hidden||el.hasAttribute('data-mc-vacuum-offscreen')||el.id==='mc-carpet-intro'||el.tagName==='SCRIPT';
      };
      try{
        const shot=await timeout(window.html2canvas(scene,{
          width:w,height:h,windowWidth:window.innerWidth,windowHeight:window.innerHeight,
          scrollX:0,scrollY:0,scale,backgroundColor:'#04070c',logging:false,
          allowTaint:false,useCORS:false,imageTimeout:900,removeContainer:true,
          ignoreElements:captureIgnore,
          onclone:(_,target)=>{
            target.style.transform='none';target.style.opacity='1';
            target.style.visibility='visible';target.style.animation='none';
            // Snapshot renderer cannot reproduce expensive live filters exactly.
            // Retain backgrounds, colors, geometry, text and image content.
            for(const el of target.querySelectorAll('*')){
              if(!el.style)continue;
              el.style.animation='none';el.style.transition='none';
              el.style.filter='none';el.style.backdropFilter='none';
              el.style.boxShadow='none';el.style.textShadow='none';
            }
            target.querySelectorAll('input[type=password],input[type=email]').forEach(input=>{input.value='';});
          }
        }),4800);
        if(destroyed||gl.isContextLost()){report('context unavailable after capture');return false;}
        gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,shot);
        if(gl.getError()!==gl.NO_ERROR)throw Error('texture upload failed');
        shot.width=1;shot.height=1;valid=true;
        return true;
      }catch(error){report('capture: '+String(error.message||error));fail();return false;}
    };
    const run=(animations,phase,duration)=>{
      if(!valid||destroyed)return null;
      stopRun();
      if(!canvas.isConnected)document.body.append(canvas);
      canvas.hidden=false;
      const reverse=phase==='emitting';
      canvas.dataset.phase=phase;
      // Pause the compositor clocks and advance them with the same sampled
      // frame as the shader. Cap elapsed steps so a stalled GPU cannot skip
      // across the entire middle of the distortion.
      for(const animation of animations){animation.pause();animation.currentTime=0;}
      document.dispatchEvent(new CustomEvent('mindcare:gravity-phase',{detail:{phase,renderer:'webgl',width:canvas.width,height:canvas.height}}));
      return new Promise(resolve=>{
        resolveRun=resolve;
        let elapsed=0,previous=null,slowFrames=0,totalFrames=0,started=performance.now();
        const tick=now=>{
          if(destroyed){stopRun();return;}
          const delta=previous===null?0:Math.max(0,now-previous);
          previous=now;
          elapsed=Math.min(duration,elapsed+Math.min(64,delta));
          const t=elapsed/duration;
          const eased=t*t*(3-2*t);
          for(const animation of animations)animation.currentTime=elapsed;
          if(valid)draw(reverse?1-eased:eased,now);
          totalFrames++;
          if(delta>48)slowFrames++;
          if(!valid||now-started>duration*3){
            // Retain the exact DOM pose and let the compositor finish
            // independently if this graphics device cannot sustain motion.
            fail();
            for(const animation of animations)animation.play();
            Promise.all(animations.map(animation=>animation.finished)).then(stopRun,stopRun);
            return;
          }
          if(t>=1){
            // Lower the next phase's resolution, never resize a live frame.
            if(slowFrames>totalFrames/4)quality=Math.min(2,quality+1);
            stopRun();return;
          }
          raf=requestAnimationFrame(tick);
        };
        raf=requestAnimationFrame(tick);
      });
    };
    const settle=phase=>{
      stopRun();
      // Keep the opaque absorption endpoint visible while login is captured.
      // Update resolution before the following phase, not during animation.
      if(phase==='absorbing'&&quality>0)resize();
      draw(phase==='emitting'?0:1);
    };
    const destroy=()=>{
      destroyed=true;valid=false;stopRun();canvas.remove();
      gl.deleteTexture(texture);gl.deleteBuffer(buffer);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
    };
    return {capture,run,settle,destroy};
  }
  window.MindcareGravity={create};
})();
