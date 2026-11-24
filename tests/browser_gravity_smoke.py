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
                document.addEventListener('mindcare:gravity-phase',event=>{window.gravityTrace.phases.push(event.detail);console.log('GRAVITY:'+JSON.stringify(event.detail));});
            })()""")
            page.goto(base + "/")
            assert page.evaluate("!!window.gravityTrace"), "Test instrumentation did not initialize"
            document_id = page.evaluate("window.gravityTrace.documentId")
            page.locator("#mc-carpet-skip").click()
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
                const view=gl.getUniformLocation(program,'u_view');
                if(view===null)throw Error('3D camera inclination uniform missing');
                gl.uniform1f(view,0);
                const sample=draw(window.gravitySnapshots[0],1);
                let upper=0,wing=0,warm=0;
                for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
                    const nx=(x-c.width/2)/(c.height*.205),ny=(y-c.height/2)/(c.height*.205);
                    const dx=nx*.985+ny*.172,dy=-nx*.172+ny*.985;
                    const rr=Math.hypot(dx,dy),dr=Math.hypot(dx,dy/.245);
                    const [r,g,b]=sample(x,y);
                    if(r>150&&g>65&&r>b+35){
                        warm++;
                        if(dy>.35&&rr>.77&&rr<1.45)upper++;
                        if(Math.abs(dx)>1.3&&Math.abs(dy)<.65&&dr<2.95)wing++;
                    }
                }
                // Inspect the same scene from a different 3D viewing angle.
                // The projected disk must change while the central sphere stays dark.
                gl.uniform1f(view,.30);
                const tilted=draw(window.gravitySnapshots[0],1);
                let viewChanges=0;
                for(let y=0;y<c.height;y+=2)for(let x=0;x<c.width;x+=2){
                    const a=sample(x,y),b=tilted(x,y);
                    if(Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1])+Math.abs(a[2]-b[2])>45)viewChanges++;
                }
                trace.lensing={center:sample(c.width/2,c.height/2),upper,wing,warm,viewChanges,tiltedCenter:tilted(c.width/2,c.height/2)};
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
            assert trace["lensing"], "no near-horizon rendered sample"
            assert max(trace["lensing"]["center"]) <= 20, trace["lensing"]
            assert trace["lensing"]["upper"] >= 15 and trace["lensing"]["wing"] >= 15, trace["lensing"]
            assert trace["lensing"]["viewChanges"] >= 100, trace["lensing"]
            assert max(trace["lensing"]["tiltedCenter"]) <= 20, trace["lensing"]
            assert page.locator(".mc-gravity-canvas").count() == 0
            assert page.locator("#auth-email").is_visible()
            # No WebGL/capture: the already tested stable DOM spiral must remain usable.
            fallback=browser.new_page(viewport={"width":1024,"height":700}, reduced_motion="no-preference")
            fallback.goto(base+"/")
            fallback.locator("#mc-carpet-skip").click()
            fallback.evaluate("window.MindcareGravity=undefined")
            fallback.locator(".mc-hero-enter").click()
            fallback.wait_for_url("**/login",timeout=12000)
            fallback.wait_for_function("() => document.getElementById('mc-vortex').hidden",timeout=12000)
            assert fallback.locator(".mc-gravity-canvas").count()==0 and fallback.locator("#auth-email").is_visible()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
