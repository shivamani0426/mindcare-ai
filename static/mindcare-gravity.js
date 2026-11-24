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
uniform float u_view;
uniform float u_orbit;
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
// A periodic particle field in the disk's own 3D polar coordinates.
 // The time-dependent angular coordinate advects entire glowing streaks
 // around the hole, instead of merely pulsing a stationary ring.
 vec2 orbitEmbers(float radius,float angle,float clock){
   float lanes=(radius-.76)*5.2;
   float lane=floor(lanes);
   float radial=fract(lanes);
   float speed=2.55/pow(max(.85,radius),1.35);
   float sectors=(angle+clock*speed)/(2.*PI)*14.;
   float sector=mod(floor(sectors),14.);
   float along=fract(sectors);
   float seed=hash(vec2(lane+17.,sector+3.));
   float mid=.28+.44*seed;
   float thickness=.10+.10*seed;
   float across=1.-smoothstep(thickness,thickness+.13,abs(radial-mid));
   float head=.72+.14*seed;
   float tail=smoothstep(head-.64,head-.30,along)*(1.-smoothstep(head-.05,head+.04,along));
   float core=1.-smoothstep(.025,.085,abs(along-head+.035));
   float active=smoothstep(.13,.34,seed);
   return vec2(tail,core)*across*active;
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
  // Perspective 3D scene in normalized black-hole coordinates. Each pixel
  // traces a camera ray through a real sphere and inclined annular disk.
  // The photon arc is a bounded artistic lensing approximation, not a
  // numerical integration of Einstein's equations.
  float ring=mix(.025,.205,k);
  vec2 n=q/ring;
  vec2 d=vec2(n.x*.985+n.y*.172,-n.x*.172+n.y*.985);
  float h=length(d);
  float aa=max(.008,1.25/(u_size.y*ring));
  float gravity=smoothstep(.02,.28,p);
  vec3 eye=vec3(0.,0.,6.);
  vec3 ray=normalize(vec3(d,-6.));
  float sphereRadius=.715;
  float b=dot(eye,ray);
  float discriminant=b*b-dot(eye,eye)+sphereRadius*sphereRadius;
  float sphereHit=-b-sqrt(max(0.,discriminant));
  float shadow=smoothstep(-aa*.8,aa*.8,discriminant);
  // Camera pitch changes the actual plane normal. No painted ellipse.
  float inclination=.235+.018*sin(u_time*.55)+u_view;
  vec3 normal=normalize(vec3(0.,1.,inclination));
  float denom=dot(ray,normal);
  float safeDenom=abs(denom)<.0001?(denom<0.?-.0001:.0001):denom;
  float diskHit=-dot(eye,normal)/safeDenom;
  vec3 hit=eye+ray*max(diskHit,0.);
  float diskR=length(hit);
  float diskAngle=atan(hit.z,hit.x);
  float band=smoothstep(.79,.92,diskR)*(1.-smoothstep(2.25,2.92,diskR));
  band*=step(.001,diskHit);
  // Kepler-inspired differential rotation makes inner plasma move faster.
  float orbital=u_orbit*2.2/max(.75,diskR);
  float streak=.65+.35*sin(47.*diskR+4.*diskAngle-orbital);
  float turbulence=.78+.22*sin(11.*diskAngle+23.*diskR-orbital*.7);
  float inner=1.-smoothstep(.90,1.95,diskR);
  vec3 plasma=mix(vec3(.065,.25,.96),vec3(.72,.91,1.),inner);
  float boost=mix(.55,1.48,smoothstep(-1.1,1.1,hit.x));
  vec3 diskLight=band*plasma*(.54+.38*streak)*turbulence*boost;
  if(band>.002){
    vec2 embers=orbitEmbers(diskR,diskAngle,u_orbit);
    // Electric-blue tails, ice-white heads and independently orbiting
    // lanes. The existing 3D visibility test occludes the rear particles.
    vec3 hot=vec3(.075,.37,1.)*boost;
    diskLight=mix(diskLight,hot*band,embers.x*.86);
    diskLight+=band*embers.y*vec3(.49,.91,1.)*boost*.85;
  }
  float rim=(1.-smoothstep(aa*1.5,.13+aa,abs(diskR-.93)))*step(.001,diskHit);
  diskLight+=rim*vec3(.83,.95,1.)*.88*boost;
  // Depth test the nearest 3D surface. The rear disk is hidden by the
  // sphere; the near disk remains visible in front of it.
  float front=step(diskHit,sphereHit)*step(.001,diskHit);
  float visibility=1.-shadow*(1.-front);
  // Lensed images of the far disk arc around the apparent shadow.
  // Inclination shapes the image; the hot inner edge forms the photon ring.
  float upper=smoothstep(-.10,.36,d.y);
  float lower=1.-smoothstep(-.42,-.06,d.y);
  float farBand=smoothstep(.76,.84,h)*(1.-smoothstep(1.12,1.49,h));
  float arcTexture=.70+.30*sin(31.*h+3.*theta-u_orbit*3.4);
  float lensBoost=mix(.54,1.48,smoothstep(-1.1,1.1,d.x));
  float lensed=farBand*(upper+.29*lower)*arcTexture*lensBoost;
  float photon=1.-smoothstep(aa,aa+.047,abs(h-.755));
  float halo=1.-smoothstep(.77,1.82,h);
  vec3 backGlow=vec3(.045,.20,.55)*halo*.40;
  backGlow+=lensed*mix(vec3(.065,.32,.95),vec3(.68,.92,1.),1.-smoothstep(.85,1.30,h));
  if(farBand>.002){
    // The bent far-side image carries the same moving blue plasma.
    vec2 bent=orbitEmbers(h+.38,theta,u_orbit);
    backGlow=mix(backGlow,vec3(.065,.36,1.)*lensBoost,
      bent.x*farBand*(upper+.26*lower)*.67);
    backGlow+=bent.y*farBand*(upper+.26*lower)*vec3(.47,.85,1.)*.52;
  }
  backGlow+=photon*vec3(.76,.93,1.)*(.65+.35*lensBoost);
  vec3 color=mix(sky,page,matter);
  color+=backGlow*gravity*(1.-matter*.45);
  color=mix(color,vec3(.001,.001,.002),shadow*gravity);
  color+=diskLight*visibility*gravity;
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
    // Software WebGL executes the fragment shader on the CPU. Keep the
    // full existing quality budget for hardware GPUs (including Brave).
    const debugRenderer=gl.getExtension('WEBGL_debug_renderer_info');
    const rendererName=debugRenderer?String(gl.getParameter(debugRenderer.UNMASKED_RENDERER_WEBGL)):'';
    const software=/swiftshader|llvmpipe|softpipe|software rasterizer/i.test(rendererName);
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
    gl.uniform1f(gl.getUniformLocation(program,'u_view'),0);
    const uOrbit=gl.getUniformLocation(program,'u_orbit');
    const resize=()=>{
      const w=window.innerWidth,h=window.innerHeight;
      const budget=software?Math.min(85000,quality===2?50000:quality===1?65000:85000):quality===2?85000:quality===1?140000:matchMedia('(max-width:650px)').matches?160000:240000;
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
      gl.uniform1f(uOrbit,(now-epoch)/1000);
      canvas.dataset.pull=pull.toFixed(3);
      gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    };
    const capture=async(scene)=>{
      if(destroyed||gl.isContextLost()){report('context unavailable before capture');return false;}
      const w=scene.clientWidth,h=scene.clientHeight;
      if(w<1||h<1){report('empty capture dimensions');return false;}
      const scale=Math.min(1,Math.sqrt((software?160000:300000)/(w*h)),gl.getParameter(gl.MAX_TEXTURE_SIZE)/Math.max(w,h));
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
        }),software?7000:4800);
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
            if(valid)report('render deadline: '+phase);
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
      // Keep the accretion matter orbiting during the login snapshot hold.
      // Reuse the same RAF handle; run(), fail/cleanup and destroy() stop it.
      if(phase==='absorbing'&&valid){
        const start=performance.now();
        let last=start;
        const hold=now=>{
          if(!valid||destroyed||gl.isContextLost()||now-start>8000)return;
          if(now-last>=(software?83:33)){draw(1,now);last=now;}
          raf=requestAnimationFrame(hold);
        };
        raf=requestAnimationFrame(hold);
      }
    };
    const destroy=()=>{
      destroyed=true;valid=false;stopRun();canvas.remove();
      gl.deleteTexture(texture);gl.deleteBuffer(buffer);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
    };
    return {capture,run,settle,destroy};
  }
  window.MindcareGravity={create};
})();
