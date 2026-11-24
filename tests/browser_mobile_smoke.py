"""Mobile Chromium and WebKit smoke tests against disposable synthetic data."""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix="mindcare-mobile-") as tmp:
    os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tmp) / "test.db")
    os.environ["SECRET_KEY"] = "local-synthetic-test-only"
    os.environ["SECURE_COOKIES"] = "0"
    from app import app, db
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        db.create_all()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            for engine, device, role in [
                ("chromium", "Pixel 7", "patient"),
                ("webkit", "iPhone 13", "caregiver"),
            ]:
                browser = getattr(p, engine).launch()
                ctx = browser.new_context(**p.devices[device], reduced_motion="reduce")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/register")
                assert page.locator("#main").get_attribute("tabindex") == "-1"
                assert page.locator(".skip").count() == 1
                assert page.locator("#main").count() == 1
                assert page.locator(".auth-v2-email-form").is_visible()
                page.locator('input[name="name"]').fill("Synthetic " + role)
                page.locator('input[name="email"]').fill(role + "@example.invalid")
                page.locator('input[name="password"]').fill("demo-only-strong-password-2026")
                page.locator(f'input[name="role"][value="{role}"]').check(force=True)
                page.get_by_role("button", name="Create my account", exact=False).click()
                page.wait_for_url("**/dashboard")
                paths = ["/dashboard", "/reminders", "/family", "/account/security"]
                if role == "patient":
                    paths += ["/games", "/help", "/settings"]
                for path in paths:
                    response = page.goto(base + path)
                    assert response.status == 200, (engine, path, response.status)
                    page.wait_for_load_state("domcontentloaded")
                    assert page.locator("#main").is_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 3"), (engine, path)
                    assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
                assert not errors, (engine, errors)
                print(f"{engine} / {device} / {role}: passed {len(paths)} authenticated routes")
                ctx.close()
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
