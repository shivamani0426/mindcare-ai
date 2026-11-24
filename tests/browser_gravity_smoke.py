"""Exercise actual WebGL rendering with synthetic public pages; no user data."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix="mindcare-gravity-") as tmp:
    os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tmp) / "test.db")
    os.environ["SECRET_KEY"] = "synthetic-gravity-test"
    os.environ["SECURE_COOKIES"] = "0"
    from app import app, db
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        db.create_all()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--enable-webgl","--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width":1024,"height":700}, reduced_motion="no-preference")
            diagnostics = []
            page.on("console", lambda message: diagnostics.append(message.text) if message.text.startswith("GRAVITY:") else None)
            page.on("pageerror", lambda error: diagnostics.append(str(error)))
            page.add_init_script("""(() => {
                window.gravityTrace={phases:[],textures:[],draws:{},colors:{},fallbacks:[],pulls:{},lensing:null,documentId:Math.random().toString()};
                window.gravityShaders={};
                window.gravitySnapshots=[];
                const proto=WebGLRenderingContext.prototype;
                const originalSource=proto.shaderSource;
                proto.shaderSource=function(shader,source){
                    if(this.canvas.classList.contains('mc-gravity-canvas')){
                        window.gravityShaders[this.getShaderParameter(shader,this.SHADER_TYPE)]=source;
                    }
                    return originalSource.call(this,shader,source);
                };
                const originalTexture=proto.texImage2D;
                proto.texImage2D=function(...args){
                    const source=args[5];
                    if(this.canvas.classList.contains('mc-gravity-canvas') && source instanceof HTMLCanvasElement){
                        const ctx=source.getContext('2d');
                        const colors=new Set();
                        const pixels=ctx.getImageData(0,0,source.width,source.height).data;
                        for(let y=1;y<8;y++)for(let x=1;x<8;x++){
                            const i=(Math.floor(source.height*y/8)*source.width+Math.floor(source.width*x/8))*4;
                            colors.add(Array.from(pixels.subarray(i,i+4)).join(','));
                        }
                        window.gravityTrace.textures.push({width:source.width,height:source.height,colors:colors.size});
                        // Retain the already-read typed RGBA array; no second canvas copy.
                        window.gravitySnapshots.push({width:source.width,height:source.height,pixels});
                    }
                    return originalTexture.apply(this,args);
                };
                const originalDraw=proto.drawArrays;
                proto.drawArrays=function(...args){
                    const result=originalDraw.apply(this,args);
                    if(!this.canvas.classList.contains('mc-gravity-canvas'))return result;
                    const phase=this.canvas.dataset.phase;
                    if(!phase)return result;
                    const trace=window.gravityTrace;
                    trace.draws[phase]=(trace.draws[phase]||0)+1;
                    const pull=Number(this.canvas.dataset.pull);
                    (trace.pulls[phase]||=[]).push(pull);
                    return result;
                };
                document.addEventListener('mindcare:gravity-fallback',event=>{window.gravityTrace.fallbacks.push(event.detail);console.log('GRAVITY:'+JSON.stringify(event.detail));});
                document.addEventListener('mindcare:gravity-phase',event=>{
                    const stage=document.getElementById('mc-vortex');
                    const rings=[...stage.querySelectorAll('.mc-vortex-ring')];
                    const particles=[...stage.querySelectorAll('.mc-vortex-particle')];
                    const canvas=document.querySelector('.mc-gravity-canvas');
                    const ringStyle=getComputedStyle(rings[0]);
                    window.gravityTrace.phases.push({...event.detail,portal:{
                        rings:rings.length,particles:particles.length,
                        segmented:rings.every(r=>getComputedStyle(r).backgroundImage.includes('conic-gradient')),
                        masked:ringStyle.maskImage.includes('radial-gradient'),
                        rotating:rings.every(r=>getComputedStyle(r).animationName==='mc-vortex-spin'),
                        suction:particles.every(r=>getComputedStyle(r).animationName==='mc-vortex-suction'),
                        aboveGpu:Number(getComputedStyle(stage).zIndex)>Number(getComputedStyle(canvas).zIndex),
                        transparentBackdrop:getComputedStyle(stage.querySelector('.mc-vortex-backdrop')).visibility==='hidden',
                        visible:!stage.hidden&&getComputedStyle(stage).display!=='none'
                    }});
                    console.log('GRAVITY:'+JSON.stringify(event.detail));
                });
            })()""")
            page.goto(base + "/")
            assert page.evaluate("!!window.gravityTrace"), "Test instrumentation did not initialize"
            document_id = page.evaluate("window.gravityTrace.documentId")
            page.locator("#mc-carpet-intro").wait_for(state="hidden", timeout=6000)
            page.locator(".mc-hero-enter").click()
            page.wait_for_url("**/login", timeout=30000)
            page.wait_for_function("() => document.getElementById('mc-vortex').hidden", timeout=18000)
            live = page.evaluate("({trace:window.gravityTrace,snapshots:window.gravitySnapshots.length})")
            print("Live motion trace:", live, "diagnostics:", diagnostics, flush=True)
            assert live["trace"]["documentId"] == document_id, live
            assert live["snapshots"] == 2, ("missing actual page textures", live, diagnostics)
            assert not live["trace"]["fallbacks"], live
            # Read pixels only after live motion has completed: gl.readPixels
            # forces a synchronous pipeline stall on software-rendered CI.
            # Compile the exact production shader captured above and draw
            # actual uploaded page textures at deterministic progress values.
            page.evaluate("""() => {
                const trace=window.gravityTrace;
                const c=document.createElement('canvas');
                c.width=320;c.height=220;
                const gl=c.getContext('webgl',{alpha:true,antialias:false,depth:false});
                if(!gl)throw Error('pixel inspection context unavailable');
                const compile=type=>{
                    const shader=gl.createShader(type);
                    gl.shaderSource(shader,window.gravityShaders[type]);
                    gl.compileShader(shader);
                    if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));
                    return shader;
                };
                const vs=compile(gl.VERTEX_SHADER),fs=compile(gl.FRAGMENT_SHADER);
                const program=gl.createProgram();
                gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
                if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
                gl.useProgram(program);
                const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);
                gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
                const pos=gl.getAttribLocation(program,'a_position');
                gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
                const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
                gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
                gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
                gl.viewport(0,0,c.width,c.height);
                gl.uniform2f(gl.getUniformLocation(program,'u_size'),c.width,c.height);
                gl.uniform1i(gl.getUniformLocation(program,'u_page'),0);
                gl.uniform1f(gl.getUniformLocation(program,'u_time'),1.25);
                const draw=(source,pull)=>{
                    if(!source||!source.width||!source.height||!source.pixels)throw Error('missing captured RGBA source');
                    // Typed arrays use the explicit nine-argument WebGL overload.
                    const flipped=new Uint8Array(source.pixels.length);
                    const row=source.width*4;
                    for(let y=0;y<source.height;y++)flipped.set(source.pixels.subarray(y*row,(y+1)*row),(source.height-y-1)*row);
                    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
                    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,source.width,source.height,0,gl.RGBA,gl.UNSIGNED_BYTE,flipped);
                    gl.uniform1f(gl.getUniformLocation(program,'u_pull'),pull);
                    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
                    const pixels=new Uint8Array(c.width*c.height*4);
                    gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
                    if(gl.getError()!==gl.NO_ERROR)throw Error('pixel inspection error');
                    return (x,y)=>{
                        const i=(Math.floor(y)*c.width+Math.floor(x))*4;
                        return [pixels[i],pixels[i+1],pixels[i+2]];
                    };
                };
                for(const [i,phase] of ['absorbing','emitting'].entries()){
                    const sample=draw(window.gravitySnapshots[i],.5);
                    const colors=new Set();
                    for(let y=1;y<5;y++)for(let x=1;x<5;x++){
                        colors.add(sample(c.width*x/5,c.height*y/5).join(','));
                    }
                    trace.colors[phase]=colors.size;
                }
                // GPU now renders only the distorted page and space. The
                // classic segmented portal is independently composited in CSS.
                const sample=draw(window.gravitySnapshots[0],1);
                let bright=0,ringPixels=0;
                for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
                    const rr=Math.hypot(x+.5-c.width/2,y+.5-c.height/2)/c.height;
                    const [r,g,b]=sample(x,y);
                    if(Math.max(r,g,b)>130)bright++;
                    if(rr>.185&&rr<.225&&b>145&&g>65&&b>=r+20)ringPixels++;
                }
                trace.lensing={bright,ringPixels};
                gl.deleteTexture(tex);gl.deleteBuffer(buf);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);
                window.gravitySnapshots=[];
            }""")
            trace = page.evaluate("window.gravityTrace")
            print("WebGL trace:", trace, "diagnostics:", diagnostics)
            assert trace["documentId"] == document_id, ("unexpected full navigation", diagnostics)
            assert [entry["phase"] for entry in trace["phases"]] == ["absorbing","emitting"], trace
            assert len(trace["textures"]) == 2 and all(t["width"]*t["height"] <= 910000 and t["colors"] >= 5 for t in trace["textures"]), trace
            assert all(trace["draws"].get(phase,0) >= 5 and trace["colors"].get(phase,0) >= 3 for phase in ("absorbing","emitting")), trace
            assert all(any(.35 < value < .65 for value in trace["pulls"].get(phase,[])) for phase in ("absorbing","emitting")), trace
            assert max(trace["pulls"]["absorbing"]) >= .985 and min(trace["pulls"]["emitting"]) <= .015, trace
            assert not trace["fallbacks"], trace
            assert trace["lensing"], "no GPU endpoint rendered sample"
            assert trace["lensing"]["ringPixels"] < 200, trace["lensing"]
            for entry in trace["phases"]:
                portal = entry["portal"]
                assert portal["rings"] == 9 and portal["particles"] == 16, portal
                assert all(portal[k] for k in ("segmented","masked","rotating","suction","aboveGpu","transparentBackdrop","visible")), portal
            assert page.locator(".mc-gravity-canvas").count() == 0
            assert page.locator("#auth-email").is_visible()
            # Close the completed GPU page before opening an independent fallback page.
            # This avoids competing background animation clocks in the software browser.
            page.close()
            # No WebGL/capture: the already tested stable DOM spiral must remain usable.
            fallback=browser.new_page(viewport={"width":1024,"height":700}, reduced_motion="no-preference")
            fallback.goto(base+"/")
            fallback.locator("#mc-carpet-intro").wait_for(state="hidden", timeout=6000)
            fallback.evaluate("window.MindcareGravity=undefined")
            fallback.locator(".mc-hero-enter").click()
            fallback.wait_for_url("**/login",timeout=12000)
            fallback.wait_for_function("() => document.getElementById('mc-vortex').hidden",timeout=12000)
            assert fallback.locator(".mc-gravity-canvas").count()==0 and fallback.locator("#auth-email").is_visible()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
