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
                window.gravityTrace={phases:[],textures:[],draws:{},colors:{},fallbacks:[],pulls:{},documentId:Math.random().toString()};
                const proto=WebGLRenderingContext.prototype;
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
                    if(pull>.35&&pull<.65&&!trace.colors[phase]){
                        const colors=new Set();
                        const w=this.drawingBufferWidth,h=this.drawingBufferHeight;
                        const pixels=new Uint8Array(w*h*4);
                        // One readback, not sixteen synchronous GPU stalls.
                        this.readPixels(0,0,w,h,this.RGBA,this.UNSIGNED_BYTE,pixels);
                        for(let y=1;y<5;y++)for(let x=1;x<5;x++){
                            const i=(Math.floor(h*y/5)*w+Math.floor(w*x/5))*4;
                            colors.add(Array.from(pixels.subarray(i,i+4)).join(','));
                        }
                        trace.colors[phase]=colors.size;
                    }
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
            trace = page.evaluate("window.gravityTrace")
            print("WebGL trace:", trace, "diagnostics:", diagnostics)
            assert trace["documentId"] == document_id, ("unexpected full navigation", diagnostics)
            assert [entry["phase"] for entry in trace["phases"]] == ["absorbing","emitting"], trace
            assert len(trace["textures"]) == 2 and all(t["width"]*t["height"] <= 910000 and t["colors"] >= 5 for t in trace["textures"]), trace
            assert all(trace["draws"].get(phase,0) >= 5 and trace["colors"].get(phase,0) >= 3 for phase in ("absorbing","emitting")), trace
            assert all(any(.35 < value < .65 for value in trace["pulls"].get(phase,[])) for phase in ("absorbing","emitting")), trace
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
