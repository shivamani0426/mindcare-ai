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
  float ring=mix(.025,.205,k);
  float halo=exp(-abs(r-ring)*22.);
  vec3 glow=halo*vec3(.15,.46,.63);
  float thin=exp(-abs(r-ring)*118.);
  float arc=.55+.45*sin(theta*3.-u_time*1.25);
  glow+=thin*mix(vec3(.35,.88,1.),vec3(1.,.83,.43),arc)*1.3;
  // A tilted accretion disk adds a visible 3D depth cue around the dark core.
  vec2 d=vec2(q.x*.94+q.y*.34,-q.x*.34+q.y*.94);
  float diskRadius=length(vec2(d.x,d.y*3.1));
  float disk=exp(-abs(diskRadius-ring*1.22)*84.);
  glow+=disk*vec3(1.,.68,.28)*(.48+.52*sin(theta+u_time*.65)*sin(theta+u_time*.65));
  float core=1.-smoothstep(ring*.70,ring*.84,r);
  float gravity=smoothstep(.02,.28,p);
  vec3 color=mix(sky,page,matter);
  color+=glow*gravity*(1.-matter*.45);
  color=mix(color,vec3(.002,.003,.006),core*gravity);
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
    if(typeof window.html2canvas!=='function')return null;
    const canvas=document.createElement('canvas');
    canvas.className=cssClass;
    canvas.setAttribute('aria-hidden','true');
    canvas.hidden=true;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,depth:false,stencil:false,
      premultipliedAlpha:false,preserveDrawingBuffer:false,powerPreference:'low-power'});
    if(!gl){report('webgl unavailable');return null;}
    let destroyed=false, valid=false, raf=0, program, buffer, texture, vs, fs;
    let slow=0,last=0,quality=0,epoch=performance.now();
    const fail=()=>{valid=false;canvas.hidden=true;cancelAnimationFrame(raf);};
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
      const budget=quality===2?90000:quality===1?180000:matchMedia('(max-width:650px)').matches?240000:360000;
      const s=Math.min(1,Math.sqrt(budget/(w*h)),gl.getParameter(gl.MAX_TEXTURE_SIZE)/Math.max(w,h));
      canvas.width=Math.max(1,Math.round(w*s));canvas.height=Math.max(1,Math.round(h*s));
      gl.viewport(0,0,canvas.width,canvas.height);gl.uniform2f(uSize,canvas.width,canvas.height);
    };
    resize();
    document.body.append(canvas);
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();fail();},{once:true});
    const draw=(pull,now=performance.now())=>{
      if(!valid||destroyed||gl.isContextLost())return;
      gl.uniform1f(uPull,pull);gl.uniform1f(uTime,(now-epoch)/1000);
      canvas.dataset.pull=pull.toFixed(3);
      gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    };
    const capture=async(scene)=>{
      if(destroyed||gl.isContextLost())return false;
      const w=scene.clientWidth,h=scene.clientHeight;
      if(w<1||h<1)return false;
      const scale=Math.min(1,Math.sqrt(420000/(w*h)),gl.getParameter(gl.MAX_TEXTURE_SIZE)/Math.max(w,h));
      try{
        const shot=await timeout(window.html2canvas(scene,{
          width:w,height:h,windowWidth:window.innerWidth,windowHeight:window.innerHeight,
          scrollX:0,scrollY:0,scale,backgroundColor:'#04070c',logging:false,
          allowTaint:false,useCORS:false,imageTimeout:900,removeContainer:true,
          onclone:(_,target)=>{
            target.style.transform='none';target.style.opacity='1';
            target.style.visibility='visible';target.style.animation='none';
            target.querySelectorAll('input[type=password],input[type=email]').forEach(input=>{input.value='';});
          }
        }),2400);
        if(destroyed||gl.isContextLost())return false;
        gl.bindTexture(gl.TEXTURE_2D,texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,shot);
        if(gl.getError()!==gl.NO_ERROR)throw Error('texture upload failed');
        shot.width=1;shot.height=1;valid=true;
        // Warm up the fragment program before the motion clock starts.
        if(canvas.hidden){draw(.5);draw(0);}
        return true;
      }catch(error){report('capture: '+String(error.message||error));fail();return false;}
    };
    const run=(animation,phase,duration)=>{
      if(!valid||destroyed)return;
      cancelAnimationFrame(raf);canvas.hidden=false;last=0;slow=0;
      const reverse=phase==='emitting';
      canvas.dataset.phase=phase;
      document.dispatchEvent(new CustomEvent('mindcare:gravity-phase',{detail:{phase,renderer:'webgl',width:canvas.width,height:canvas.height}}));
      const tick=now=>{
        if(!valid||destroyed)return;
        const t=Math.max(0,Math.min(1,Number(animation.currentTime||0)/duration));
        const eased=t*t*(3-2*t);
        draw(reverse?1-eased:eased,now);
        if(last&&now-last>34)slow++;else slow=Math.max(0,slow-1);
        last=now;
        if(slow>=2&&quality<2){quality++;resize();slow=0;draw(reverse?1-eased:eased,now);}
        if(t<1)raf=requestAnimationFrame(tick);
      };
      draw(reverse?1:0);raf=requestAnimationFrame(tick);
    };
    const settle=phase=>{cancelAnimationFrame(raf);draw(phase==='emitting'?0:1);};
    const destroy=()=>{
      destroyed=true;valid=false;cancelAnimationFrame(raf);canvas.remove();
      gl.deleteTexture(texture);gl.deleteBuffer(buffer);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
    };
    return {capture,run,settle,destroy};
  }
  window.MindcareGravity={create};
})();
