"""Target Firefox, including actual intermediate geometry and form submission."""
import os
import sys
import tempfile
import threading
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix="mindcare-vacuum-") as tmp:
    os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tmp) / "test.db")
    os.environ["SECRET_KEY"] = "synthetic-vacuum-test"
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
            browser = p.firefox.launch()
            page = browser.new_page(viewport={"width":1280,"height":720}, reduced_motion="no-preference")
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/")
            page.locator("#mc-carpet-skip").click()
            page.evaluate("""() => {
                window.samples = [];
                window.originalPortal = document.getElementById('mc-vortex');
                document.addEventListener('mindcare:vortex-motion', event => {
                    const phase = event.detail.phase;
                    const scene = document.querySelector('.mc-vacuum-scene');
                    const animation = scene.getAnimations()[0];
                    function sample() {
                        if (!scene.isConnected || animation.playState !== 'running') return;
                        const style = getComputedStyle(scene);
                        const m = new DOMMatrixReadOnly(style.transform);
                        const scale = Math.hypot(m.m11,m.m12,m.m13);
                        window.samples.push({phase,scale,opacity:Number(style.opacity)});
                        requestAnimationFrame(sample);
                    }
                    requestAnimationFrame(sample);
                });
            }""")
            page.locator(".mc-hero-enter").click()
            page.wait_for_url("**/login", timeout=16000)
            page.wait_for_function("() => document.getElementById('mc-vortex').hidden", timeout=16000)
            assert page.evaluate("window.originalPortal === document.getElementById('mc-vortex')")
            samples = page.evaluate("window.samples")
            for phase, direction in (("absorbing", -1), ("emitting", 1)):
                values = [s["scale"] for s in samples if s["phase"] == phase]
                intermediate = [v for v in values if .1 < v < .9]
                assert len(intermediate) >= 3 and (values[-1]-values[0])*direction > .45, (phase, values)
                print(f"Firefox {phase}: {len(values)} rendered samples, {len(intermediate)} intermediate poses")
            assert page.locator("#auth-email").is_visible()
            assert page.locator(".mc-vacuum-scene").count() == 0
            page.locator("#auth-email").fill("missing@example.invalid")
            page.locator("#auth-password").fill("synthetic-password")
            with page.expect_response(lambda r: r.url == base + "/login" and r.request.method == "POST") as response:
                page.locator("#auth-email-form button[type=submit]").click()
            assert response.value.status < 500
            assert page.locator("#auth-email").is_visible()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
